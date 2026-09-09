with source as (
    select * from {{ source('raw', 'customers') }}
)

select
    customer_id,
    email,
    country,
    plan_tier,
    acquisition_channel,
    -- added by the 2025-09-01 schema change; null on rows loaded under the
    -- old schema.
    consent_flag,
    cast(created_at as date) as created_date,
    cast(updated_at as date) as updated_date,
    cast(_loaded_at as timestamptz) as loaded_at,
    -- the 2025-09-01 schema change renamed marketing_segment -> segment;
    -- coalesce resolves it into one output column.
    coalesce(segment, marketing_segment) as segment
from source
