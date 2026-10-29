"""What has already been seen or alerted, so you never get the same alert twice.

One DynamoDB table, key ``pk``:
- ``seen#<sha1 of url>``: a Slickdeals post already handled (expires after 45 days).
- ``best#<item id>``: lowest Best Buy price seen and the last price alerted on.
- ``health``: per-source failure tracking and the daily summary's counters and closest prices.
"""

from __future__ import annotations

import hashlib
import json
import time
from decimal import Decimal
from typing import Protocol

SEEN_TTL_SECONDS = 45 * 24 * 3600


class State(Protocol):
    def seen(self, url: str) -> bool: ...
    def mark_seen(self, url: str) -> None: ...
    def get(self, key: str) -> dict | None: ...
    def put(self, key: str, record: dict) -> None: ...


def _seen_key(url: str) -> str:
    return "seen#" + hashlib.sha1(url.encode()).hexdigest()


def _to_dynamo(value):
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _to_dynamo(v) for k, v in value.items()}
    return value


def _from_dynamo(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: _from_dynamo(v) for k, v in value.items()}
    return value


class DynamoState:
    def __init__(self, table_name: str, client=None):
        import boto3  # included in the Lambda runtime

        self.table = (client or boto3.resource("dynamodb")).Table(table_name)

    def seen(self, url: str) -> bool:
        return "Item" in self.table.get_item(Key={"pk": _seen_key(url)})

    def mark_seen(self, url: str) -> None:
        self.table.put_item(Item={"pk": _seen_key(url), "expires": int(time.time()) + SEEN_TTL_SECONDS})

    def get(self, key: str) -> dict | None:
        item = self.table.get_item(Key={"pk": key}).get("Item")
        if not item:
            return None
        return {k: _from_dynamo(v) for k, v in item.items() if k != "pk"}

    def put(self, key: str, record: dict) -> None:
        self.table.put_item(Item={"pk": key, **_to_dynamo(record)})


class MemoryState:
    """For tests and local dry runs."""

    def __init__(self):
        self.seen_urls: set[str] = set()
        self.records: dict[str, dict] = {}

    def seen(self, url: str) -> bool:
        return url in self.seen_urls

    def mark_seen(self, url: str) -> None:
        self.seen_urls.add(url)

    def get(self, key: str) -> dict | None:
        return self.records.get(key)

    def put(self, key: str, record: dict) -> None:
        self.records[key] = json.loads(json.dumps(record))  # a deep copy, like a real store
