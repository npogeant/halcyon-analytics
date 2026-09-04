from __future__ import annotations

import argparse
import logging

from . import relational, web_events

SOURCES = {
    "relational": relational,
    "web_events": web_events,
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Load the Halcyon raw layer: relational sources (dlt) and web_events (dlt)."
    )
    parser.add_argument(
        "--source",
        choices=list(SOURCES.keys()),
        help="run only this source (default: run all)",
    )
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="drop existing raw data and incremental state, then reload everything",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    targets = [args.source] if args.source else list(SOURCES.keys())
    for name in targets:
        info = SOURCES[name].run(full_refresh=args.full_refresh)
        print(info)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
