-- Grain: one row per order line -- (order_id, order_item_id). Order-level
-- attributes (shipping_cost, discount_amount, refund_amount) don't live at
-- this grain naturally; they're allocated down to each line using the same
-- rule throughout (pro-rata by the line's share of the order's gross
-- revenue), with the rounding remainder assigned to the order's last line
-- (by order_item_id) instead of split evenly, so every order's lines sum
-- back to the order-level amount exactly, not just within a few cents.
--
-- order_id and status are degenerate dimensions: kept directly on the fact
-- rather than modeled as their own dim_order table, since neither carries
-- any further descriptive attributes -- a dim_order table would just be
-- order_id and status again, with nothing else to justify the join.
--
-- order_date_key and shipped_date_key are both role-playing references to
-- the same dim_date table: one physical dimension, two logical roles.

with order_lines as (
    select
        oi.order_id,
        oi.order_item_id,
        oi.product_id,
        oi.quantity,
        oi.unit_price_usd,
        oi.quantity * oi.unit_price_usd as gross_amount_usd
    from {{ ref('stg_sales__order_items') }} as oi
),

order_line_totals as (
    select
        order_id,
        sum(gross_amount_usd) as order_gross_amount_usd,
        count(*) as line_count
    from order_lines
    group by order_id
),

orders_context as (
    select
        order_id,
        customer_id,
        order_date,
        status,
        shipping_cost_usd as order_shipping_cost_usd,
        discount_amount_usd as order_discount_amount_usd,
        shipped_date
    from {{ ref('stg_sales__orders') }}
),

refunds_by_order as (
    -- Refunds reference payment_id, not an order line -- payments.order_id
    -- is the only link back to an order. Every refund in this dataset is a
    -- full refund (confirmed against the generator), but this sums rather
    -- than assumes exactly one row, so it stays correct if that ever changes.
    select
        p.order_id,
        sum(r.amount_usd) as order_refund_amount_usd
    from {{ ref('stg_billing__refunds') }} as r
    inner join
        {{ ref('stg_billing__payments') }} as p
        on r.payment_id = p.payment_id
    where p.order_id is not null
    group by p.order_id
),

lines_with_shares as (
    select
        ol.*,
        olt.order_gross_amount_usd,
        olt.line_count,
        oc.customer_id,
        oc.order_date,
        oc.status,
        oc.order_shipping_cost_usd,
        oc.order_discount_amount_usd,
        oc.shipped_date,
        coalesce(rbo.order_refund_amount_usd, 0) as order_refund_amount_usd,
        row_number() over (
            partition by ol.order_id order by ol.order_item_id
        ) as line_rank
    from order_lines as ol
    inner join order_line_totals as olt on ol.order_id = olt.order_id
    inner join orders_context as oc on ol.order_id = oc.order_id
    left join refunds_by_order as rbo on ol.order_id = rbo.order_id
),

-- Pro-rata each order-level amount by the line's share of gross revenue,
-- rounded to the cent.
allocated_raw as (
    select
        *,
        round(
            order_shipping_cost_usd
            * (gross_amount_usd / order_gross_amount_usd),
            2
        ) as raw_shipping_amount_usd,
        round(
            order_discount_amount_usd
            * (gross_amount_usd / order_gross_amount_usd),
            2
        ) as raw_discount_amount_usd,
        round(
            order_refund_amount_usd
            * (gross_amount_usd / order_gross_amount_usd),
            2
        ) as raw_refunded_amount_usd
    from lines_with_shares
),

-- The last line of each order absorbs whatever rounding remainder the other
-- lines' pro-rata shares left behind, so the allocated lines always
-- reconcile to the order-level amount exactly.
allocated as (
    select
        *,
        case
            when line_rank = line_count
                then order_shipping_cost_usd - coalesce(
                    sum(raw_shipping_amount_usd) filter (
                        where line_rank < line_count
                    )
                        over (partition by order_id),
                    0
                )
            else raw_shipping_amount_usd
        end as shipping_amount_usd,
        case
            when line_rank = line_count
                then order_discount_amount_usd - coalesce(
                    sum(raw_discount_amount_usd) filter (
                        where line_rank < line_count
                    )
                        over (partition by order_id),
                    0
                )
            else raw_discount_amount_usd
        end as discount_amount_usd,
        case
            when line_rank = line_count
                then order_refund_amount_usd - coalesce(
                    sum(raw_refunded_amount_usd) filter (
                        where line_rank < line_count
                    )
                        over (partition by order_id),
                    0
                )
            else raw_refunded_amount_usd
        end as refunded_amount_usd
    from allocated_raw
)

select
    a.order_id,
    a.order_item_id,
    a.status,
    a.order_date as order_date_key,
    a.shipped_date as shipped_date_key,
    a.quantity,
    cast(a.gross_amount_usd as decimal(18, 2)) as gross_amount_usd,
    cast(a.discount_amount_usd as decimal(18, 2)) as discount_amount_usd,
    -- Explicit casts throughout: bigint * decimal(18,2) widens to
    -- decimal(37,2) in DuckDB (defensive against overflow), and dividing two
    -- decimals produces a plain DOUBLE -- neither matches the contract's
    -- exact decimal(18,2) without an explicit cast back down.
    cast(
        a.gross_amount_usd - a.discount_amount_usd as decimal(18, 2)
    ) as net_amount_usd,
    cast(a.shipping_amount_usd as decimal(18, 2)) as shipping_amount_usd,
    cast(a.refunded_amount_usd as decimal(18, 2)) as refunded_amount_usd,
    cast(
        round(a.quantity * coalesce(dp.cost_amount, 0), 2) as decimal(18, 2)
    ) as cost_amount_usd,
    coalesce(dc.customer_key, '-1') as customer_key,
    coalesce(dp.product_key, '-1') as product_key
from allocated as a
left join {{ ref('dim_customer') }} as dc
    on
        a.customer_id = dc.customer_id
        and a.order_date >= dc.valid_from
        and (dc.valid_to is null or a.order_date < dc.valid_to)
left join {{ ref('dim_product') }} as dp
    on
        a.product_id = dp.product_id
        and a.order_date >= dp.valid_from
        and (dp.valid_to is null or a.order_date < dp.valid_to)
