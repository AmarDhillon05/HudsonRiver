"""Lambda entry point, run on a schedule by EventBridge."""

from __future__ import annotations

import json
import logging
import os

from . import check, watchlist
from .ntfy import NtfySender
from .state import DynamoState

logging.getLogger().setLevel(logging.INFO)


def handler(event, context):
    result = check.run(
        watchlist.load(),
        DynamoState(os.environ["TABLE_NAME"]),
        NtfySender(
            os.environ["NTFY_TOPIC"],
            os.environ.get("NTFY_SERVER", "https://ntfy.sh"),
            os.environ.get("NTFY_TOKEN") or None,
        ),
        bestbuy_search=check.bestbuy_searcher(os.environ.get("BESTBUY_API_KEY")),
    )
    logging.info("check finished: %s", json.dumps(result))
    return result
