{% snapshot customers_snapshot %}

{{
    config(
        target_schema='snapshots',
        unique_key='customer_id',
        strategy='check',
        check_cols=['country', 'plan_tier', 'segment'],
    )
}}

-- Configured and ready for genuinely incremental capture once this project's
-- customer source arrives incrementally rather than as a one-time bulk
-- historical load. Today, dim_customer's history comes from a direct SQL
-- reconstruction instead (see int_customer_history.sql) because a single
-- `dbt snapshot` invocation can only ever capture "state right now" -- it
-- cannot retroactively produce the ~2 years of history the source already
-- contains. This snapshot exists so the next real change, whenever one
-- actually lands through normal ingestion, is captured correctly.
--
-- `check` strategy, not `timestamp`: updated_date happens to be a reliable
-- cursor here (confirmed against the generator -- it's bumped by exactly
-- these three columns and nothing else), but comparing the business columns
-- directly doesn't depend on that continuing to hold if the source's own
-- bookkeeping ever drifts. That's the more defensive default for a column
-- dbt didn't produce itself.

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
    from {{ ref('stg_crm__customers') }}
    qualify row_number() over (
        partition by customer_id order by updated_date desc, customer_id asc
    ) = 1

{% endsnapshot %}
