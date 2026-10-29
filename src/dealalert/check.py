"""One pass over the watchlist: fetch, filter, decide, alert.

Alert rules:
- Slickdeals post that matches an item, posted recently, not seen before:
  at or below target -> high priority; within ``near_pct`` above target ->
  default priority; price not in the title -> low priority ("check price").
  Anything pricier is ignored. Each post alerts at most once.
- Best Buy: alert when the lowest matching price is at or below target and
  lower than the price last alerted on, or when it is a new low within
  ``near_pct`` of target.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

from . import ntfy
from .ntfy import Alert
from .sources import Listing, bestbuy, slickdeals
from .state import State
from .watchlist import Item, Watchlist, matches

log = logging.getLogger(__name__)

SlickdealsSearch = Callable[[str], list[Listing]]
BestBuySearch = Callable[[str], list[Listing]]


def _money(value: float) -> str:
    return f"${value:,.0f}" if value == int(value) else f"${value:,.2f}"


def slickdeals_alerts(item: Item, listings: list[Listing], wl: Watchlist, state: State, now: datetime) -> list[Alert]:
    alerts = []
    cutoff = now - timedelta(days=wl.max_post_age_days)
    near_limit = item.target * (1 + wl.near_pct)
    for listing in listings:
        if not matches(item, listing.title, wl.exclude):
            continue
        if listing.posted and listing.posted < cutoff:
            continue
        if state.seen(listing.url):
            continue
        state.mark_seen(listing.url)

        price = listing.price
        if price is None:
            alerts.append(Alert(f"{item.name}: new deal posted", listing.title, ntfy.CHECK_PRICE, listing.url, ("eyes",)))
        elif price <= item.target:
            alerts.append(Alert(
                f"{item.name} at {_money(price)} (target {_money(item.target)})",
                listing.title, ntfy.AT_TARGET, listing.url, ("moneybag",),
            ))
        elif price <= near_limit:
            alerts.append(Alert(
                f"{item.name} at {_money(price)}, {_money(price - item.target)} over target",
                listing.title, ntfy.NEAR_TARGET, listing.url, ("chart_with_downwards_trend",),
            ))
    return alerts


def bestbuy_alerts(item: Item, listings: list[Listing], wl: Watchlist, state: State, now: datetime) -> list[Alert]:
    priced = [l for l in listings if l.price is not None and matches(item, l.title, wl.exclude)]
    if not priced:
        return []
    cheapest = min(priced, key=lambda l: l.price)
    price = cheapest.price
    prev = state.get("best#" + item.id) or {}
    prev_low = prev.get("low")
    prev_alerted = prev.get("alerted")

    alert = None
    if price <= item.target and (prev_alerted is None or price < prev_alerted):
        alert = Alert(
            f"{item.name} at {_money(price)} at Best Buy (target {_money(item.target)})",
            cheapest.title, ntfy.AT_TARGET, cheapest.url, ("moneybag",),
        )
    elif price <= item.target * (1 + wl.near_pct) and prev_low is not None and price < prev_low:
        alert = Alert(
            f"{item.name} new low: {_money(price)} at Best Buy",
            f"{cheapest.title}\nWas {_money(prev_low)}. {_money(price - item.target)} over target.",
            ntfy.NEAR_TARGET, cheapest.url, ("chart_with_downwards_trend",),
        )

    record = {"low": price, "url": cheapest.url, "at": now.isoformat()}
    if alert and alert.priority == ntfy.AT_TARGET:
        record["alerted"] = price
    elif prev_alerted is not None and price <= item.target:
        record["alerted"] = prev_alerted
    # Otherwise the price is back above target: drop "alerted" so the next drop alerts again.
    state.put("best#" + item.id, record)
    return [alert] if alert else []


SOURCE_LABELS = {"slickdeals": "Slickdeals", "bestbuy": "Best Buy"}

# A source that has failed on every fetch for this long gets one ntfy alert.
FAILING_ALERT_AFTER = timedelta(hours=3)
# The weekly note turns urgent if no check has succeeded for this long.
STALE_AFTER = timedelta(hours=6)

HEALTH_KEY = "health"


def run(
    wl: Watchlist,
    state: State,
    sender,
    slickdeals_search: SlickdealsSearch = slickdeals.search,
    bestbuy_search: BestBuySearch | None = None,
    now: datetime | None = None,
) -> dict:
    """Check every item. A failing source is logged and skipped. A source that
    keeps failing is reported to ntfy (and again when it recovers), and if every
    fetch fails the run raises so the Lambda also shows an error."""
    now = now or datetime.now(timezone.utc)
    sent, fetches, failures = 0, 0, 0
    source_results: dict[str, list[str | None]] = {}  # source -> error per fetch (None = ok)
    for item in wl.items:
        sources = [("slickdeals", slickdeals_search, slickdeals_alerts)]
        if bestbuy_search:
            sources.append(("bestbuy", bestbuy_search, bestbuy_alerts))
        for name, search, decide in sources:
            fetches += 1
            try:
                listings = search(item.query)
            except Exception as e:
                failures += 1
                source_results.setdefault(name, []).append(f"{type(e).__name__}: {e}")
                log.exception("fetch failed: %s for %s", name, item.id)
                continue
            source_results.setdefault(name, []).append(None)
            for alert in decide(item, listings, wl, state, now):
                sender.send(alert)
                sent += 1

    _update_health(state, sender, source_results, sent, now)
    if fetches and failures == fetches:
        raise RuntimeError(f"all {fetches} price fetches failed")
    return {"items": len(wl.items), "fetches": fetches, "failures": failures, "alerts": sent}


def _update_health(state: State, sender, source_results: dict, sent: int, now: datetime) -> None:
    health = state.get(HEALTH_KEY) or {}
    sources = health.get("sources", {})
    for name, errors in source_results.items():
        label = SOURCE_LABELS.get(name, name)
        record = sources.get(name, {})
        if all(errors):  # every fetch from this source failed
            since = record.get("failing_since") or now.isoformat()
            record = {"failing_since": since, "alerted": record.get("alerted", False), "error": errors[-1][:300]}
            if not record["alerted"] and now - datetime.fromisoformat(since) >= FAILING_ALERT_AFTER:
                sender.send(Alert(
                    f"Deal alert: {label} checks are failing",
                    f"Every {label} check has failed since {since[:16].replace('T', ' ')} UTC, "
                    f"so deals there can be missed.\nLast error: {record['error']}",
                    ntfy.AT_TARGET, _source_url(name), ("warning",),
                ))
                record["alerted"] = True
        else:
            if record.get("alerted"):
                sender.send(Alert(f"Deal alert: {label} checks are working again", "Back to normal.",
                                  ntfy.CHECK_PRICE, _source_url(name), ("white_check_mark",)))
            record = {}
        sources[name] = record
    health["sources"] = sources
    if any(e is None for errors in source_results.values() for e in errors):
        health["last_ok"] = now.isoformat()
    health["alerts_since_note"] = health.get("alerts_since_note", 0) + sent
    state.put(HEALTH_KEY, health)


def _source_url(name: str) -> str:
    return "https://www.bestbuy.com" if name == "bestbuy" else "https://slickdeals.net"


def weekly_note(wl: Watchlist, state: State, sender, now: datetime | None = None) -> dict:
    """A low-priority "still running" push, so silence never hides a broken checker."""
    now = now or datetime.now(timezone.utc)
    health = state.get(HEALTH_KEY) or {}
    last_ok = health.get("last_ok")
    count = health.get("alerts_since_note", 0)
    names = ", ".join(f"{i.name} ({_money(i.target)})" for i in wl.items)
    if last_ok and now - datetime.fromisoformat(last_ok) < STALE_AFTER:
        title = f"Deal alert is running: {count} alert{'s' if count != 1 else ''} this week"
        priority = ntfy.CHECK_PRICE
    else:
        when = f"since {last_ok[:16].replace('T', ' ')} UTC" if last_ok else "yet"
        title = f"Deal alert hasn't completed a check {when}"
        priority = ntfy.AT_TARGET
    sender.send(Alert(title, f"Watching: {names}", priority, "https://slickdeals.net", ("calendar",)))
    health["alerts_since_note"] = 0
    state.put(HEALTH_KEY, health)
    return {"note": title}


def bestbuy_searcher(api_key: str | None) -> BestBuySearch | None:
    if not api_key:
        return None
    return lambda query: bestbuy.search(query, api_key)
