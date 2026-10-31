from datetime import datetime, timedelta, timezone

import pytest

from dealalert import check, ntfy
from dealalert.ntfy import ConsoleSender
from dealalert.sources import Listing
from dealalert.state import MemoryState
from dealalert.watchlist import Item, Watchlist

NOW = datetime(2026, 10, 25, 20, 0, tzinfo=timezone.utc)
X1 = Item("x1", "X1 Carbon Gen 14", "x1 carbon gen 14", [["x1 carbon"], ["gen 14"]])
WL = Watchlist(items=[X1], exclude=["refurb"], start_at=2000, max_post_age_days=3)


def post(title, price, url="https://slickdeals.net/f/1", age_days=0.5):
    return Listing("slickdeals", title, url, price, NOW - timedelta(days=age_days))


def bb(price, url="https://bestbuy.com/x1"):
    return Listing("bestbuy", "Lenovo ThinkPad X1 Carbon Gen 14", url, price)


def run(slick=(), best=None, state=None, wl=WL, now=NOW):
    sender = ConsoleSender()
    state = state or MemoryState()
    result = check.run(
        wl, state, sender,
        slickdeals_search=lambda q: list(slick),
        bestbuy_search=(lambda q: list(best)) if best is not None else None,
        now=now,
    )
    return sender.sent, state, result


# --- lowest price seen so far ---------------------------------------------

def test_first_price_under_start_alerts_and_sets_the_low():
    sent, state, _ = run([post("X1 Carbon Gen 14 $1,899", 1899)])
    assert [a.title for a in sent] == ["X1 Carbon Gen 14: new low $1,899 at Slickdeals"]
    assert sent[0].priority == ntfy.HIGH and "First price under $2,000" in sent[0].message
    assert state.get("low#x1")["price"] == 1899


def test_nothing_at_or_above_start_alerts():
    sent, state, _ = run([post("X1 Carbon Gen 14 $2,000", 2000), post("X1 Carbon Gen 14 $2,299", 2299, "https://sd/b")])
    assert sent == [] and state.get("low#x1") is None


def test_only_lower_prices_alert_after_that():
    state = MemoryState()
    run([post("X1 Carbon Gen 14 $1,799", 1799, "https://sd/a")], state=state)
    same, _, _ = run([post("X1 Carbon Gen 14 $1,799", 1799, "https://sd/b")], state=state)
    higher, _, _ = run([post("X1 Carbon Gen 14 $1,850", 1850, "https://sd/c")], state=state)
    lower, _, _ = run([post("X1 Carbon Gen 14 $1,649", 1649, "https://sd/d")], state=state)
    assert same == [] and higher == []
    assert [a.title for a in lower] == ["X1 Carbon Gen 14: new low $1,649 at Slickdeals"]
    assert "Previous low: $1,799" in lower[0].message
    assert state.get("low#x1")["price"] == 1649


def test_the_same_post_never_alerts_twice():
    state = MemoryState()
    first, _, _ = run([post("X1 Carbon Gen 14 $1,499", 1499)], state=state)
    again, _, _ = run([post("X1 Carbon Gen 14 $1,499", 1499)], state=state)
    assert len(first) == 1 and again == []


def test_one_alert_per_run_for_the_cheapest_across_sources():
    sent, state, _ = run([post("X1 Carbon Gen 14 $1,750", 1750, "https://sd/a"),
                          post("X1 Carbon Gen 14 $1,690", 1690, "https://sd/b")], best=[bb(1720)])
    assert [a.url for a in sent] == ["https://sd/b"]
    sent, _, _ = run([], best=[bb(1599)], state=state)
    assert [a.title for a in sent] == ["X1 Carbon Gen 14: new low $1,599 at Best Buy"]


def test_per_item_start_overrides_start_at():
    cheap = Item("x1", "X1 Carbon Gen 14", "q", [["x1 carbon"]], start=1500)
    wl = Watchlist(items=[cheap], start_at=2000)
    sent, _, _ = run([post("X1 Carbon $1,599", 1599)], wl=wl)
    assert sent == []
    sent, _, _ = run([post("X1 Carbon $1,449", 1449)], wl=wl)
    assert "First price under $1,500" in sent[0].message


def test_skips_old_unmatched_and_excluded():
    sent, _, _ = run([
        post("X1 Carbon Gen 14 $1,299", 1299, "https://sd/old", age_days=10),
        post("X1 Carbon Gen 13 $1,299", 1299, "https://sd/g13"),
        post("Refurb X1 Carbon Gen 14 $999", 999, "https://sd/refurb"),
    ])
    assert sent == []


def test_post_without_a_price_alerts_once_at_low_priority():
    state = MemoryState()
    first, _, _ = run([post("X1 Carbon Gen 14 deal, see thread", None)], state=state)
    again, _, _ = run([post("X1 Carbon Gen 14 deal, see thread", None)], state=state)
    assert [a.priority for a in first] == [ntfy.LOW] and again == []


def test_items_sharing_a_query_fetch_it_once():
    a = Item("a", "Blade 14 RTX 5070", "blade 14", [["blade 14"], ["5070"]])
    b = Item("b", "Blade 14 RTX 5060", "blade 14", [["blade 14"], ["5060"]])
    wl = Watchlist(items=[a, b])
    calls = []

    def search(q):
        calls.append(q)
        return [post("Razer Blade 14 RTX 5060 $1,549", 1549, "https://sd/5060")]

    sender = ConsoleSender()
    result = check.run(wl, MemoryState(), sender, slickdeals_search=search, now=NOW)
    assert calls == ["blade 14"] and result["fetches"] == 1
    assert [x.title for x in sender.sent] == ["Blade 14 RTX 5060: new low $1,549 at Slickdeals"]


# --- failures ----------------------------------------------------------------

def broken(q):
    raise OSError("HTTP 403 Forbidden")


def ok_slick(q):
    return []


def check_at(state, sender, when, slick):
    try:
        check.run(WL, state, sender, slickdeals_search=slick, now=when)
    except RuntimeError:
        pass  # every fetch failed; expected while the source is down


def test_one_failing_source_does_not_stop_the_other():
    sender = ConsoleSender()
    result = check.run(WL, MemoryState(), sender, slickdeals_search=broken, bestbuy_search=lambda q: [bb(1500)], now=NOW)
    assert result["failures"] == 1 and len(sender.sent) == 1


def test_all_sources_failing_raises():
    with pytest.raises(RuntimeError):
        check.run(WL, MemoryState(), ConsoleSender(), slickdeals_search=broken, now=NOW)


def test_a_failed_shared_query_counts_once():
    wl = Watchlist(items=[Item("a", "A", "same", [["a"]]), Item("b", "B", "same", [["b"]])])
    with pytest.raises(RuntimeError, match="all 1 price fetches failed"):
        check.run(wl, MemoryState(), ConsoleSender(), slickdeals_search=broken, now=NOW)


def test_failing_source_alerts_once_after_three_hours_then_on_recovery():
    state, sender = MemoryState(), ConsoleSender()
    for minutes in (0, 30, 120, 150):
        check_at(state, sender, NOW + timedelta(minutes=minutes), broken)
    assert sender.sent == []  # under 3 hours: stay quiet, it may be a blip
    check_at(state, sender, NOW + timedelta(hours=3), broken)
    check_at(state, sender, NOW + timedelta(hours=4), broken)
    assert [a.title for a in sender.sent] == ["Deal alert: Slickdeals checks are failing"]
    assert sender.sent[0].priority == ntfy.HIGH and "403" in sender.sent[0].message
    check_at(state, sender, NOW + timedelta(hours=5), ok_slick)
    check_at(state, sender, NOW + timedelta(hours=6), ok_slick)
    assert [a.title for a in sender.sent][1:] == ["Deal alert: Slickdeals checks are working again"]


def test_a_blip_resets_the_failure_clock():
    state, sender = MemoryState(), ConsoleSender()
    check_at(state, sender, NOW, broken)
    check_at(state, sender, NOW + timedelta(hours=2), ok_slick)
    check_at(state, sender, NOW + timedelta(hours=4), broken)
    check_at(state, sender, NOW + timedelta(hours=5), broken)
    assert sender.sent == []


# --- daily summary -------------------------------------------------------------

def test_daily_summary_shows_lowest_and_today():
    state = MemoryState()
    run([post("X1 Carbon Gen 14 $1,649", 1649, "https://sd/low")], state=state)
    run([post("X1 Carbon Gen 14 $1,749", 1749, "https://sd/today")], state=state, now=NOW + timedelta(hours=1))
    sender = ConsoleSender()
    check.daily_summary(WL, state, sender, now=NOW + timedelta(hours=2))
    [note] = sender.sent
    assert note.title == "Deal alert: 1 alert today"
    assert "X1 Carbon Gen 14: lowest $1,649 (Slickdeals, Oct 25); today $1,649" in note.message
    assert "Checked 2 times since the last summary." in note.message


def test_daily_summary_with_nothing_found():
    state = MemoryState()
    run([], state=state)
    sender = ConsoleSender()
    check.daily_summary(WL, state, sender, now=NOW + timedelta(hours=1))
    [note] = sender.sent
    assert note.title == "Deal alert: no new lows today"
    assert note.priority == ntfy.LOW
    assert "X1 Carbon Gen 14: nothing under $2,000 yet" in note.message
    assert "Checked 1 time since" in note.message


def test_daily_summary_resets_its_counters():
    state = MemoryState()
    run([post("X1 Carbon Gen 14 $1,499", 1499)], state=state)
    sender = ConsoleSender()
    check.daily_summary(WL, state, sender, now=NOW + timedelta(hours=1))
    run([], state=state)
    check.daily_summary(WL, state, sender, now=NOW + timedelta(hours=2))
    assert sender.sent[1].title == "Deal alert: no new lows today"
    first_line = sender.sent[1].message.split("\n")[0]
    assert "lowest $1,499" in first_line and "today" not in first_line


def test_daily_summary_is_urgent_when_checks_stopped():
    state = MemoryState()
    run([], state=state)
    sender = ConsoleSender()
    check.daily_summary(WL, state, sender, now=NOW + timedelta(days=2))
    assert sender.sent[0].priority == ntfy.HIGH
    assert sender.sent[0].title.startswith("Deal alert hasn't completed a check since 2026-10-25 20:00")
    fresh = ConsoleSender()
    check.daily_summary(WL, MemoryState(), fresh, now=NOW)
    assert fresh.sent[0].title == "Deal alert hasn't completed a check yet"
