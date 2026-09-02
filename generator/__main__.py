from __future__ import annotations

import argparse
import shutil
import time

from . import config
from .entities import (
    customers,
    marketing_spend,
    orders,
    payments,
    products,
    subscriptions,
    support_tickets,
    web_events,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate the Halcyon synthetic source system."
    )
    parser.add_argument(
        "--disable",
        nargs="*",
        default=[],
        choices=list(config.DEFECTS.keys()),
        help="defect names to turn off for this run",
    )
    args = parser.parse_args()

    defects = dict(config.DEFECTS)
    for name in args.disable:
        defects[name] = False

    shutil.rmtree(config.OUTPUT_DIR, ignore_errors=True)

    start = time.monotonic()
    stats = {}

    customers_data = customers.generate(defects)
    stats["customers"] = customers_data["stats"]

    products_data = products.generate(defects)
    stats["products"] = products_data["stats"]

    orders_data = orders.generate(defects, customers_data, products_data)
    stats["orders"] = orders_data["stats"]

    subscriptions_data = subscriptions.generate(defects, customers_data)
    stats["subscriptions"] = subscriptions_data["stats"]

    stats["payments"] = payments.generate(defects, orders_data, subscriptions_data)
    stats["web_events"] = web_events.generate(defects, customers_data, products_data)
    stats["support_tickets"] = support_tickets.generate(defects, customers_data)
    stats["marketing_spend"] = marketing_spend.generate(defects)

    elapsed = time.monotonic() - start

    print(
        f"Generated Halcyon synthetic source system (seed={config.SEED}) in {elapsed:.1f}s"
    )
    for entity, entity_stats in stats.items():
        print(f"  {entity}: {entity_stats}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
