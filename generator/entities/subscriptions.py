from __future__ import annotations

from datetime import timedelta

from .. import config
from ..rng import rng_for
from ..writer import write_parquet

PLANS = ["starter", "growth", "enterprise"]


def generate(defects: dict, customers: dict) -> dict:
    rng = rng_for(config.SEED, "subscriptions")

    customer_ids = customers["customer_ids"]
    created_at = customers["created_at"]
    n = len(customer_ids)

    subscriber_idx = [i for i in range(n) if rng.random() < 0.4]

    sub_id: list[str] = []
    sub_customer_id: list[str] = []
    sub_plan: list[str] = []
    sub_started_at: list[str] = []
    sub_status: list[str] = []
    sub_active_until: list[str] = []
    sub_updated_at: list[str] = []

    event_id: list[str] = []
    event_sub_id: list[str] = []
    event_type: list[str] = []
    event_at: list[str] = []

    for seq, idx in enumerate(subscriber_idx, start=1):
        sid = f"sub_{seq:06d}"
        plan = rng.choice(PLANS)
        started_at = created_at[idx] + timedelta(days=int(rng.integers(0, 30)))
        if started_at > config.END_DATE:
            continue

        last_event_at = [started_at]

        def emit(evt_type: str, at, sid=sid, last_event_at=last_event_at):
            event_id.append(f"{sid}_e{len(event_id) + 1}")
            event_sub_id.append(sid)
            event_type.append(evt_type)
            event_at.append(at.isoformat())
            last_event_at[0] = at

        cursor = started_at
        emit("created", cursor)
        status = "trialing"

        cursor = cursor + timedelta(days=14)
        if cursor <= config.END_DATE:
            emit("trial_ended", cursor)
            status = "active"

        for _ in range(int(rng.integers(0, 3))):
            cursor = cursor + timedelta(days=int(rng.integers(20, 120)))
            if cursor > config.END_DATE:
                break
            if rng.random() < 0.5:
                emit("upgraded", cursor)
            else:
                emit("downgraded", cursor)

        if status == "active" and rng.random() < 0.15:
            cursor = cursor + timedelta(days=int(rng.integers(10, 90)))
            if cursor <= config.END_DATE:
                emit("paused", cursor)
                status = "paused"
                cursor = cursor + timedelta(days=int(rng.integers(5, 60)))
                if cursor <= config.END_DATE and rng.random() < 0.7:
                    emit("resumed", cursor)
                    status = "active"

        active_until = config.END_DATE
        if rng.random() < 0.25:
            cursor = cursor + timedelta(days=int(rng.integers(10, 200)))
            if cursor <= config.END_DATE:
                emit("cancelled", cursor)
                status = "cancelled"
                active_until = cursor

        sub_id.append(sid)
        sub_customer_id.append(customer_ids[idx])
        sub_plan.append(plan)
        sub_started_at.append(started_at.isoformat())
        sub_status.append(status)
        sub_active_until.append(active_until.isoformat())
        sub_updated_at.append(last_event_at[0].isoformat())

    write_parquet(
        {
            "subscription_id": sub_id,
            "customer_id": sub_customer_id,
            "plan": sub_plan,
            "started_at": sub_started_at,
            "status": sub_status,
            "updated_at": sub_updated_at,
        },
        f"{config.OUTPUT_DIR}/subscriptions/subscriptions.parquet",
    )
    write_parquet(
        {
            "subscription_event_id": event_id,
            "subscription_id": event_sub_id,
            "event_type": event_type,
            "event_at": event_at,
        },
        f"{config.OUTPUT_DIR}/subscription_events/subscription_events.parquet",
    )

    return {
        "stats": {"subscriptions": len(sub_id), "subscription_events": len(event_id)},
        "subscription_id": sub_id,
        "customer_id": sub_customer_id,
        "started_at": sub_started_at,
        "active_until": sub_active_until,
    }
