-- Model config (materialized, contract) lives in dim_customer.yml, not here --
-- keeps everything about this model's contract in one file, next to the
-- column types it governs.

-- Real Type 2 dimension, replacing AE-09's minimal current-state-only
-- placeholder. History comes from int_customer_history's one-time SQL
-- reconstruction, not from customers_snapshot directly -- see that model's
-- header comment for why a single dbt snapshot invocation can't supply it.
--
-- valid_to uses NULL for the current version, not a 9999-12-31 sentinel:
-- paired with the explicit is_current boolean, "give me today's state" is
-- just `where is_current`, no NULL-handling needed. An arbitrary as-of query
-- does need to handle it: `valid_from <= :as_of and (valid_to is null or
-- valid_to > :as_of)`.

with history as (
    select * from {{ ref('int_customer_history') }}
),

with_surrogate_key as (
    select
        {{ surrogate_key(['customer_id', 'valid_from']) }} as customer_key,
        customer_id,
        email,
        country,
        plan_tier,
        acquisition_channel,
        segment,
        consent_flag,
        created_date,
        valid_from,
        valid_to,
        is_current
    from history
),

-- Unknown member: a fact row with a missing/unresolvable customer_id still
-- joins to this instead of being silently dropped by an inner join. The real
-- surrogate keys are hashes (varchar), not auto-incrementing integers, so
-- '-1' here is a literal sentinel string in that same column, not a real
-- integer -1 -- matching the convention's intent (an unmistakable, reserved
-- key value) within the type this project's surrogate keys actually use.
unknown_member as (
    select
        '-1' as customer_key,
        'unknown' as customer_id,
        cast(null as varchar) as email,
        cast(null as varchar) as country,
        cast(null as varchar) as plan_tier,
        cast(null as varchar) as acquisition_channel,
        cast(null as varchar) as segment,
        cast(null as boolean) as consent_flag,
        cast(null as date) as created_date,
        date '1900-01-01' as valid_from,
        cast(null as date) as valid_to,
        true as is_current
)

select * from with_surrogate_key
union all
select * from unknown_member
