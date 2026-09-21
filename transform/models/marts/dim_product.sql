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
        -- No real COGS system exists in this dataset -- cost_amount is a
        -- documented business assumption (60% gross margin), not sourced
        -- data, applied consistently across every price version so a
        -- product's margin stays constant even as its price changes.
        -- AE-12 needs this on the dimension, not computed inline in
        -- fct_orders, since a product's cost basis is an attribute of the
        -- product, not something a fact table should recompute per row.
        effective_date as valid_from,
        round(price_amount_usd * 0.40, 2) as cost_amount,
        lead(effective_date) over (
            partition by product_id order by effective_date
        ) as valid_to
    from prices
),

with_surrogate_key as (
    select
        {{ surrogate_key(['v.product_id', 'v.valid_from']) }} as product_key,
        v.product_id,
        p.name,
        p.category,
        v.list_price,
        v.cost_amount,
        v.valid_from,
        v.valid_to,
        (v.valid_to is null) as is_current
    from versioned as v
    inner join products as p on v.product_id = p.product_id
),

-- Unknown member: AE-12's fct_orders needs this. AE-11 already found some
-- products have orders that predate their earliest recorded price (e.g.
-- prd_026 has orders from 2024-09-14, no price on record until
-- 2025-02-23) -- an as-of join for those lines finds no match here, and
-- this is what they fall back to instead of a null product_key.
unknown_member as (
    select
        '-1' as product_key,
        'unknown' as product_id,
        cast(null as varchar) as name, -- noqa: RF04
        cast(null as varchar) as category,
        cast(null as decimal(18, 2)) as list_price,
        cast(null as decimal(18, 2)) as cost_amount,
        date '1900-01-01' as valid_from,
        cast(null as date) as valid_to,
        true as is_current
)

select * from with_surrogate_key
union all
select * from unknown_member
