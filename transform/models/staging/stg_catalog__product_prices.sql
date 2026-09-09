with source as (
    select * from {{ source('raw', 'product_prices') }}
)

select
    product_id,
    cast(price_amount as decimal(18, 2)) as price_amount_usd,
    cast(effective_date as date) as effective_date,
    cast(_loaded_at as timestamptz) as loaded_at
from source
