from __future__ import annotations

from .. import config
from ..dates import day_range
from ..rng import rng_for
from ..writer import write_parquet
from .products import price_as_of

STATUSES = ["placed", "paid", "shipped", "completed", "cancelled"]
STATUS_WEIGHTS = [0.05, 0.10, 0.15, 0.65, 0.05]


def generate(defects: dict, customers: dict, products: dict) -> dict:
    rng = rng_for(config.SEED, "orders")

    customer_ids = customers["customer_ids"]
    created_at = customers["created_at"]
    product_ids = products["product_ids"]
    price_series = products["price_series"]

    order_id: list[str] = []
    order_customer_id: list = []
    order_date: list[str] = []
    order_status: list[str] = []
    order_total: list[float] = []

    item_id: list[str] = []
    item_order_id: list[str] = []
    item_product_id: list[str] = []
    item_quantity: list[int] = []
    item_unit_price: list[float] = []

    order_seq = 0
    for day in day_range(config.START_DATE, config.END_DATE):
        eligible = [i for i, c in enumerate(created_at) if c <= day]
        if not eligible:
            continue
        n_orders = int(rng.poisson(lam=len(eligible) * 0.018))
        if n_orders == 0:
            continue
        buyers = rng.choice(eligible, size=n_orders, replace=True)
        for buyer_idx in buyers:
            order_seq += 1
            oid = f"ord_{order_seq:07d}"
            n_items = int(rng.integers(1, 5))
            items_total = 0.0
            chosen_products = rng.choice(product_ids, size=n_items, replace=True)
            for product_id in chosen_products:
                item_id.append(f"{oid}_i{len(item_id) + 1}")
                item_order_id.append(oid)
                item_product_id.append(product_id)
                quantity = int(rng.integers(1, 4))
                unit_price = price_as_of(price_series[product_id], day.isoformat())
                item_quantity.append(quantity)
                item_unit_price.append(unit_price)
                items_total += quantity * unit_price

            order_id.append(oid)
            order_customer_id.append(customer_ids[buyer_idx])
            order_date.append(day.isoformat())
            order_status.append(rng.choice(STATUSES, p=STATUS_WEIGHTS))
            order_total.append(round(items_total, 2))

    if defects["null_customer_id"]:
        null_rate = 0.002
        n_nulls = int(len(order_id) * null_rate)
        for idx in rng.choice(len(order_id), size=n_nulls, replace=False):
            order_customer_id[idx] = None

    if defects["duplicate_orders"]:
        dup_rate = 0.001
        n_dupes = max(1, int(len(order_id) * dup_rate))
        for idx in rng.choice(len(order_id), size=n_dupes, replace=False):
            order_id.append(order_id[idx])
            order_customer_id.append(order_customer_id[idx])
            order_date.append(order_date[idx])
            order_status.append(order_status[idx])
            order_total.append(order_total[idx])

    write_parquet(
        {
            "order_id": order_id,
            "customer_id": order_customer_id,
            "order_date": order_date,
            "status": order_status,
            "total_amount": order_total,
        },
        f"{config.OUTPUT_DIR}/orders/orders.parquet",
    )
    write_parquet(
        {
            "order_item_id": item_id,
            "order_id": item_order_id,
            "product_id": item_product_id,
            "quantity": item_quantity,
            "unit_price": item_unit_price,
        },
        f"{config.OUTPUT_DIR}/order_items/order_items.parquet",
    )

    return {
        "stats": {"orders": len(order_id), "order_items": len(item_id)},
        "order_id": order_id,
        "customer_id": order_customer_id,
        "order_date": order_date,
        "status": order_status,
        "total_amount": order_total,
    }
