from __future__ import annotations

import csv
import glob
import uuid
from datetime import UTC, datetime

import dlt
import pyarrow.parquet as pq

from . import config

_EPOCH_DATE = "1970-01-01"
_EPOCH_DATETIME = "1970-01-01T00:00:00"


def _read_parquet(path: str):
    yield from pq.read_table(path).to_pylist()


def _read_parquet_glob(pattern: str):
    for path in sorted(glob.glob(pattern)):
        yield from _read_parquet(path)


def _read_csv(path: str):
    with open(path, encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f)


def _read_support_tickets_csv(path: str):
    # Hand-maintained export: some rows carry a stray trailing comma (AE-02's
    # `duplicate_orders`-style defect, but for tickets). Tolerated structurally
    # here so the row isn't lost; the messy `status` casing is left untouched
    # for AE-15 to normalise in staging -- that's business logic, not transport.
    with open(path, encoding="utf-8") as f:
        header = f.readline().rstrip("\n").split(",")
        for line in f:
            fields = line.rstrip("\n").split(",")
            yield dict(zip(header, fields[: len(header)]))


def _with_metadata(rows, source_name: str, load_id: str, loaded_at: str):
    for row in rows:
        yield {
            **row,
            "_loaded_at": loaded_at,
            "_source_name": source_name,
            "_load_id": load_id,
        }


@dlt.source(name="halcyon_relational")
def halcyon_relational_source(load_id: str, loaded_at: str):
    def meta(rows, name):
        return _with_metadata(rows, name, load_id, loaded_at)

    @dlt.resource(
        name="customers", write_disposition="append", primary_key="customer_id"
    )
    def customers(
        cursor=dlt.sources.incremental("updated_at", initial_value=_EPOCH_DATETIME),  # noqa: B008 -- dlt's documented incremental pattern
    ):
        # append, not merge: the generator's 24 monthly snapshot files are the
        # only place this project's full customer attribute history exists.
        # Merging on customer_id would collapse them to current-state-only,
        # destroying exactly the history AE-10's dbt snapshot needs to answer
        # "what was this customer's plan tier as of an arbitrary past date."
        # primary_key still enables cross-run boundary dedup (see `orders`);
        # it doesn't collapse the within-run history.
        yield from meta(
            _read_parquet_glob(f"{config.RAW_DIR}/customers/customers_*.parquet"),
            "customers",
        )

    @dlt.resource(name="products", write_disposition="merge", primary_key="product_id")
    def products(
        cursor=dlt.sources.incremental("created_at", initial_value=_EPOCH_DATE),  # noqa: B008 -- dlt's documented incremental pattern
    ):
        yield from meta(
            _read_parquet(f"{config.RAW_DIR}/products/products.parquet"), "products"
        )

    @dlt.resource(
        name="product_prices",
        write_disposition="append",
        primary_key=["product_id", "effective_date"],
    )
    def product_prices(
        cursor=dlt.sources.incremental("effective_date", initial_value=_EPOCH_DATE),  # noqa: B008 -- dlt's documented incremental pattern
    ):
        yield from meta(
            _read_parquet(f"{config.RAW_DIR}/product_prices/product_prices.parquet"),
            "product_prices",
        )

    @dlt.resource(name="orders", write_disposition="append", primary_key="order_id")
    def orders(
        cursor=dlt.sources.incremental("order_date", initial_value=_EPOCH_DATE),  # noqa: B008 -- dlt's documented incremental pattern
    ):
        # primary_key here only lets dlt's incremental de-duplicate rows it
        # already sent at the same order_date boundary on a *later* run --
        # write_disposition stays "append", so it never collapses rows within
        # a single load. The injected duplicate-order_id defect still lands in
        # raw twice on the first load, faithfully. Deduplication of that
        # defect happens downstream, in staging (AE-07), not here.
        yield from meta(
            _read_parquet(f"{config.RAW_DIR}/orders/orders.parquet"), "orders"
        )

    @dlt.resource(
        name="order_items", write_disposition="append", primary_key="order_item_id"
    )
    def order_items(
        cursor=dlt.sources.incremental("order_id", initial_value=""),  # noqa: B008 -- dlt's documented incremental pattern
    ):
        yield from meta(
            _read_parquet(f"{config.RAW_DIR}/order_items/order_items.parquet"),
            "order_items",
        )

    @dlt.resource(
        name="subscriptions", write_disposition="merge", primary_key="subscription_id"
    )
    def subscriptions(
        cursor=dlt.sources.incremental("updated_at", initial_value=_EPOCH_DATETIME),  # noqa: B008 -- dlt's documented incremental pattern
    ):
        yield from meta(
            _read_parquet(f"{config.RAW_DIR}/subscriptions/subscriptions.parquet"),
            "subscriptions",
        )

    @dlt.resource(
        name="subscription_events",
        write_disposition="append",
        primary_key="subscription_event_id",
    )
    def subscription_events(
        cursor=dlt.sources.incremental("event_at", initial_value=_EPOCH_DATETIME),  # noqa: B008 -- dlt's documented incremental pattern
    ):
        yield from meta(
            _read_parquet(
                f"{config.RAW_DIR}/subscription_events/subscription_events.parquet"
            ),
            "subscription_events",
        )

    @dlt.resource(name="payments", write_disposition="append", primary_key="payment_id")
    def payments(
        cursor=dlt.sources.incremental("paid_at", initial_value=_EPOCH_DATE),  # noqa: B008 -- dlt's documented incremental pattern
    ):
        yield from meta(
            _read_parquet(f"{config.RAW_DIR}/payments/payments.parquet"), "payments"
        )

    @dlt.resource(name="refunds", write_disposition="append", primary_key="refund_id")
    def refunds(
        cursor=dlt.sources.incremental("refunded_at", initial_value=_EPOCH_DATE),  # noqa: B008 -- dlt's documented incremental pattern
    ):
        yield from meta(
            _read_parquet(f"{config.RAW_DIR}/refunds/refunds.parquet"), "refunds"
        )

    @dlt.resource(
        name="support_tickets", write_disposition="append", primary_key="ticket_id"
    )
    def support_tickets(
        cursor=dlt.sources.incremental("created_at", initial_value=_EPOCH_DATE),  # noqa: B008 -- dlt's documented incremental pattern
    ):
        yield from meta(
            _read_support_tickets_csv(
                f"{config.RAW_DIR}/support_tickets/support_tickets.csv"
            ),
            "support_tickets",
        )

    @dlt.resource(
        name="marketing_spend",
        write_disposition="append",
        primary_key=["date", "channel"],
    )
    def marketing_spend(
        cursor=dlt.sources.incremental("date", initial_value=_EPOCH_DATE),  # noqa: B008 -- dlt's documented incremental pattern
    ):
        yield from meta(
            _read_csv(f"{config.RAW_DIR}/marketing_spend/marketing_spend.csv"),
            "marketing_spend",
        )

    return (
        customers,
        products,
        product_prices,
        orders,
        order_items,
        subscriptions,
        subscription_events,
        payments,
        refunds,
        support_tickets,
        marketing_spend,
    )


def run(full_refresh: bool = False):
    load_id = str(uuid.uuid4())
    loaded_at = datetime.now(UTC).isoformat()

    pipeline = dlt.pipeline(
        pipeline_name=config.PIPELINE_NAME,
        destination=dlt.destinations.duckdb(credentials=config.DUCKDB_PATH),
        dataset_name=config.DATASET_NAME,
    )
    source = halcyon_relational_source(load_id=load_id, loaded_at=loaded_at)
    return pipeline.run(source, refresh="drop_data" if full_refresh else None)
