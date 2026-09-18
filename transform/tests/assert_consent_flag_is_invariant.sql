-- int_customer_history.sql treats consent_flag as a plain attribute rather
-- than a version-boundary column, on the assumption that it never actually
-- changes for a given customer once known. This guards that assumption:
-- fails (returns rows) if any customer's known consent_flag values ever
-- disagree with each other.

select customer_id
from {{ ref('stg_crm__customers') }}
where consent_flag is not null
group by customer_id
having count(distinct consent_flag) > 1
