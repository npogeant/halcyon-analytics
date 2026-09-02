from __future__ import annotations

from datetime import date, timedelta

from .. import config
from ..rng import rng_for
from ..writer import write_parquet

PAID_ORDER_STATUSES = {"paid", "shipped", "completed"}
METHODS = ["card", "bank_transfer", "paypal"]
MONTHLY_PLAN_PRICE_CENTS = {"starter": 2900, "growth": 9900, "enterprise": 29900}


def _to_amount(dollars: float, defects: dict) -> int:
    # `cents_vs_decimal`: payments always store integer cents, while orders
    # and product_prices store decimal dollars -- two units in two sources.
    return round(dollars * 100) if defects["cents_vs_decimal"] else round(dollars, 2)


def generate(defects: dict, orders: dict, subscriptions: dict) -> dict:
    rng = rng_for(config.SEED, "payments")

    payment_id: list[str] = []
    payment_customer_id: list = []
    payment_order_id: list = []
    payment_subscription_id: list = []
    payment_amount: list = []
    payment_method: list[str] = []
    payment_paid_at: list[str] = []

    for order_id, customer_id, order_date, status, total in zip(
        orders["order_id"],
        orders["customer_id"],
        orders["order_date"],
        orders["status"],
        orders["total_amount"],
    ):
        if status not in PAID_ORDER_STATUSES:
            continue
        pid = f"pay_{len(payment_id) + 1:07d}"
        paid_at = date.fromisoformat(order_date) + timedelta(
            days=int(rng.integers(0, 3))
        )
        payment_id.append(pid)
        payment_customer_id.append(customer_id)
        payment_order_id.append(order_id)
        payment_subscription_id.append(None)
        payment_amount.append(_to_amount(total, defects))
        payment_method.append(rng.choice(METHODS))
        payment_paid_at.append(paid_at.isoformat())

    for sub_id, customer_id, started_at, active_until in zip(
        subscriptions["subscription_id"],
        subscriptions["customer_id"],
        subscriptions["started_at"],
        subscriptions["active_until"],
    ):
        cursor = date.fromisoformat(started_at)
        end = date.fromisoformat(active_until)
        plan_price = MONTHLY_PLAN_PRICE_CENTS["starter"]
        while cursor <= end:
            pid = f"pay_{len(payment_id) + 1:07d}"
            payment_id.append(pid)
            payment_customer_id.append(customer_id)
            payment_order_id.append(None)
            payment_subscription_id.append(sub_id)
            payment_amount.append(_to_amount(plan_price / 100, defects))
            payment_method.append(rng.choice(METHODS))
            payment_paid_at.append(cursor.isoformat())
            cursor = cursor + timedelta(days=30)

    write_parquet(
        {
            "payment_id": payment_id,
            "customer_id": payment_customer_id,
            "order_id": payment_order_id,
            "subscription_id": payment_subscription_id,
            "amount_cents": payment_amount,
            "method": payment_method,
            "paid_at": payment_paid_at,
        },
        f"{config.OUTPUT_DIR}/payments/payments.parquet",
    )

    refund_id, refund_payment_id, refund_amount, refund_at, refund_reason = (
        _generate_refunds(defects, rng, payment_id, payment_amount, payment_paid_at)
    )
    write_parquet(
        {
            "refund_id": refund_id,
            "payment_id": refund_payment_id,
            "amount_cents": refund_amount,
            "refunded_at": refund_at,
            "reason": refund_reason,
        },
        f"{config.OUTPUT_DIR}/refunds/refunds.parquet",
    )

    return {"payments": len(payment_id), "refunds": len(refund_id)}


REASONS = ["customer_request", "duplicate_charge", "product_defect", "billing_error"]


def _generate_refunds(defects: dict, rng, payment_id, payment_amount, payment_paid_at):
    refund_id: list[str] = []
    refund_payment_id: list[str] = []
    refund_amount: list = []
    refund_at: list[str] = []
    refund_reason: list[str] = []

    base_rate = 0.04
    eligible = [
        i
        for i, paid_at in enumerate(payment_paid_at)
        if date.fromisoformat(paid_at) <= config.REFUND_SPIKE_DATE
    ]

    for i, (pid, amount, paid_at) in enumerate(
        zip(payment_id, payment_amount, payment_paid_at)
    ):
        if rng.random() >= base_rate:
            continue
        refunded_at = date.fromisoformat(paid_at) + timedelta(
            days=int(rng.integers(1, 20))
        )
        if refunded_at > config.END_DATE:
            continue
        refund_id.append(f"ref_{len(refund_id) + 1:07d}")
        refund_payment_id.append(pid)
        refund_amount.append(amount)
        refund_at.append(refunded_at.isoformat())
        refund_reason.append(rng.choice(REASONS))

    if defects["volume_anomaly"] and eligible:
        window_start = config.REFUND_SPIKE_DATE - timedelta(days=14)
        window_end = config.REFUND_SPIKE_DATE + timedelta(days=14)
        local_refunds_in_window = sum(
            1
            for refunded_at in refund_at
            if window_start <= date.fromisoformat(refunded_at) <= window_end
        )
        local_baseline = max(1, round(local_refunds_in_window / 29))
        spike_day_count = sum(
            1 for r in refund_at if r == config.REFUND_SPIKE_DATE.isoformat()
        )
        n_spike = max(0, local_baseline * 8 - spike_day_count)
        spike_targets = rng.choice(
            eligible, size=min(n_spike, len(eligible)), replace=False
        )
        for idx in spike_targets:
            refund_id.append(f"ref_{len(refund_id) + 1:07d}")
            refund_payment_id.append(payment_id[idx])
            refund_amount.append(payment_amount[idx])
            refund_at.append(config.REFUND_SPIKE_DATE.isoformat())
            refund_reason.append("customer_request")

    return refund_id, refund_payment_id, refund_amount, refund_at, refund_reason
