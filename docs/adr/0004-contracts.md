# 0004 · Data contracts at the mart boundary

## Status
Accepted

## Context
`AE-07` gave staging a stable, predictable convention. That's necessary but not sufficient: nothing
*enforced* it. A column could silently disappear or change type between staging and a mart, and a `dbt
build` would still succeed — the failure would show up three layers downstream, as a null column on a
dashboard nobody could immediately explain. `contract: enforced` on a mart model closes that specific gap:
dbt refuses to build the model at all if its declared shape doesn't match what the SQL actually produces.

This project doesn't have a real mart yet (`AE-10`–`AE-14` build those, milestone M3, after this issue).
So `AE-09` builds one now: a deliberately minimal `dim_customer` — current state per customer, no SCD2
history — specifically to have something real to enforce a contract on and break on purpose. `AE-10`
replaces it with the actual Type 2 version built on a `dbt snapshot`.

## Decision

**Contracts guarantee shape and types. Nothing else.** `dim_customer`'s contract declares nine columns,
each with a `data_type`, plus `primary_key`/`not_null` on `customer_id`. dbt checks this at *compile* time,
before any row is touched — verified directly: deliberately mistyping `consent_flag` as `varchar` instead
of `boolean` produced a compilation error naming the exact column and mismatch (`BOOLEAN` vs `VARCHAR`)
before the `CREATE TABLE` statement ever ran. That's the contract working exactly as designed.

**Contracts do not guarantee meaning.** A column can pass every check in this contract — right name, right
type, not null, values present — and still mean something different than it used to. Concrete example from
this project's own domain: `subscriptions.status = 'active'`. Nothing stops a future change to the
generator (or, in a real system, to the source application) from redefining what "active" *means* — say,
from "has a currently-valid, unexpired subscription" to "has logged in within the last 30 days" — while the
column stays `varchar`, stays not null, and keeps producing the exact same set of string values
(`active`/`trialing`/`paused`/`cancelled`). Every contract check in this project would pass. Every metric
built on `status = 'active'` (MRR, churn, the semantic layer's eventual `AE-17` metrics) would be silently
wrong. A contract enforces the *container*; it has no way to know the *content*'s definition changed.

**Two breaks were reproduced, not just described** — the whole point of this issue's context (*"a contract
that has never been violated is a comment"*):
1. **Staging**: `stg_crm__customers`'s `dbt_expectations.expect_table_columns_to_match_set` check,
   temporarily regressed to the pre-schema-change column list (removing `consent_flag`, simulating "staging
   hadn't been updated for the 2025-09-01 change yet"). Failed with the exact column named:
   `relation_column = CONSENT_FLAG`, `input_column = NULL`. This is the earliest layer that would have
   caught the real schema change, had `AE-07` not already handled it via `coalesce()`.
2. **Mart**: `dim_customer`'s contract, temporarily mistyping `consent_flag`. Failed at compile time with
   `data type mismatch`, before any data was written.

Both were reverted immediately after capturing the failure output; neither represents a real defect in the
shipped code.

**`on_schema_change: fail` is the only choice that doesn't undermine the contract itself.**
`append_new_columns`/`sync_all_columns` would let an incremental run silently alter `dim_customer`'s actual
columns — which directly contradicts what an *enforced* contract is supposed to guarantee: that the shape
is fixed and known in advance. dbt doesn't hard-block combining them (checked directly against dbt-core's
`on_schema_change.sql` macro — no contract-awareness there), but doing so would be self-defeating: an
`ignore`/`sync` policy papering over exactly the kind of drift the contract exists to catch loudly instead.

**No `foreign_key` constraint yet.** `dim_customer` is a dimension with nothing referencing it — no fact
table exists to declare a foreign key against. This isn't a gap left open on purpose to revisit "eventually";
it's the direct consequence of building the mart layer out of dependency order for this one issue. `AE-12`
(`fct_orders`) is where a real `foreign_key` constraint against `dim_customer.customer_id` becomes possible
and appropriate.

## Consumers affected (no formal exposures exist yet — `AE-31`)

`dim_customer` has no real downstream consumers today; it's new. Once it does, a contract change here
(renaming or retyping a column) would be a breaking change for: any mart joining on `customer_id`
(`AE-12`+), the semantic layer's customer entity (`AE-17`), and eventually any BI dashboard or exposure
built on top (`AE-31`). This list is narrative, not a formal `exposures:` block — those don't exist in this
project until `AE-31`; documenting them now would be inventing structure this project hasn't earned yet.

## What this costs

A contract violation blocks the *entire* model from building, even if only one column drifted — there's no
partial success. That's the tradeoff: strict, loud failure at the boundary in exchange for zero tolerance,
which is exactly the point (a build that "mostly worked" while quietly getting one column wrong is worse
than one that visibly failed).
