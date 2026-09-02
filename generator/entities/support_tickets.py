from __future__ import annotations

from datetime import timedelta

from .. import config
from ..rng import rng_for
from ..writer import write_text_lines

STATUS_VARIANTS = [
    "Open",
    "open",
    "OPEN",
    "Closed",
    "closed",
    "Resolved",
    "resolved",
    "Pending",
    "pending",
    "In Progress",
    "in progress",
]
SUBJECTS = [
    "Cannot log in",
    "Billing question",
    "Feature request",
    "Refund status",
    "Integration broken",
    "Data export issue",
    "Slow dashboard",
    "Cancel subscription",
]


def generate(defects: dict, customers: dict) -> dict:
    rng = rng_for(config.SEED, "support_tickets")

    customer_ids = customers["customer_ids"]
    created_at = customers["created_at"]

    n_tickets = 3_000
    lines = []
    for i in range(n_tickets):
        customer_idx = int(rng.integers(0, len(customer_ids)))
        earliest = created_at[customer_idx]
        remaining = max(1, (config.END_DATE - earliest).days)
        ticket_date = earliest + timedelta(days=int(rng.integers(0, remaining)))

        subject = rng.choice(SUBJECTS)
        status = rng.choice(STATUS_VARIANTS)
        line = f"tkt_{i + 1:05d},{customer_ids[customer_idx]},{subject},{status},{ticket_date.isoformat()}"

        # Hand-maintained export: ~1% of rows carry a stray trailing comma.
        if rng.random() < 0.01:
            line += ","
        lines.append(line)

    write_text_lines(
        lines,
        f"{config.OUTPUT_DIR}/support_tickets/support_tickets.csv",
        header="ticket_id,customer_id,subject,status,created_at",
    )

    return {"support_tickets": n_tickets}
