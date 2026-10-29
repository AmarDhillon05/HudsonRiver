from datetime import datetime, timedelta, timezone

import pytest

from dealalert import check, ntfy
from dealalert.ntfy import ConsoleSender
from dealalert.sources import Listing
from dealalert.state import MemoryState
from dealalert.watchlist import Item, Watchlist

NOW = datetime(2026, 10, 25, 20, 0, tzinfo=timezone.utc)
X1 = Item("x1", "X1 Carbon Gen 14", 1600, "x1 carbon gen 14", [["x1 carbon"], ["gen 14"]])
WL = Watchlist(items=[X1], exclude=["refurb"], near_pct=0.10, max_post_age_days=3)


def post(title, price, url="https://slickdeals.net/f/1", age_days=0.5):
    return Listing("slickdeals", title, url, price, NOW - timedelta(days=age_days))


def bb(price, url="https://bestbuy.com/x1"):
    return Listing("bestbuy", "Lenovo ThinkPad X1 Carbon Gen 14", url, price)


def run(slick=(), best=None, state=None):
    sender = ConsoleSender()
    state = state or MemoryState()
    result = check.run(
        WL, state, sender,
        slickdeals_search=lambda q: list(slick),
        bestbuy_search=(lambda q: list(best)) if best is not None else None,
        now=NOW,
    )
    return sender.sent, state, result


def test_slickdeals_priorities():
    sent, _, _ = run([
        post("X1 Carbon Gen 14 $1,499", 1499, "https://sd/a"),
        post("X1 Carbon Gen 14 $1,690", 1690, "https://sd/b"),
        post("X1 Carbon Gen 14 $1,900", 1900, "https://sd/c"),
        post("X1 Carbon Gen 14 deal", None, "https://sd/d"),
    ])
    assert [a.priority for a in sent] == [ntfy.AT_TARGET, ntfy.NEAR_TARGET, ntfy.CHECK_PRICE]
    assert sent[0].url == "https://sd/a"
    assert "$90 over target" in sent[1].title


def test_slickdeals_alerts_each_post_once():
    state = MemoryState()
    first, _, _ = run([post("X1 Carbon Gen 14 $1,499", 1499)], state=state)
    again, _, _ = run([post("X1 Carbon Gen 14 $1,499", 1499)], state=state)
    assert len(first) == 1 and again == []


def test_slickdeals_skips_old_unmatched_and_excluded():
    sent, _, _ = run([
        post("X1 Carbon Gen 14 $1,299", 1299, "https://sd/old", age_days=10),
        post("X1 Carbon Gen 13 $1,299", 1299, "https://sd/g13"),
        post("Refurb X1 Carbon Gen 14 $999", 999, "https://sd/refurb"),
    ])
    assert sent == []


def test_bestbuy_alerts_at_target_once_then_on_further_drop():
    state = MemoryState()
    s1, _, _ = run(best=[bb(1700), bb(1599, "https://bestbuy.com/cheap")], state=state)
    s2, _, _ = run(best=[bb(1599)], state=state)
    s3, _, _ = run(best=[bb(1549)], state=state)
    assert [a.priority for a in s1] == [ntfy.AT_TARGET]
    assert s1[0].url == "https://bestbuy.com/cheap"
    assert s2 == []
    assert [a.priority for a in s3] == [ntfy.AT_TARGET]


def test_bestbuy_realerts_after_price_goes_back_up():
    state = MemoryState()
    run(best=[bb(1599)], state=state)
    run(best=[bb(1999)], state=state)
    again, _, _ = run(best=[bb(1599)], state=state)
    assert [a.priority for a in again] == [ntfy.AT_TARGET]


def test_bestbuy_near_target_new_low():
    state = MemoryState()
    first, _, _ = run(best=[bb(1750)], state=state)
    lower, _, _ = run(best=[bb(1690)], state=state)
    assert first == []  # no previous low to compare against
    assert [a.priority for a in lower] == [ntfy.NEAR_TARGET]
    assert state.get("best#x1")["low"] == 1690


def test_one_failing_source_does_not_stop_the_other():
    def broken(q):
        raise OSError("blocked")

    sender = ConsoleSender()
    result = check.run(WL, MemoryState(), sender, slickdeals_search=broken, bestbuy_search=lambda q: [bb(1500)], now=NOW)
    assert result["failures"] == 1 and len(sender.sent) == 1


def test_all_sources_failing_raises():
    def broken(q):
        raise OSError("blocked")

    with pytest.raises(RuntimeError):
        check.run(WL, MemoryState(), ConsoleSender(), slickdeals_search=broken, now=NOW)


def broken(q):
    raise OSError("HTTP 403 Forbidden")


def ok_slick(q):
    return []


def check_at(state, sender, when, slick):
    try:
        check.run(WL, state, sender, slickdeals_search=slick, now=when)
    except RuntimeError:
        pass  # every fetch failed; expected while the source is down


def test_failing_source_alerts_once_after_three_hours_then_on_recovery():
    state, sender = MemoryState(), ConsoleSender()
    for minutes in (0, 30, 120, 150):
        check_at(state, sender, NOW + timedelta(minutes=minutes), broken)
    assert sender.sent == []  # under 3 hours: stay quiet, it may be a blip
    check_at(state, sender, NOW + timedelta(hours=3), broken)
    check_at(state, sender, NOW + timedelta(hours=4), broken)
    assert [a.title for a in sender.sent] == ["Deal alert: Slickdeals checks are failing"]
    assert sender.sent[0].priority == ntfy.AT_TARGET and "403" in sender.sent[0].message
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


def test_daily_summary_with_no_deals_still_pushes_closest_prices():
    state = MemoryState()
    # Seen before (no new alert) but still the closest current price; one old post ignored.
    state.mark_seen("https://sd/near")
    run([post("X1 Carbon Gen 14 $1,749", 1749, "https://sd/near"),
         post("X1 Carbon Gen 14 $1,299", 1299, "https://sd/old", age_days=10)], state=state)
    run([], state=state)
    sender = ConsoleSender()
    check.daily_summary(WL, state, sender, now=NOW + timedelta(hours=1))
    [note] = sender.sent
    assert note.title == "Deal alert: no deals today"
    assert note.priority == ntfy.CHECK_PRICE
    assert "X1 Carbon Gen 14: $1,749 at Slickdeals, $149 over (target $1,600)" in note.message
    assert "Checked 2 times since the last summary." in note.message
    assert note.url == "https://sd/near"


def test_daily_summary_counts_alerts_and_resets():
    state = MemoryState()
    run([post("X1 Carbon Gen 14 $1,499", 1499)], state=state)
    sender = ConsoleSender()
    check.daily_summary(WL, state, sender, now=NOW + timedelta(hours=1))
    assert sender.sent[0].title == "Deal alert: 1 alert today"
    assert "AT TARGET" in sender.sent[0].message
    run([], state=state, )
    check.daily_summary(WL, state, sender, now=NOW + timedelta(hours=2))
    assert sender.sent[1].title == "Deal alert: no deals today"
    assert "X1 Carbon Gen 14: nothing posted (target $1,600)" in sender.sent[1].message
    assert "Checked 1 time since" in sender.sent[1].message


def test_daily_summary_keeps_the_cheapest_across_runs_and_sources():
    state = MemoryState()
    run([post("X1 Carbon Gen 14 $1,750", 1750, "https://sd/a")], best=[bb(1720)], state=state)
    run([post("X1 Carbon Gen 14 $1,690", 1690, "https://sd/b")], best=[bb(1720)], state=state)
    sender = ConsoleSender()
    check.daily_summary(WL, state, sender, now=NOW + timedelta(hours=1))
    assert "$1,690 at Slickdeals" in sender.sent[0].message


def test_daily_summary_is_urgent_when_checks_stopped():
    state = MemoryState()
    run([], state=state)
    sender = ConsoleSender()
    check.daily_summary(WL, state, sender, now=NOW + timedelta(days=2))
    assert sender.sent[0].priority == ntfy.AT_TARGET
    assert sender.sent[0].title.startswith("Deal alert hasn't completed a check since 2026-10-25 20:00")
    fresh = ConsoleSender()
    check.daily_summary(WL, MemoryState(), fresh, now=NOW)
    assert fresh.sent[0].title == "Deal alert hasn't completed a check yet"
