-- Type 2: one row per historical price version, same pattern as
-- dim_customer. Unlike stg_crm__customers, stg_catalog__product_prices is
-- already a clean event log (one row per real price change, verified: zero
-- consecutive rows share the same price for a product), so this builds
-- directly off it with no reconstruction step needed.

with products as (
    select * from {{ ref('stg_catalog__products') }}
),

prices as (
    select * from {{ ref('stg_catalog__product_prices') }}
),

versioned as (
    select
        product_id,
        price_amount_usd as list_price,
        effective_date as valid_from,
        lead(effective_date) over (
            partition by product_id order by effective_date
        ) as valid_to
    from prices
)

select
    {{ surrogate_key(['v.product_id', 'v.valid_from']) }} as product_key,
    v.product_id,
    p.name,
    p.category,
    v.list_price,
    v.valid_from,
    v.valid_to,
    (v.valid_to is null) as is_current
from versioned as v
inner join products as p on v.product_id = p.product_id
