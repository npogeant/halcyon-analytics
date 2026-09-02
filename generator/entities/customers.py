from __future__ import annotations

import hashlib
from datetime import timedelta

import numpy as np
from faker import Faker

from .. import config
from ..dates import month_ends
from ..rng import rng_for
from ..writer import write_parquet


def _consent_flag(customer_id: str) -> bool:
    # Deterministic, independent of any RNG stream: whether a customer had
    # already given consent by the time the `consent_flag` column was added.
    return int(hashlib.sha256(customer_id.encode()).hexdigest(), 16) % 2 == 0


def generate(defects: dict) -> dict:
    rng = rng_for(config.SEED, "customers")
    fake = Faker()
    Faker.seed(config.SEED)

    n = config.N_CUSTOMERS
    span_days = (config.END_DATE - config.START_DATE).days
    customer_ids = [f"cus_{i + 1:05d}" for i in range(n)]
    created_offsets = rng.integers(0, span_days, size=n)
    created_at = [
        config.START_DATE + timedelta(days=int(created_offsets[i])) for i in range(n)
    ]

    country = rng.choice(config.COUNTRIES, size=n).tolist()
    segment = rng.choice(config.MARKETING_SEGMENTS, size=n).tolist()
    tier = rng.choice(config.PLAN_TIERS, size=n).tolist()
    emails = [fake.unique.email() for _ in range(n)]

    # A quarter of customers change 1-3 attributes at some point after signup.
    n_changes = np.minimum(rng.poisson(lam=0.4, size=n), 3)
    changes = []
    for idx in range(n):
        for _ in range(int(n_changes[idx])):
            field = rng.choice(["country", "marketing_segment", "plan_tier"])
            days_after = rng.integers(30, max(31, span_days - created_offsets[idx]))
            effective_date = created_at[idx] + timedelta(days=int(days_after))
            if effective_date > config.END_DATE:
                continue
            if field == "country":
                new_value = rng.choice(
                    [c for c in config.COUNTRIES if c != country[idx]]
                )
            elif field == "marketing_segment":
                new_value = rng.choice(
                    [s for s in config.MARKETING_SEGMENTS if s != segment[idx]]
                )
            else:
                new_value = rng.choice([t for t in config.PLAN_TIERS if t != tier[idx]])
            changes.append((effective_date, idx, field, new_value))
    changes.sort(key=lambda c: c[0])

    state_country = list(country)
    state_segment = list(segment)
    state_tier = list(tier)

    months = month_ends(config.START_DATE, config.END_DATE)
    change_ptr = 0
    row_count = 0
    for month_end in months:
        while change_ptr < len(changes) and changes[change_ptr][0] <= month_end:
            _, idx, field, new_value = changes[change_ptr]
            if field == "country":
                state_country[idx] = new_value
            elif field == "marketing_segment":
                state_segment[idx] = new_value
            else:
                state_tier[idx] = new_value
            change_ptr += 1

        present = [i for i in range(n) if created_at[i] <= month_end]
        if not present:
            continue
        row_count += len(present)

        post_schema_change = (
            defects["schema_change"] and month_end >= config.SCHEMA_CHANGE_DATE
        )
        columns = {
            "customer_id": [customer_ids[i] for i in present],
            "email": [emails[i] for i in present],
            "country": [state_country[i] for i in present],
            "plan_tier": [state_tier[i] for i in present],
            "created_at": [created_at[i].isoformat() for i in present],
        }
        if post_schema_change:
            columns["segment"] = [state_segment[i] for i in present]
            columns["consent_flag"] = [_consent_flag(customer_ids[i]) for i in present]
        else:
            columns["marketing_segment"] = [state_segment[i] for i in present]

        write_parquet(
            columns,
            f"{config.OUTPUT_DIR}/customers/customers_{month_end.strftime('%Y_%m')}.parquet",
        )

    return {
        "stats": {
            "customers": n,
            "customer_snapshot_rows": row_count,
            "months": len(months),
        },
        "customer_ids": customer_ids,
        "created_at": created_at,
    }
