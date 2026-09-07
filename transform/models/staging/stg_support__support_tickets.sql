with source as (
    select * from {{ source('raw', 'support_tickets') }}
)

select
    ticket_id,
    customer_id,
    subject,
    -- Free-text status casing (e.g. "Open"/"open"/"OPEN") is left exactly as
    -- the source sent it. Normalizing it into a controlled vocabulary is
    -- AE-15's job, not this one -- staging renames and casts, it doesn't
    -- resolve business meaning.
    status,
    cast(created_at as date) as created_date,
    cast(_loaded_at as timestamptz) as loaded_at
from source
