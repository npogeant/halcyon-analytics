-- AE-11: proves the three list_price SCD strategies answer "revenue by
-- price band" differently. Bands are tertiles of the observed price
-- distribution ($150, $365) -- see docs/data-model.md's SCD comparison for
-- the full write-up of what each number means and why they differ.
--
-- Revenue is quantity * unit_price_usd, the actual transaction price
-- (matches docs/data-model.md section 4's revenue definition), computed
-- directly from order_items rather than a future fct_orders -- AE-11 has no
-- dependency on AE-12.

with order_lines as (
    select
        oi.product_id,
        o.order_date,
        oi.quantity * oi.unit_price_usd as revenue
    from {{ ref('stg_sales__order_items') }} as oi
    inner join {{ ref('stg_sales__orders') }} as o on oi.order_id = o.order_id
),

-- Type 1: every order banded by TODAY's price, regardless of order_date.
type1 as (
    select
        'type_1_overwrite' as scd_type,
        case
            when dp.list_price < 150 then 'budget'
            when dp.list_price < 365 then 'mid'
            else 'premium'
        end as price_band,
        sum(ol.revenue) as revenue
    from order_lines as ol
    inner join
        {{ ref('dim_product_type1') }} as dp
        on ol.product_id = dp.product_id
    group by scd_type, price_band
),

-- Type 2: every order banded by the price actually in effect on its own
-- order_date -- the historically correct answer, when one exists. This is a
-- left join, not inner: some products have orders that predate their
-- earliest recorded price (e.g. prd_026 has orders from 2024-09-14, but its
-- first price wasn't recorded until 2025-02-23). An inner join here would
-- silently drop that revenue from the report entirely -- a real Type 2
-- failure mode, not a query bug: point-in-time precision only works for
-- dates the dimension's history actually covers.
type2 as (
    select
        'type_2_scd' as scd_type,
        case
            when dp.product_id is null then 'no_price_recorded'
            when dp.list_price < 150 then 'budget'
            when dp.list_price < 365 then 'mid'
            else 'premium'
        end as price_band,
        sum(ol.revenue) as revenue
    from order_lines as ol
    left join {{ ref('dim_product') }} as dp
        on
            ol.product_id = dp.product_id
            and ol.order_date >= dp.valid_from
            and (dp.valid_to is null or ol.order_date < dp.valid_to)
    group by scd_type, price_band
),

-- Type 3: no date column exists to know when the current price took over,
-- so per-order history isn't answerable here at all. Banding every order by
-- previous_list_price instead stands in for a different, legitimate
-- question this model *can* answer: "what would revenue look like judged
-- entirely under the prior pricing scheme."
type3 as (
    select
        'type_3_previous_value' as scd_type,
        case
            when dp.previous_list_price is null then 'no_prior_price'
            when dp.previous_list_price < 150 then 'budget'
            when dp.previous_list_price < 365 then 'mid'
            else 'premium'
        end as price_band,
        sum(ol.revenue) as revenue
    from order_lines as ol
    inner join
        {{ ref('dim_product_type3') }} as dp
        on ol.product_id = dp.product_id
    group by scd_type, price_band
)

select * from type1
union all
select * from type2
union all
select * from type3
order by scd_type, price_band
