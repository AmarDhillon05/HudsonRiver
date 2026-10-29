"""The watchlist: which laptops to look for and what price is worth an alert.

Edit ``watchlist.json`` next to this file and redeploy. Each item's ``match`` is
a list of groups; a listing title matches when it contains at least one term
from every group. Titles containing any global ``exclude`` term never match.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PATH = Path(__file__).with_name("watchlist.json")


@dataclass(frozen=True)
class Item:
    id: str
    name: str
    target: float
    query: str
    match: list[list[str]]


@dataclass(frozen=True)
class Watchlist:
    items: list[Item]
    exclude: list[str] = field(default_factory=list)
    near_pct: float = 0.10
    max_post_age_days: float = 3


def load(path: Path = DEFAULT_PATH) -> Watchlist:
    raw = json.loads(path.read_text())
    items = [Item(**i) for i in raw["items"]]
    ids = [i.id for i in items]
    if len(ids) != len(set(ids)):
        raise ValueError("watchlist item ids must be unique")
    return Watchlist(
        items=items,
        exclude=raw.get("exclude", []),
        near_pct=raw.get("near_pct", 0.10),
        max_post_age_days=raw.get("max_post_age_days", 3),
    )


def _normalize(text: str) -> str:
    """Lowercase, collapse spaces, and spell generations one way: "14th Gen",
    "Gen14", "Generation 14" and "G14" all become "gen 14" (so match on that)."""
    text = re.sub(r"\s+", " ", text.lower())
    text = re.sub(r"(?<![a-z0-9])(\d{1,2})(?:st|nd|rd|th) gen(?:eration)?(?![a-z0-9])", r"gen \1", text)
    text = re.sub(r"(?<![a-z0-9])gen(?:eration)? ?(\d{1,2})(?![0-9])", r"gen \1", text)
    return text


def _contains(text: str, term: str) -> bool:
    # Word boundaries so "g6" doesn't match "g60" and "used" doesn't match "focused".
    return re.search(r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?![a-z0-9])", text) is not None


def matches(item: Item, title: str, exclude: list[str]) -> bool:
    text = _normalize(title)
    if any(_contains(text, term) for term in exclude):
        return False
    return all(any(_contains(text, term) for term in group) for group in item.match)
