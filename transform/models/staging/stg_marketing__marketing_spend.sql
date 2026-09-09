with source as (
    select * from {{ source('raw', 'marketing_spend') }}
)

select
    cast(date as date) as spend_date,
    channel,
    -- currency is always USD in this dataset (checked, not assumed); the unit
    -- is named in the column instead of carrying a separate currency column
    -- that never varies.
    cast(spend as decimal(18, 2)) as spend_amount_usd,
    cast(_loaded_at as timestamptz) as loaded_at
from source
