"""Slickdeals deal search, read through its public RSS feed (no key needed).

The search is fuzzy (a query for "x1 carbon gen 14" also returns chargers and
refurbished E15s), so every post is filtered with ``watchlist.matches`` later.
"""

from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from .. import http
from . import Listing

FEED_URL = "https://slickdeals.net/newsearch.php?searcharea=deals&searchin=first&rss=1&q={q}"

# Laptop prices only: ignore small amounts like "$50 off" or "$5.99 shipping".
MIN_PLAUSIBLE_PRICE = 300

_PRICE = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{2}))?")


# Amounts that are discounts, not prices: "$400 off", "Save $500", "$300 savings".
_DISCOUNT_AFTER = re.compile(r"\s*(?:off|discount|savings?|rebate|instant savings)\b", re.I)
_DISCOUNT_BEFORE = re.compile(r"(?:save|saving|savings of|extra|additional)\s*(?:up to\s*)?$", re.I)


def parse_price(title: str) -> float | None:
    """Lowest plausible laptop price in a deal title, e.g. "... $1,385" -> 1385.0."""
    prices = []
    for m in _PRICE.finditer(title):
        if _DISCOUNT_AFTER.match(title, m.end()) or _DISCOUNT_BEFORE.search(title[: m.start()]):
            continue
        whole, cents = m.groups()
        value = float(whole.replace(",", "")) + (int(cents) / 100 if cents else 0)
        if value >= MIN_PLAUSIBLE_PRICE:
            prices.append(value)
    return min(prices) if prices else None


def parse_feed(xml: bytes) -> list[Listing]:
    root = ET.fromstring(xml)
    listings = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        # Drop the RSS tracking params so the same post always has the same URL.
        link = link.split("?", 1)[0]
        posted = None
        if item.findtext("pubDate"):
            try:
                posted = parsedate_to_datetime(item.findtext("pubDate"))
            except (TypeError, ValueError):
                pass
        listings.append(Listing("slickdeals", title, link, parse_price(title), posted))
    return listings


def search(query: str) -> list[Listing]:
    return parse_feed(http.get(FEED_URL.format(q=urllib.parse.quote_plus(query))))
