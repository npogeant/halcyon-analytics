-- Type 3 (previous-value column): one row per product, current price plus
-- one step of history. Built for AE-11's side-by-side comparison, not for
-- production use -- see dim_product for that.
--
-- Note what this genuinely can't do: there's no date column recording when
-- the current price took effect, so nothing here can tell you whether a
-- given historical order should be banded by list_price or
-- previous_list_price. It can only support a before/after comparison in
-- aggregate ("what would revenue look like under the prior price scheme"),
-- not a true point-in-time reconstruction the way dim_product (Type 2) can.

with products as (
    select * from {{ ref('stg_catalog__products') }}
),

ranked_prices as (
    select
        product_id,
        price_amount_usd,
        row_number() over (
            partition by product_id order by effective_date desc
        ) as price_rank
    from {{ ref('stg_catalog__product_prices') }}
),

current_price as (
    select
        product_id,
        price_amount_usd as list_price
    from ranked_prices
    where price_rank = 1
),

previous_price as (
    select
        product_id,
        price_amount_usd as previous_list_price
    from ranked_prices
    where price_rank = 2
)

select
    p.product_id,
    p.name,
    p.category,
    cp.list_price,
    pp.previous_list_price
from products as p
left join current_price as cp on p.product_id = cp.product_id
left join previous_price as pp on p.product_id = pp.product_id
