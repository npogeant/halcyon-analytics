-- Fails (returns rows) if any product_id has a count of is_current rows
-- other than exactly one.

select
    product_id,
    count(*) as current_row_count
from {{ ref('dim_product') }}
where is_current
group by product_id
having count(*) != 1
