with source as (
    select * from {{ source('raw', 'web_events') }}
)

select
    event_id,
    customer_id,
    session_id,
    event_type,
    {{ to_utc('event_at') }} as event_at,
    product_id,
    url,
    channel,
    device,
    -- geo stays JSON, not flattened -- see ingestion/README.md for why.
    -- json_extract_string promotes the one attribute currently in use to a real
    -- column without discarding the underlying JSON, so a future key added
    -- inside geo needs no model change here.
    json_extract_string(geo, '$.country') as geo_country,
    utm_campaign,
    cast(_partition_date as date) as partition_date,
    cast(_loaded_at as timestamptz) as loaded_at
from source
