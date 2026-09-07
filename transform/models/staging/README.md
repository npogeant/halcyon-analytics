# Staging

One model per source table (`AE-04`/`AE-05`'s raw tables), renaming and casting only — no joins, no
aggregation, no filtering. Materialized as views. Named `stg_<domain>__<entity>`, where `<domain>` groups
tables by business area (`crm`, `catalog`, `sales`, `subscriptions`, `billing`, `support`, `marketing`,
`events`), not by dlt pipeline name.

## Convention

- **snake_case** names throughout (the source already is; kept, not re-derived).
- **`*_id` suffix** for every key column.
- **Timestamp suffix reflects actual granularity, not the source's naming.** Most `_at`-suffixed columns in
  raw are date-only (the generator builds them from Python `date`, not `datetime`, objects — `orders.order_date`,
  `payments.paid_at`, `refunds.refunded_at`, `support_tickets.created_at`, `subscriptions.started_at`/`updated_at`,
  `subscription_events.event_at`, `customers.created_at`/`updated_at`). Those are renamed to a `*_date`
  suffix and cast to `DATE` in staging. Only `web_events.event_at` genuinely carries time-of-day; it keeps
  the `_at` suffix and is cast to `TIMESTAMPTZ` via `to_utc()`. Blindly copying the source's `_at` naming
  would have been the mechanical choice; this isn't that — it's a naming convention that reflects what the
  data actually is.
- **All timestamps converted to UTC** via `to_utc()` (only `web_events.event_at` needs it; every date-only
  column above is unambiguous and just cast to `DATE`).
- **All money normalized to decimal USD**, column suffixed `_usd` (`amount_usd`, not `amount`). This
  project only ever has one currency (`marketing_spend.currency` is always `"USD"` in the generated data),
  so the suffix names the unit without a currency-conversion macro to go with it — if a second currency
  ever appeared, that would need real conversion logic, not just a rename.
- **A loaded-at audit column** (`loaded_at`, cast to `TIMESTAMPTZ`) is kept on every staging model. Every
  other underscore-prefixed dlt/ingestion metadata column (`_source_name`, `_load_id`, `_dlt_load_id`,
  `_dlt_id`, `_partition_date`) is dropped — staging selects named business columns, not transport
  bookkeeping (`AE-06`'s ELT boundary again: those columns describe the *load*, not the *data*).

## Macros

- `to_utc(column)` — the naive-vs-UTC-suffixed timestamp defect, resolved with an explicit assumption
  (naive means UTC, not any other timezone) rather than relying on DuckDB's session `TimeZone` default.
- `cents_to_decimal(column)` — the cents-vs-decimal money defect (`payments`/`refunds` store cents;
  `orders`/`product_prices` already store decimal dollars).
- `surrogate_key(field_list)` — thin wrapper around `dbt_utils.generate_surrogate_key`. Not used by any
  staging model (staging keeps natural keys); it's declared here because this is where the project's macro
  conventions get established, and `AE-10` is its first real consumer.

## Deduplication

`stg_sales__orders` deduplicates the generator's injected ~0.1% duplicate-`order_id` defect with
`ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY loaded_at ASC, order_id ASC) = 1` — earliest-loaded copy
wins. In this dataset the duplicate rows are byte-identical copies, so the tie-break is functionally moot
here, but it's still deterministic and would resolve correctly against a real source where two "duplicate"
rows disagree on some other column. `AE-12`'s uniqueness test on `fct_orders`' grain key is what proves this
actually worked, downstream.
