"""One pass over the watchlist: fetch, filter, decide, alert.

Alert rule: each laptop tracks the lowest price seen so far, starting at the
watchlist's ``start_at`` ($2,000). A matching, recent listing (new units only)
priced below that sends a high-priority alert and becomes the new lowest, so
each alert is a new low. A matching Slickdeals post with no price in its title
gets one low-priority "check price" alert.

Once a day ``daily_summary`` pushes what happened, even when nothing was
found: alerts sent, checks run, and each laptop's lowest and today's price.
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

Search = Callable[[str], list[Listing]]

SOURCE_LABELS = {"slickdeals": "Slickdeals", "bestbuy": "Best Buy"}

# A source that has failed on every fetch for this long gets one ntfy alert.
FAILING_ALERT_AFTER = timedelta(hours=3)
# The daily summary turns urgent if no check has succeeded for this long.
STALE_AFTER = timedelta(hours=6)

HEALTH_KEY = "health"


def _money(value: float) -> str:
    return f"${value:,.0f}" if value == int(value) else f"${value:,.2f}"


def _low_key(item: Item) -> str:
    return "low#" + item.id


def decide(item: Item, listings: list[Listing], wl: Watchlist, state: State, now: datetime) -> tuple[list[Alert], Listing | None]:
    """Alerts for one item from every source's listings this run, plus the
    cheapest current listing (for the daily summary)."""
    cutoff = now - timedelta(days=wl.max_post_age_days)
    current = [
        l for l in listings
        if matches(item, l.title, wl.exclude) and (l.posted is None or l.posted >= cutoff)
    ]
    alerts = []

    for l in current:
        if l.price is None and not state.seen(l.url):
            state.mark_seen(l.url)
            alerts.append(Alert(f"{item.name}: new deal posted", l.title, ntfy.LOW, l.url, ("eyes",)))

    priced = [l for l in current if l.price is not None]
    cheapest = min(priced, key=lambda l: l.price, default=None)
    if cheapest is None:
        return alerts, None

    low = state.get(_low_key(item))
    threshold = low["price"] if low else wl.start_for(item)
    if cheapest.price < threshold:
        where = SOURCE_LABELS.get(cheapest.source, cheapest.source)
        before = f"Previous low: {_money(threshold)}" if low else f"First price under {_money(threshold)}"
        alerts.append(Alert(
            f"{item.name}: new low {_money(cheapest.price)} at {where}",
            f"{cheapest.title}\n{before}",
            ntfy.HIGH, cheapest.url, ("moneybag",),
        ))
        state.put(_low_key(item), {
            "price": cheapest.price, "url": cheapest.url, "source": cheapest.source, "at": now.isoformat(),
        })
    return alerts, cheapest


def run(
    wl: Watchlist,
    state: State,
    sender,
    slickdeals_search: Search = slickdeals.search,
    bestbuy_search: Search | None = None,
    now: datetime | None = None,
) -> dict:
    """Check every item. A failing source is logged and skipped. A source that
    keeps failing is reported to ntfy (and again when it recovers), and if every
    fetch fails the run raises so the Lambda also shows an error."""
    now = now or datetime.now(timezone.utc)
    sent, fetches, failures = 0, 0, 0
    source_results: dict[str, list[str | None]] = {}  # source -> error per fetch (None = ok)
    closest: dict[str, Listing] = {}  # item id -> cheapest current matching listing
    sources = [("slickdeals", slickdeals_search)] + ([("bestbuy", bestbuy_search)] if bestbuy_search else [])
    # Items that share a query (both Blade 14s) fetch it once; None marks a failed fetch.
    fetched: dict[tuple[str, str], list[Listing] | None] = {}
    for item in wl.items:
        listings: list[Listing] = []
        for name, search in sources:
            key = (name, item.query)
            if key not in fetched:
                fetches += 1
                try:
                    fetched[key] = search(item.query)
                    source_results.setdefault(name, []).append(None)
                except Exception as e:
                    fetched[key] = None
                    failures += 1
                    source_results.setdefault(name, []).append(f"{type(e).__name__}: {e}")
                    log.exception("fetch failed: %s for %s", name, item.id)
            listings += fetched[key] or []
        alerts, cheapest = decide(item, listings, wl, state, now)
        if cheapest:
            closest[item.id] = cheapest
        for alert in alerts:
            sender.send(alert)
            sent += 1

    _update_health(state, sender, source_results, sent, closest, now)
    if fetches and failures == fetches:
        raise RuntimeError(f"all {fetches} price fetches failed")
    return {"items": len(wl.items), "fetches": fetches, "failures": failures, "alerts": sent}


def _update_health(state: State, sender, source_results: dict, sent: int, closest: dict, now: datetime) -> None:
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
                    ntfy.HIGH, _source_url(name), ("warning",),
                ))
                record["alerted"] = True
        else:
            if record.get("alerted"):
                sender.send(Alert(f"Deal alert: {label} checks are working again", "Back to normal.",
                                  ntfy.LOW, _source_url(name), ("white_check_mark",)))
            record = {}
        sources[name] = record
    health["sources"] = sources
    if any(e is None for errors in source_results.values() for e in errors):
        health["last_ok"] = now.isoformat()
    health["alerts_since_note"] = health.get("alerts_since_note", 0) + sent
    health["checks_since_note"] = health.get("checks_since_note", 0) + 1
    day = health.get("closest", {})
    for item_id, listing in closest.items():
        if item_id not in day or listing.price < day[item_id]["price"]:
            day[item_id] = {"price": listing.price, "url": listing.url, "source": listing.source}
    health["closest"] = day
    state.put(HEALTH_KEY, health)


def _source_url(name: str) -> str:
    return "https://www.bestbuy.com" if name == "bestbuy" else "https://slickdeals.net"


def daily_summary(wl: Watchlist, state: State, sender, now: datetime | None = None) -> dict:
    """Push once a day whatever happened, so you hear from it even with no deals:
    alerts sent, checks run, and each laptop's lowest so far and today's price.
    Urgent if no check has succeeded recently."""
    now = now or datetime.now(timezone.utc)
    health = state.get(HEALTH_KEY) or {}
    last_ok = health.get("last_ok")
    alerts = health.get("alerts_since_note", 0)
    checks = health.get("checks_since_note", 0)
    day = health.get("closest", {})

    lines = []
    best_gap, click = None, "https://slickdeals.net"
    for item in wl.items:
        low = state.get(_low_key(item))
        today = day.get(item.id)
        if low:
            when = datetime.fromisoformat(low["at"]).strftime("%b %-d")
            line = f"{item.name}: lowest {_money(low['price'])} ({SOURCE_LABELS.get(low.get('source'), '')}, {when})"
        else:
            line = f"{item.name}: nothing under {_money(wl.start_for(item))} yet"
        if today:
            line += f"; today {_money(today['price'])}"
            gap = today["price"] - (low["price"] if low else wl.start_for(item))
            if best_gap is None or gap < best_gap:
                best_gap, click = gap, today["url"]
        lines.append(line)

    if last_ok and now - datetime.fromisoformat(last_ok) < STALE_AFTER:
        if alerts:
            title = f"Deal alert: {alerts} alert{'s' if alerts != 1 else ''} today"
        else:
            title = "Deal alert: no new lows today"
        priority = ntfy.LOW
    else:
        when = f"since {last_ok[:16].replace('T', ' ')} UTC" if last_ok else "yet"
        title = f"Deal alert hasn't completed a check {when}"
        priority = ntfy.HIGH
    message = "\n".join(lines) + f"\nChecked {checks} time{'s' if checks != 1 else ''} since the last summary."
    sender.send(Alert(title, message, priority, click, ("calendar",)))

    health.update(alerts_since_note=0, checks_since_note=0, closest={})
    state.put(HEALTH_KEY, health)
    return {"summary": title}


def bestbuy_searcher(api_key: str | None) -> Search | None:
    if not api_key:
        return None
    return lambda query: bestbuy.search(query, api_key)
