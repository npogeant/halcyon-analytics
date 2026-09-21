-- Type 1 (overwrite): one row per product, current price only. Built for
-- AE-11's side-by-side comparison, not for production use -- see dim_product
-- for that. No history at all: an order placed before the last price change
-- gets banded by today's price when joined here, not the price actually
-- charged at the time.

with products as (
    select * from {{ ref('stg_catalog__products') }}
),

current_price as (
    select
        product_id,
        price_amount_usd as list_price
    from {{ ref('stg_catalog__product_prices') }}
    qualify row_number() over (
        partition by product_id order by effective_date desc
    ) = 1
)

select
    p.product_id,
    p.name,
    p.category,
    cp.list_price
from products as p
left join current_price as cp on p.product_id = cp.product_id
