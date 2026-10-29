"""Lambda entry point, run on two EventBridge schedules: the price check, and a
weekly "still running" note (event ``{"task": "weekly-note"}``)."""

from __future__ import annotations

import json
import logging
import os

from . import check, watchlist
from .ntfy import NtfySender
from .state import DynamoState

logging.getLogger().setLevel(logging.INFO)


def handler(event, context):
    wl = watchlist.load()
    state = DynamoState(os.environ["TABLE_NAME"])
    sender = NtfySender(
        os.environ["NTFY_TOPIC"],
        os.environ.get("NTFY_SERVER", "https://ntfy.sh"),
        os.environ.get("NTFY_TOKEN") or None,
    )
    if (event or {}).get("task") == "weekly-note":
        result = check.weekly_note(wl, state, sender)
    else:
        result = check.run(wl, state, sender, bestbuy_search=check.bestbuy_searcher(os.environ.get("BESTBUY_API_KEY")))
    logging.info("finished: %s", json.dumps(result))
    return result
