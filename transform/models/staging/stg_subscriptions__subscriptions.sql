with source as (
    select * from {{ source('raw', 'subscriptions') }}
)

select
    subscription_id,
    customer_id,
    plan,
    status,
    cast(started_at as date) as started_date,
    cast(updated_at as date) as updated_date,
    cast(_loaded_at as timestamptz) as loaded_at
from source
