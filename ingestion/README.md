# Ingestion

Two `dlt` pipelines that load the Halcyon raw layer from `data/raw/` into the `raw` schema of the DuckDB
warehouse at `data/halcyon.duckdb` — the same file `transform/profiles.yml` points dbt at:

- `relational.py` (`AE-04`) — every relational/tabular source (customers, orders, payments, ...).
- `web_events.py` (`AE-05`) — the partitioned JSONL event stream.

Both write into the same `raw` dataset and can run independently or together.

```
make ingest
# or directly:
uv run python -m ingestion                              # both sources
uv run python -m ingestion --source relational
uv run python -m ingestion --source web_events
uv run python -m ingestion --full-refresh                # drop raw data + incremental state, reload everything
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

## `web_events` (`AE-05`)

`web_events` isn't in the table above: it's a single resource, `append`, primary key `event_id`, loaded
from `ingestion/web_events.py`.

**Incremental cursor is the file's partition date, never `event_at`.** The generator's late-arriving
defect writes ~2% of events with an `event_at` 1–3 days *earlier* than the `dt=` partition folder they
land in. If the incremental cursor were `event_at`, a day's late events would sit behind dlt's already-advanced
watermark and never be re-scanned — silently losing data, and doing it quietly. `_partition_date` only
ever advances forward one real file at a time regardless of what any individual event's `event_at` says,
so it's safe as an extraction checkpoint. `event_at` stays in the row as an ordinary column — comparing it
against `_partition_date` (or `_loaded_at`) is exactly how a downstream query identifies which events
arrived late.

**Schema-agnostic extraction: no maintained column list.** `_read_partition_as_table` parses each day's
file with `pyarrow.json.read_json`, which infers the table schema directly from the file — every field
present in the JSON is picked up automatically, including one this code has never seen before. The only
type this pipeline forces is `event_at`, which must stay a raw string (see below); everything else,
`utm_campaign` included, needs zero code awareness of its name to be captured correctly. An earlier version
of this resource kept an explicit `_COLUMNS` allowlist and manually built each column with `event.get(name)`
— convenient for the vectorized extraction, but a real correctness gap: any field not on that list would
be silently dropped before dlt ever saw it, regardless of dlt's own `evolve`/`freeze` schema contract. That
list is gone; nothing here needs updating if the source ever adds a field.

**Nested field: `geo` kept as a single JSON column, not flattened.** Every event carries
`geo: {"country": ...}`. `pyarrow.json.read_json` reads it as a native arrow `struct` column; dlt maps a
struct-typed arrow column to its own `json` data type automatically (`max_table_nesting=0` on the resource
is what tells it to do that instead of flattening the struct into `geo__country` — no explicit `columns=`
type hint needed at all, since the arrow type itself already says "struct," not "string"). Tradeoff:
`geo__country` would be directly filterable/joinable in the warehouse with an ordinary equality predicate,
at the cost of a rebuild any time the attribute bag's shape changes. Keeping it as JSON means the raw layer
survives arbitrary future keys inside `geo` with zero pipeline changes, at the cost of needing
`json_extract` in staging to pull `country` out — the right tradeoff for an attribute bag with no fixed,
agreed-on shape yet (unlike `channel`/`device`, which stay flat top-level columns because the bus matrix
already documents them as dimensions).

**`event_at` is the one field forced to a fixed type, and for the opposite reason `geo` isn't.**
`pyarrow.json.read_json`'s own type inference would otherwise parse well-formed timestamps into
`timestamp[s]` and silently collapse the naive-vs-UTC-suffixed distinction the generator injects on
purpose — the exact defect `AE-07`'s `to_utc()` macro exists to fix downstream. That's ingestion making a
business decision about the data it isn't allowed to make (`AE-06`'s ELT boundary). `ParseOptions(
explicit_schema=pa.schema([("event_at", pa.string())]), unexpected_field_behavior="infer")` pins that one
field and leaves every other field, named or not, to be inferred normally.

**Schema evolution: `evolve` columns, `freeze` data types.**
`schema_contract={"columns": "evolve", "data_type": "freeze"}`. New columns (like the mid-history
`utm_campaign` addition below) are allowed to land automatically — the alternative, `freeze`, would raise
and stop the whole load the first time a genuinely new, legitimate field showed up, which fails exactly
the requirement that ingestion "must survive it without dropping data." `data_type: freeze` is the
guardrail on the other side: if `event_id` ever arrived as an integer instead of a string, that's a real
break, and it should fail loudly at ingestion rather than get silently coerced.

**The mid-history schema change (`utm_campaign`) needed no special handling at all, in the end.** Events
before 2025-11-01 have no `utm_campaign` key in the source JSON; events from that date on always have it.
`pyarrow.json.read_json` already infers per-file, so an early day's parsed table simply has no
`utm_campaign` column, and a post-change day's table has it, fully populated, with a correctly-inferred
`string` type — no code anywhere names `utm_campaign` specifically.

This went through two real false starts worth recording, in order:

1. An earlier version yielded per-row Python dicts (not arrow tables) built from a maintained `_COLUMNS`
   list, always including `utm_campaign` (`None` when absent). A batch entirely before the change date then
   had an all-null column, and dlt can't infer a type from all-null data — its own warning is explicit:
   *"these columns will not be materialized in the destination"* unless a type hint is provided.
2. The fix reached for next was an explicit `columns={"utm_campaign": {"data_type": "text"}}` hint on the
   resource. That "worked," but it meant declaring a column's type before any run had ever seen it — not
   something a real pipeline could do for a field it doesn't know exists yet — and it meant the field was
   part of the schema from the very first run, so dlt never actually *discovered* a new column, defeating
   the point of demonstrating schema evolution at all. It also still depended on the `_COLUMNS` allowlist,
   so any *other* unanticipated field would still have been silently dropped.

Switching extraction to `pyarrow.json.read_json` (above) removed both problems at once: the all-null case
never arises, because a column that isn't in the source data for a given file just isn't in that file's
inferred schema at all — and no field name needs to be known in advance for any of this to work correctly.

Verified as two separate runs against a partitioned subset of `data/raw/web_events/`: a `--full-refresh`
run against only pre-2025-11-01 partitions produces a `raw.web_events` table with **no** `utm_campaign`
column at all; adding the remaining partitions and re-running (incremental, no `--full-refresh`) logs
exactly `schema evolution: raw.web_events gained column(s) ['utm_campaign']` and nothing else — a genuine,
dynamically-discovered column addition, not a preemptive declaration. Combined row count after both phases
matches a from-scratch full run exactly (5,116,634 rows, zero dropped), `utm_campaign` is `NULL` for every
row from before the change and populated for every row from on/after it.

**Schema-change logging.** `_log_schema_changes` reads `load_info.load_packages[i].schema_update` — dlt's
own record of exactly which tables/columns were added during that specific run — and logs any new columns
on `web_events` via Python's `logging` module. This is what fired the `['utm_campaign']` line above. On a
first-ever full backfill (the normal `make ingest` path, since all 730 partition files already exist from
one generator run), every column looks "new" in that one log line, which is expected and not wrong — dlt's
`_dlt_version` table in the destination is the durable, queryable schema-history record either way.

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

Verified during development, for both `relational` and `web_events`:
- Two consecutive runs against unchanged source data: identical row counts on every table. The `relational`
  load step drops from ~20s to ~0.2s on the second run; `web_events`'s load step drops from ~10s to ~0.2s
  the same way — but note the *extraction* phase (reading and JSON-parsing all 730 partition files) still
  runs in full every time regardless of what's actually new, since nothing here skips a file at the
  filesystem level. A full combined run (`make ingest`, both sources, one full backfill) takes ~2.5 minutes
  wall time; an idempotent no-op rerun still takes ~30s for the same reason. That's an accepted tradeoff for
  a local demo pipeline, not a target to optimize further here.
- `kill -9` mid-run, then re-run: no duplicate or corrupted rows — but killing only the top-level `python -m
  ingestion` process is not sufficient to reproduce a real crash. dlt's normalize step runs in its own
  worker process (`pool_type="process"` by default), so `kill -9` on the parent can leave that child alive,
  holding DuckDB's file lock; the next run then fails fast with a clear
  `IO Error: Could not set lock on file ...` rather than corrupting anything, and recovers cleanly once the
  orphaned process is also killed. A true kill (process-group kill, or an actual OOM) takes the whole tree
  down together and recovers exactly like the simple case: no duplicate or corrupted rows, from `dlt`'s own
  load-package atomicity.

## Raw layer discipline

Nothing in `ingestion/` renames columns, converts currency, or filters rows — that's staging's job
(`AE-07`, and the ELT boundary formalized in `AE-06`). The one exception is `support_tickets`: a stray
trailing comma on ~1% of rows (another `AE-02` defect) is tolerated structurally so the row isn't dropped,
but the messy `status` casing itself is left untouched for `AE-15` to normalize downstream.
