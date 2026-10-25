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
    assert state.get_best("x1")["low"] == 1690


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
