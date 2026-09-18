-- Fails (returns rows) if any two versions of the same customer have
-- overlapping valid_from/valid_to ranges. A customer's history should be a
-- clean, non-overlapping timeline: at any given date, exactly one version
-- should be in effect.

select
    a.customer_id,
    a.customer_key,
    a.valid_from as a_valid_from,
    a.valid_to as a_valid_to,
    b.customer_key as b_customer_key,
    b.valid_from as b_valid_from,
    b.valid_to as b_valid_to
from {{ ref('dim_customer') }} as a
inner join {{ ref('dim_customer') }} as b
    on
        a.customer_id = b.customer_id
        and a.customer_key != b.customer_key
        and a.valid_from < coalesce(b.valid_to, date '9999-12-31')
        and coalesce(a.valid_to, date '9999-12-31') > b.valid_from
