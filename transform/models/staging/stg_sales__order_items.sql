with source as (
    select * from {{ source('raw', 'order_items') }}
)

select
    order_item_id,
    order_id,
    product_id,
    quantity,
    cast(unit_price as decimal(18, 2)) as unit_price_usd,
    cast(_loaded_at as timestamptz) as loaded_at
from source
