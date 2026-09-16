-- Model config (materialized, unique_key, on_schema_change, contract) lives in
-- dim_customer.yml, not here -- keeps everything about this model's contract
-- in one file, next to the column types it governs.

-- MINIMAL placeholder: current state per customer only, no SCD2 history yet.
-- AE-10 replaces this with the real Type 2 version, built on a dbt snapshot.
-- This exists now specifically to have a real mart to enforce AE-09's
-- contract on -- staging still carries all 24 monthly snapshots per
-- customer (AE-07 kept the full history for exactly that later use).

with source as (
    select stg.* from {{ ref('stg_crm__customers') }} as stg
    {% if is_incremental() %}
    -- Only re-process customers whose latest known change is newer than what
    -- this table already has -- an unchanged customer's existing row is left
    -- alone. Safe because every snapshot after a customer's last real change
    -- carries identical values forward (see AE-02's generator), so picking
    -- any one of them for a given customer_id gives the same result.
        where stg.updated_date > (
            select coalesce(max(prior_load.updated_date), date '1900-01-01')
            from {{ this }} as prior_load
        )
    {% endif %}
),

ranked as (
    select
        *,
        row_number() over (
            partition by customer_id
            order by updated_date desc, customer_id asc
        ) as _rank
    from source
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
    updated_date
from ranked
where _rank = 1
