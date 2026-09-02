# 0002 · Conformed dimensions

## Status
Accepted

## Context
The bus matrix in `docs/data-model.md` names five candidate conformed dimensions: `date`, `customer`,
`product`, `channel`, `plan`. A dimension is worth conforming — building once, with one surrogate key, one
SCD policy, reused everywhere — only when at least two business processes actually share it at the same
grain and meaning. Conforming a dimension that only one process uses is speculative design cost paid
before there's a second consumer to justify it.

## Decision

**Truly conformed now** (built as a real dimension table, shared by ≥2 facts):
- **`dim_date`** — every fact joins to it (`fct_orders`, `fct_subscription_daily`, `fct_web_events`,
  `marketing_spend`). No process defines "date" differently, so this is the cheapest possible conform.
- **`dim_customer`** — shared by `fct_orders`, `fct_subscription_daily`, `fct_web_events`, and (via the
  bridge) `support`. Built as SCD Type 2 (`AE-10`) so each fact resolves "customer as of that fact's date,"
  which is the entire reason a dimension exists instead of a denormalized lookup.
- **`dim_product`** — shared by `fct_orders` and `fct_web_events`. Built with all three SCD variants
  side by side (`AE-11`) for the price-history case; `fct_orders` joins against whichever is chosen as
  production (`AE-11`).

**Declared but not yet built as full dimensions** (single-consumer today, embedded as a plain attribute
instead of a dimension table):
- **`plan`** — used only by `fct_subscription_daily`, with three fixed values (`starter`, `growth`,
  `enterprise`). Stored as a degenerate dimension (a plain column on the fact) rather than a separate
  `dim_plan` table: a dimension table buys attribute history and reuse, and a 3-row, effectively-static
  lookup gets neither. Revisit if plan-level attributes (e.g. feature entitlements) grow enough to need
  their own SCD.
- **`channel`** — used only by `marketing_spend` today. `fct_orders` and `fct_web_events` don't yet carry
  attribution (see `docs/data-model.md` §6, a known generator gap), so there's no second consumer to
  conform against yet. Declaring it now in the bus matrix, rather than waiting, is deliberate: once
  attribution lands on orders/events, `channel` needs to already mean the same thing everywhere, and
  retrofitting a shared definition after two facts have each invented their own is the expensive path.

## What this costs
Conforming `dim_customer` and `dim_product` as SCD2 means every fact join carries a range condition
(`order_date BETWEEN valid_from AND valid_to`) instead of a plain equi-join — slower and more error-prone
to write by hand, which is exactly what the surrogate-key and join macros in `AE-07`/`AE-10` exist to
paper over. Leaving `plan` and `channel` unconformed for now means a future migration to full dimension
tables if either grows table-worthy attributes; that migration touches every fact that embedded them, so
it should not be delayed indefinitely — it's exactly the point `docs/data-model.md` §6 is left open on.
