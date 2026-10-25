"""Price sources. Each returns a list of ``Listing``s for one watchlist item."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Listing:
    source: str  # "slickdeals" or "bestbuy"
    title: str
    url: str
    price: float | None  # None when the price couldn't be read
    posted: datetime | None = None
    regular_price: float | None = None
