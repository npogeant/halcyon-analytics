with source as (
    select * from {{ source('raw', 'refunds') }}
)

select
    refund_id,
    payment_id,
    {{ cents_to_decimal('amount_cents') }} as amount_usd,
    reason,
    cast(refunded_at as date) as refunded_date,
    cast(_loaded_at as timestamptz) as loaded_at
from source
