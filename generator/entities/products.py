from __future__ import annotations

from datetime import timedelta

from faker import Faker

from .. import config
from ..rng import rng_for
from ..writer import write_parquet

CATEGORIES = ["software", "hardware", "services", "add-on"]


def price_as_of(price_series: list[tuple[str, float]], as_of_date: str) -> float:
    price = price_series[0][1]
    for effective_date, amount in price_series:
        if effective_date > as_of_date:
            break
        price = amount
    return price


def generate(defects: dict) -> dict:
    rng = rng_for(config.SEED, "products")
    fake = Faker()
    Faker.seed(config.SEED + 1)

    n = config.N_PRODUCTS
    product_ids = [f"prd_{i + 1:03d}" for i in range(n)]
    names = [fake.unique.catch_phrase() for _ in range(n)]
    categories = rng.choice(CATEGORIES, size=n).tolist()

    span_days = (config.END_DATE - config.START_DATE).days
    created_offsets = rng.integers(0, span_days // 4, size=n)
    created_at = [config.START_DATE + timedelta(days=int(o)) for o in created_offsets]

    write_parquet(
        {
            "product_id": product_ids,
            "name": names,
            "category": categories,
            "created_at": [d.isoformat() for d in created_at],
        },
        f"{config.OUTPUT_DIR}/products/products.parquet",
    )

    # Every product launches at a base price, then gets 0-3 price changes on
    # known dates -- the reason SCD Type 2 exists downstream.
    price_product_id: list[str] = []
    price_amount: list[float] = []
    price_effective_date: list[str] = []

    for i in range(n):
        base_price = round(float(rng.uniform(9, 499)), 2)
        price_product_id.append(product_ids[i])
        price_amount.append(base_price)
        price_effective_date.append(created_at[i].isoformat())

        n_changes = int(rng.integers(0, 4))
        current_price = base_price
        remaining_span = (config.END_DATE - created_at[i]).days
        if remaining_span <= 0:
            continue
        change_days = sorted(
            rng.choice(
                remaining_span, size=min(n_changes, remaining_span), replace=False
            )
        )
        for offset in change_days:
            effective_date = created_at[i] + timedelta(days=int(offset))
            if effective_date <= created_at[i]:
                continue
            direction = rng.choice([-1, 1])
            current_price = round(
                max(1.0, current_price * (1 + direction * rng.uniform(0.05, 0.2))), 2
            )
            price_product_id.append(product_ids[i])
            price_amount.append(current_price)
            price_effective_date.append(effective_date.isoformat())

    write_parquet(
        {
            "product_id": price_product_id,
            "price_amount": price_amount,
            "effective_date": price_effective_date,
        },
        f"{config.OUTPUT_DIR}/product_prices/product_prices.parquet",
    )

    price_series: dict[str, list[tuple[str, float]]] = {pid: [] for pid in product_ids}
    for pid, amount, eff_date in zip(
        price_product_id, price_amount, price_effective_date
    ):
        price_series[pid].append((eff_date, amount))
    for series in price_series.values():
        series.sort()

    return {
        "stats": {"products": n, "price_points": len(price_product_id)},
        "product_ids": product_ids,
        "price_series": price_series,
    }
