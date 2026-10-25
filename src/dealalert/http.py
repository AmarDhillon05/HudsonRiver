"""Tiny stdlib HTTP helpers, so the Lambda ships with no dependencies."""

from __future__ import annotations

import json
import urllib.request

USER_AGENT = "Mozilla/5.0 (compatible; laptop-deal-alert/1.0)"
TIMEOUT = 15


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def post_json(url: str, body: dict, headers: dict | None = None) -> None:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        resp.read()
