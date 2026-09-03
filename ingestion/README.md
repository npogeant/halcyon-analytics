# Relational ingestion

A `dlt` pipeline that loads every relational/tabular entity from `data/raw/` (everything except
`web_events`, which is `AE-05`'s job) into the `raw` schema of the DuckDB warehouse at
`data/halcyon.duckdb` — the same file `transform/profiles.yml` points dbt at.

```
make ingest
# or directly:
uv run python -m ingestion
uv run python -m ingestion --full-refresh   # drop raw data + incremental state, reload everything
```

To inspect the raw layer directly (no dbt model required):

```
make shell
# opens the DuckDB CLI (v1.5.5, matching the `duckdb` Python driver pin) on data/halcyon.duckdb
```

```sql
SELECT * FROM raw.orders LIMIT 10;
SELECT table_name FROM information_schema.tables WHERE table_schema = 'raw';
```

## Write disposition, per table

| Table | Disposition | Primary key | Incremental cursor | Why |
|---|---|---|---|---|
| `products` | `merge` | `product_id` | `created_at` | Catalog metadata is conceptually mutable even though this generator never changes it post-creation; merge is still the correct disposition for what this table represents. |
| `subscriptions` | `merge` | `subscription_id` | `updated_at` | A subscription's status changes over its lifecycle (`trialing` → `active` → ... → `cancelled`); merge keeps one current-state row per subscription. |
| `product_prices` | `append` | `(product_id, effective_date)` | `effective_date` | Each price change is a new, immutable event — never edited, only appended to. |
| `order_items` | `append` | `order_item_id` | `order_id` | Immutable line items; never updated after an order is placed. |
| `subscription_events` | `append` | `subscription_event_id` | `event_at` | An immutable event log by definition. |
| `payments` | `append` | `payment_id` | `paid_at` | A payment is a one-time, immutable financial event. |
| `refunds` | `append` | `refund_id` | `refunded_at` | Same reasoning as `payments`. |
| `support_tickets` | `append` | `ticket_id` | `created_at` | The generator doesn't model ticket status mutation, so there's nothing to merge; append reflects what the source actually provides. |
| `marketing_spend` | `append` | `(date, channel)` | `date` | A daily fact at day × channel grain, booked once per day and never revised. |
| **`orders`** | **`append`** | `order_id` | `order_date` | **Deliberately not merged.** The generator injects a ~0.1% duplicate-`order_id` defect on purpose, and raw must be a faithful record of what the source sent — including its defects. `AE-07` deduplicates this in staging, with a documented tie-break rule. See below for what `primary_key` is still doing here. |
| **`customers`** | **`append`** | `customer_id` | `updated_at` | **Also deliberately not merged**, for a different reason: the generator's 24 monthly snapshot files are the *only* place this project's customer attribute history exists (`country`/`segment`/`plan_tier` over time). Merging on `customer_id` would collapse everything to current-state-only, destroying exactly the history `AE-10`'s `dbt snapshot` needs to answer "what was this customer's plan tier as of an arbitrary past date." Raw holds all ~62.8k historical snapshot rows for 5,000 customers, not a collapsed 5,000. |

`primary_key` on an `append` resource does **not** collapse rows within a single load — it only lets
dlt's incremental extraction recognize "I already sent this row at this cursor value on a previous run"
and skip re-sending it. This matters because every cursor above is date-only (no time component): on any
given day, many rows share the exact same cursor value, and without `primary_key`, dlt's default
`range_start="closed"` re-includes *all* same-day rows on every subsequent run — which is exactly what
broke idempotency during development here (`orders` grew from 33,386 to 33,474 rows on a second, unchanged
run before this was added). With `primary_key` set, the two genuinely-duplicate `order_id` rows still both
land in `raw.orders` on the *first* load (dlt has no prior-run state yet to compare against), and neither
grows further on subsequent runs. `customers` works the same way: all ~62.8k historical rows land on the
first load regardless of `primary_key` (dlt never dedupes within a single load), and `primary_key` only
stops that count from growing further on repeat runs.

## Load metadata

Every raw table carries `_loaded_at`, `_source_name`, `_load_id`, set once per pipeline run and identical
across every row loaded in that run.

Every raw table also carries `_dlt_load_id`/`_dlt_id` — these are dlt's own internal bookkeeping columns
(load-package tracking, merge staging), not something this pipeline adds. They're deliberately left in
place rather than stripped: `_dlt_load_id` in particular is part of the same mechanism behind the
crash-safety guarantee below, and dlt's merge disposition can fall back to `_dlt_id` as a row identity when
no primary key is set (not the case here — every merge table has one). They won't leak into dbt docs
later, though: `AE-07`'s staging models select named columns explicitly (`renaming and casting only`), so
`_dlt_load_id`/`_dlt_id` simply never get selected unless a model deliberately reaches for them.

## Idempotency and crash safety

Verified during development:
- Two consecutive runs against unchanged source data: identical row counts on every table (the second run
  finished in ~0.2s vs ~20s for the first, since incremental extraction reads all the source files but
  discards everything already past each resource's cursor before it reaches the destination).
- `kill -9` mid-run, then re-run: no duplicate or corrupted rows. This comes from `dlt`'s own load-package
  atomicity (each run stages data before committing it as a whole), not anything custom built here.

## Raw layer discipline

Nothing in `ingestion/` renames columns, converts currency, or filters rows — that's staging's job
(`AE-07`, and the ELT boundary formalized in `AE-06`). The one exception is `support_tickets`: a stray
trailing comma on ~1% of rows (another `AE-02` defect) is tolerated structurally so the row isn't dropped,
but the messy `status` casing itself is left untouched for `AE-15` to normalize downstream.
