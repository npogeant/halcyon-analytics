-- Fails (returns rows) if any two versions of the same product have
-- overlapping valid_from/valid_to ranges.

select
    a.product_id,
    a.product_key,
    a.valid_from as a_valid_from,
    a.valid_to as a_valid_to,
    b.product_key as b_product_key,
    b.valid_from as b_valid_from,
    b.valid_to as b_valid_to
from {{ ref('dim_product') }} as a
inner join {{ ref('dim_product') }} as b
    on
        a.product_id = b.product_id
        and a.product_key != b.product_key
        and a.valid_from < coalesce(b.valid_to, date '9999-12-31')
        and coalesce(a.valid_to, date '9999-12-31') > b.valid_from
