{{ config(materialized='view') }}

-- Reconstructs dim_customer's full Type 2 history from stg_crm__customers in a
-- single pass, rather than replaying `dbt snapshot` once per historical change
-- date (730 distinct change dates across the customer base -- one invocation
-- per date would take roughly an hour and still only be as fast as dbt's own
-- startup cost allows).
--
-- The source landed as a one-time bulk load of the generator's full history
-- (all 24 monthly files already sit in the staging table at once), not as a
-- real incremental feed. A single `dbt snapshot` invocation can only ever
-- capture "state right now" -- it has no way to retroactively produce the
-- ~2 years of prior versions this table already contains. A genuine
-- `dbt snapshot` (see snapshots/customers_snapshot.sql) still exists and is
-- correctly configured to capture any *future* change the normal way; this
-- model's job is strictly the one-time backfill of everything that already
-- happened before this pipeline could have been watching.
--
-- Only country, plan_tier and segment drive a new version. acquisition_channel
-- is fixed at signup (per the generator, never revisited) and consent_flag
-- never actually varies for a given customer once known (verified: zero
-- customers carry two distinct non-null values, see dim_customer.yml's test)
-- -- both ride along as plain attributes rather than participating in
-- version-boundary detection.

with customer_days as (
    -- Collapse the raw duplicate rows that share one updated_date (an
    -- artifact of the source's schema evolution: pre/post schema-change rows
    -- for an unchanged month differ only in which columns are populated, not
    -- in the actual business values) down to one row per customer per
    -- distinct change date.
    select
        customer_id,
        updated_date,
        max(email) as email,
        max(country) as country,
        max(plan_tier) as plan_tier,
        max(acquisition_channel) as acquisition_channel,
        max(segment) as segment,
        max(consent_flag) as consent_flag,
        min(created_date) as created_date
    from {{ ref('stg_crm__customers') }}
    group by customer_id, updated_date
),

with_lags as (
    select
        *,
        lag(country) over customer_timeline as prev_country,
        lag(plan_tier) over customer_timeline as prev_plan_tier,
        lag(segment) over customer_timeline as prev_segment
    from customer_days
    window customer_timeline as (partition by customer_id order by updated_date)
),

changes_flagged as (
    -- A plain boolean OR cast to int, not a CASE expression: sqlfluff's
    -- duckdb dialect (v4.3.0) can't parse `is distinct from` inside a CASE
    -- WHEN (confirmed in isolation -- it parses fine everywhere else), so
    -- this sidesteps that rather than fighting the linter.
    select
        *,
        cast(
            (prev_country is distinct from country)
            or (prev_plan_tier is distinct from plan_tier)
            or (prev_segment is distinct from segment)
            as integer
        ) as is_new_version
    from with_lags
),

versioned as (
    select
        *,
        sum(is_new_version) over (
            partition by customer_id order by updated_date
            rows between unbounded preceding and current row
        ) as version_number
    from changes_flagged
),

collapsed as (
    select
        customer_id,
        version_number,
        min(updated_date) as valid_from,
        max(email) as email,
        max(country) as country,
        max(plan_tier) as plan_tier,
        max(acquisition_channel) as acquisition_channel,
        max(segment) as segment,
        max(consent_flag) as consent_flag,
        min(created_date) as created_date
    from versioned
    group by customer_id, version_number
)

select
    customer_id,
    email,
    country,
    plan_tier,
    acquisition_channel,
    segment,
    consent_flag,
    created_date,
    valid_from,
    lead(valid_from) over customer_versions as valid_to,
    (lead(valid_from) over customer_versions is null) as is_current
from collapsed
window customer_versions as (partition by customer_id order by valid_from)
