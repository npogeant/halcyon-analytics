-- Acceptance criteria: "summing allocated line amounts reproduces order
-- totals to the cent." net_amount_usd + shipping_amount_usd per line, summed
-- back up to the order, should equal the order's own total_amount_usd
-- (which is items_total + shipping_cost - discount_amount by construction --
-- see the orders generator). Fails (returns rows) if any order is off by
-- more than one cent, which would mean the allocation logic itself is wrong,
-- not just a rounding artifact.

with allocated_totals as (
    select
        order_id,
        sum(net_amount_usd + shipping_amount_usd) as allocated_total_usd
    from {{ ref('fct_orders') }}
    group by order_id
)

select
    o.order_id,
    o.total_amount_usd,
    a.allocated_total_usd,
    abs(o.total_amount_usd - a.allocated_total_usd) as difference_usd
from {{ ref('stg_sales__orders') }} as o
inner join allocated_totals as a on o.order_id = a.order_id
where abs(o.total_amount_usd - a.allocated_total_usd) > 0.01
