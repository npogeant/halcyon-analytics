with source as (
    select * from {{ source('raw', 'products') }}
)

select
    product_id,
    name,
    category,
    cast(created_at as date) as created_date,
    cast(_loaded_at as timestamptz) as loaded_at
from source
