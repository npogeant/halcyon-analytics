from __future__ import annotations

import bisect
from datetime import timedelta

import numpy as np

from .. import config
from ..dates import day_range
from ..rng import rng_for
from ..writer import write_text_lines

EVENT_TYPES = ["page_view", "add_to_cart", "checkout_started", "checkout_completed"]
EVENT_WEIGHTS = [0.70, 0.15, 0.08, 0.07]
PAGES = ["/home", "/pricing", "/products", "/blog", "/support", "/checkout"]


def generate(defects: dict, customers: dict, products: dict) -> dict:
    rng = rng_for(config.SEED, "web_events")

    order = sorted(
        range(len(customers["customer_ids"])), key=lambda i: customers["created_at"][i]
    )
    sorted_created_at = [customers["created_at"][i] for i in order]
    sorted_customer_ids = [customers["customer_ids"][i] for i in order]
    product_ids = np.array(products["product_ids"])

    days = day_range(config.START_DATE, config.END_DATE)
    n_days = len(days)
    total_written = 0

    for day_idx, day in enumerate(days):
        growth = day_idx / max(1, n_days - 1)
        base_volume = int(3_000 + growth * 8_000)
        n_events = int(base_volume * rng.uniform(0.85, 1.15))

        eligible_count = bisect.bisect_right(sorted_created_at, day)

        event_types = rng.choice(EVENT_TYPES, size=n_events, p=EVENT_WEIGHTS)
        is_anonymous = rng.random(n_events) < 0.3
        customer_idx = rng.integers(0, max(1, eligible_count), size=n_events)
        seconds_in_day = rng.integers(0, 86_400, size=n_events)
        session_nums = rng.integers(0, 5_000_000, size=n_events)
        is_naive = defects["naive_utc_timestamps"] and (rng.random(n_events) < 0.05)
        is_late = defects["late_web_events"] and (rng.random(n_events) < 0.02)
        late_offset_days = rng.integers(1, 4, size=n_events)
        page_choice = rng.choice(PAGES, size=n_events)
        product_choice = (
            rng.choice(product_ids, size=n_events) if len(product_ids) else None
        )

        lines = []
        for i in range(n_events):
            event_type = event_types[i]
            occurred_at = (
                day - timedelta(days=int(late_offset_days[i])) if is_late[i] else day
            )
            ts = f"{occurred_at.isoformat()}T{int(seconds_in_day[i]) // 3600:02d}:{(int(seconds_in_day[i]) // 60) % 60:02d}:{int(seconds_in_day[i]) % 60:02d}"
            if not is_naive[i]:
                ts += "Z"

            cust_json = (
                "null"
                if is_anonymous[i]
                else f'"{sorted_customer_ids[customer_idx[i]]}"'
            )
            has_product = event_type in (
                "add_to_cart",
                "checkout_started",
                "checkout_completed",
            )
            prod_json = (
                f'"{product_choice[i]}"'
                if has_product and product_choice is not None
                else "null"
            )

            event_id = f"evt_{day_idx:04d}_{i:07d}"
            session_id = f"ses_{session_nums[i]}"
            lines.append(
                f'{{"event_id": "{event_id}", "customer_id": {cust_json}, '
                f'"session_id": "{session_id}", "event_type": "{event_type}", '
                f'"event_at": "{ts}", "product_id": {prod_json}, "url": "{page_choice[i]}"}}'
            )

        write_text_lines(
            lines,
            f"{config.OUTPUT_DIR}/web_events/dt={day.isoformat()}/events.jsonl",
        )
        total_written += len(lines)

    return {"web_events": total_written, "days": n_days}
