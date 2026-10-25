"""Run one check locally against the real feeds, without AWS.

    PYTHONPATH=src python -m dealalert.cli               # print alerts, send nothing
    PYTHONPATH=src python -m dealalert.cli --any-age     # include old posts too
    PYTHONPATH=src python -m dealalert.cli --ntfy TOPIC  # actually push to ntfy
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import os

from . import check, watchlist
from .ntfy import ConsoleSender, NtfySender
from .state import MemoryState


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ntfy", metavar="TOPIC", help="push to this ntfy topic instead of printing")
    parser.add_argument("--any-age", action="store_true", help="ignore max_post_age_days")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    wl = watchlist.load()
    if args.any_age:
        wl = dataclasses.replace(wl, max_post_age_days=10_000)
    sender = NtfySender(args.ntfy) if args.ntfy else ConsoleSender()
    result = check.run(wl, MemoryState(), sender, bestbuy_search=check.bestbuy_searcher(os.environ.get("BESTBUY_API_KEY")))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
