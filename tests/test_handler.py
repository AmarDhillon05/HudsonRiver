"""The Lambda entry point routes the two scheduled events correctly."""

import pytest

from dealalert import check, handler, ntfy


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("TABLE_NAME", "t")
    monkeypatch.setenv("NTFY_TOPIC", "topic")
    monkeypatch.delenv("BESTBUY_API_KEY", raising=False)
    monkeypatch.setattr(handler, "DynamoState", lambda name: ("state", name))
    calls = []
    monkeypatch.setattr(check, "run", lambda wl, state, sender, bestbuy_search=None: calls.append(("run", bestbuy_search)) or {})
    monkeypatch.setattr(check, "daily_summary", lambda wl, state, sender: calls.append(("summary",)) or {})
    return calls


def test_scheduled_event_runs_the_check(env):
    handler.handler({"source": "aws.events"}, None)
    assert env == [("run", None)]


def test_daily_event_sends_the_summary(env):
    handler.handler({"task": "daily-summary"}, None)
    assert env == [("summary",)]


def test_ntfy_sender_posts_json(monkeypatch):
    sent = []
    monkeypatch.setattr(ntfy.http, "post_json", lambda url, body, headers: sent.append((url, body, headers)))
    ntfy.NtfySender("topic", "https://ntfy.example/").send(ntfy.Alert("t ™", "m", 4, "https://x", ("moneybag",)))
    url, body, headers = sent[0]
    assert url == "https://ntfy.example"
    assert body == {"topic": "topic", "title": "t ™", "message": "m", "priority": 4, "tags": ["moneybag"], "click": "https://x"}
    assert headers == {}
