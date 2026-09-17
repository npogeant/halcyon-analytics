-- Fails (returns rows) if any customer_id has a count of is_current rows
-- other than exactly one.

select
    customer_id,
    count(*) as current_row_count
from {{ ref('dim_customer') }}
where is_current
group by customer_id
having count(*) != 1
