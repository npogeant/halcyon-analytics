with source as (
    select * from {{ source('raw', 'orders') }}
),

casted as (
    select
        order_id,
        customer_id,
        cast(order_date as date) as order_date,
        status,
        cast(total_amount as decimal(18, 2)) as total_amount_usd,
        cast(_loaded_at as timestamptz) as loaded_at
    from source
),

deduplicated as (
    -- Resolves the injected ~0.1% duplicate-order_id defect. Duplicates in
    -- this dataset are byte-identical copies; the tie-break (earliest
    -- loaded_at, then order_id) is still deterministic and would resolve
    -- correctly against a real source where two "duplicate" rows disagree on
    -- some other column.
    select
        *,
        row_number() over (
            partition by order_id
            order by loaded_at asc, order_id asc
        ) as _dedup_rank
    from casted
)

select
    order_id,
    customer_id,
    order_date,
    status,
    total_amount_usd,
    loaded_at
from deduplicated
where _dedup_rank = 1
