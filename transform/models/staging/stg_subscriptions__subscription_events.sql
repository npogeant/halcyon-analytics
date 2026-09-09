with source as (
    select * from {{ source('raw', 'subscription_events') }}
)

select
    subscription_event_id,
    subscription_id,
    event_type,
    cast(event_at as date) as event_date,
    cast(_loaded_at as timestamptz) as loaded_at
from source
