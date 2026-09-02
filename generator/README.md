# Halcyon synthetic source system

Generates ~24 months of history (2024-09-01 → 2026-08-31) for ~5,000 customers into `data/raw/`.
Deterministic: the same seed (`generator/config.py::SEED`) always produces byte-identical output,
regardless of the date the generator is actually run on.

```
make seed
# or directly:
uv run python -m generator
uv run python -m generator --disable duplicate_orders late_web_events
```

## Entities

| Entity | Format | Path |
|---|---|---|
| `customers` | Parquet, one monthly full-table snapshot | `data/raw/customers/customers_YYYY_MM.parquet` |
| `products`, `product_prices` | Parquet | `data/raw/products/`, `data/raw/product_prices/` |
| `orders`, `order_items` | Parquet | `data/raw/orders/`, `data/raw/order_items/` |
| `subscriptions`, `subscription_events` | Parquet | `data/raw/subscriptions/`, `data/raw/subscription_events/` |
| `payments`, `refunds` | Parquet | `data/raw/payments/`, `data/raw/refunds/` |
| `web_events` | JSONL, partitioned by load date | `data/raw/web_events/dt=YYYY-MM-DD/events.jsonl` |
| `support_tickets` | CSV, single hand-maintained export | `data/raw/support_tickets/support_tickets.csv` |
| `marketing_spend` | CSV, daily grain by channel | `data/raw/marketing_spend/marketing_spend.csv` |

`customers` ships as periodic full snapshots rather than a single current-state table, since that's
the only way to represent both attribute drift over time and the schema-change defect below without a
CDC/audit-log source. Every other relational entity is a single current-state extract.

## Injected defects

Every defect is toggleable via `--disable <name>` (see `config.DEFECTS` for the full list) and is on by
default.

| Defect | `--disable` name | Where | When | Exercised by |
|---|---|---|---|---|
| Duplicate `order_id` rows (~0.1%) | `duplicate_orders` | `orders.parquet` | throughout | `AE-07` (staging dedup convention) |
| Null `customer_id` on a small % of orders | `null_customer_id` | `orders.parquet` | throughout | `AE-06` (raw-layer contract), `AE-09` (mart contracts) |
| Money in cents (payments/refunds) vs decimal (orders, product_prices) | `cents_vs_decimal` | `payments.parquet`, `refunds.parquet` | throughout | `AE-07` (`cents_to_decimal()` macro) |
| Naive vs UTC-suffixed timestamps mixed (~5%) | `naive_utc_timestamps` | `web_events` JSONL `event_at` | throughout | `AE-07` (`to_utc()` macro) |
| ~2% of `web_events` arrive 1–3 days late (`event_at` date < partition `dt`) | `late_web_events` | `web_events` JSONL | throughout | `AE-05` (event_at vs `_loaded_at`), `AE-14` (late-arriving lookback) |
| Schema change: `customers.marketing_segment` → `segment`, `consent_flag` added | `schema_change` | `customers` monthly snapshots | 2025-09-01 onward | `AE-05`, `AE-06`, `AE-09` (contract break, on purpose) |
| Volume anomaly: refunds spike ~8x the local daily baseline | `volume_anomaly` | `refunds.parquet` | 2026-03-16 | `AE-28` (anomaly monitoring) |

## Conformed attribution fields

`customers.acquisition_channel` and `web_events.channel`/`web_events.device` were added after `AE-03`'s
bus matrix showed business questions 4 and 7 (CAC by channel, conversion by device/channel) had no source
data to answer them from. All channel-valued fields (`customers`, `web_events`, `marketing_spend`) draw
from the same `config.CHANNELS` list, so the values can't drift between sources — see
`docs/adr/0002-conformed-dimensions.md`.

## Incremental cursors

`customers.updated_at` and `subscriptions.updated_at` were added for `AE-04`'s ingestion pipeline, which
needs a real merge cursor for these two genuinely-mutable entities. Computing "when did this change" by
diffing snapshots at ingestion time would itself be business logic, forbidden by the ELT boundary
(`AE-06`) — so, as a real source system would, the value is set at the point of change: `customers.updated_at`
is the most recent attribute-change date (or `created_at` if none), and `subscriptions.updated_at` is the
latest lifecycle event's timestamp. See `ingestion/README.md` for how every table's cursor and write
disposition were chosen.

## Design notes

- Each entity draws from its own seeded RNG stream (`generator/rng.py`), keyed by entity name, so adding
  or reordering entities in `generator/__main__.py` never changes another entity's random draws.
- `START_DATE`/`END_DATE` in `config.py` are fixed calendar dates, not "today" — required for byte-identical
  output on any run date.
- `web_events` is generated with vectorized numpy arrays per day (not row-by-row Faker) to hit ≥5M rows
  in well under the 5-minute budget; a full run generates ~5.1M events in under a minute.
