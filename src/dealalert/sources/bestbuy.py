"""Best Buy Products API: exact current prices. Free key from developer.bestbuy.com.

Optional: with no key configured this source is skipped.
"""

from __future__ import annotations

import json
import urllib.parse

from .. import http
from . import Listing

API_URL = (
    "https://api.bestbuy.com/v1/products({search}&condition=new)"
    "?apiKey={key}&format=json&pageSize=50&show=sku,name,salePrice,regularPrice,url"
)


def _search_clause(query: str) -> str:
    return "&".join("search=" + urllib.parse.quote(word) for word in query.split())


def parse(body: bytes) -> list[Listing]:
    products = json.loads(body).get("products", [])
    return [
        Listing("bestbuy", p["name"], p["url"], p.get("salePrice"), regular_price=p.get("regularPrice"))
        for p in products
        if p.get("name") and p.get("url")
    ]


def search(query: str, api_key: str) -> list[Listing]:
    url = API_URL.format(search=_search_clause(query), key=urllib.parse.quote(api_key))
    return parse(http.get(url))
