from __future__ import annotations

import argparse

from . import relational


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Load the Halcyon relational sources into the raw DuckDB schema."
    )
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="drop existing raw data and incremental state, then reload everything",
    )
    args = parser.parse_args()

    info = relational.run(full_refresh=args.full_refresh)
    print(info)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
