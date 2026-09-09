with source as (
    select * from {{ source('raw', 'payments') }}
)

select
    payment_id,
    customer_id,
    order_id,
    subscription_id,
    {{ cents_to_decimal('amount_cents') }} as amount_usd,
    method,
    cast(paid_at as date) as paid_date,
    cast(_loaded_at as timestamptz) as loaded_at
from source
