"""What has already been seen or alerted, so you never get the same alert twice.

One DynamoDB table, key ``pk``:
- ``seen#<sha1 of url>``: a Slickdeals post already handled (expires after 45 days).
- ``best#<item id>``: lowest Best Buy price seen and the last price alerted on.
"""

from __future__ import annotations

import hashlib
import time
from decimal import Decimal
from typing import Protocol

SEEN_TTL_SECONDS = 45 * 24 * 3600


class State(Protocol):
    def seen(self, url: str) -> bool: ...
    def mark_seen(self, url: str) -> None: ...
    def get_best(self, item_id: str) -> dict | None: ...
    def put_best(self, item_id: str, record: dict) -> None: ...


def _seen_key(url: str) -> str:
    return "seen#" + hashlib.sha1(url.encode()).hexdigest()


def _to_dynamo(value):
    return Decimal(str(value)) if isinstance(value, float) else value


def _from_dynamo(value):
    return float(value) if isinstance(value, Decimal) else value


class DynamoState:
    def __init__(self, table_name: str, client=None):
        import boto3  # included in the Lambda runtime

        self.table = (client or boto3.resource("dynamodb")).Table(table_name)

    def seen(self, url: str) -> bool:
        return "Item" in self.table.get_item(Key={"pk": _seen_key(url)})

    def mark_seen(self, url: str) -> None:
        self.table.put_item(Item={"pk": _seen_key(url), "expires": int(time.time()) + SEEN_TTL_SECONDS})

    def get_best(self, item_id: str) -> dict | None:
        item = self.table.get_item(Key={"pk": "best#" + item_id}).get("Item")
        if not item:
            return None
        return {k: _from_dynamo(v) for k, v in item.items() if k != "pk"}

    def put_best(self, item_id: str, record: dict) -> None:
        self.table.put_item(Item={"pk": "best#" + item_id, **{k: _to_dynamo(v) for k, v in record.items()}})


class MemoryState:
    """For tests and local dry runs."""

    def __init__(self):
        self.seen_urls: set[str] = set()
        self.best: dict[str, dict] = {}

    def seen(self, url: str) -> bool:
        return url in self.seen_urls

    def mark_seen(self, url: str) -> None:
        self.seen_urls.add(url)

    def get_best(self, item_id: str) -> dict | None:
        return self.best.get(item_id)

    def put_best(self, item_id: str, record: dict) -> None:
        self.best[item_id] = dict(record)
