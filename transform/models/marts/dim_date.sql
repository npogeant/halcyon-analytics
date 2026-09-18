{{
  config(
    materialized='table',
    contract={'enforced': true}
  )
}}

-- One row per calendar day, covering the generator's full history
-- (2024-09-01 to 2026-08-31) plus one year forward, per AE-10's scope.
-- "Main market" for is_holiday is deliberately US: the brief never states
-- one, and this project has no real company to inherit a market from, so
-- this is a documented choice, not an assumption left implicit.

with spine as (
    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('2024-09-01' as date)",
        end_date="cast('2027-09-01' as date)"
    ) }}
),

-- dbt_utils.date_spine's output is a TIMESTAMP under the hood (its dateadd
-- macro is generic across day/hour/minute granularities) -- cast to DATE
-- once here rather than repeating the cast on every derived column below.
spine_dates as (
    select cast(date_day as date) as date_day
    from spine
),

holidays as (
    select
        holiday_date,
        holiday_name
    from {{ ref('us_federal_holidays') }}
)

select
    spine_dates.date_day as date_key,
    holidays.holiday_name,
    -- year/month/quarter aren't reserved in DuckDB (verified directly) and
    -- are the standard names for these columns in any date dimension;
    -- renaming them to dodge a style lint would hurt readability for no
    -- real benefit.
    extract(year from spine_dates.date_day) as year, -- noqa: RF04
    extract(quarter from spine_dates.date_day) as quarter, -- noqa: RF04
    extract(month from spine_dates.date_day) as month, -- noqa: RF04
    strftime(spine_dates.date_day, '%B') as month_name,
    extract(day from spine_dates.date_day) as day_of_month,
    -- ISO day of week: 1 = Monday .. 7 = Sunday.
    isodow(spine_dates.date_day) as iso_day_of_week,
    strftime(spine_dates.date_day, '%A') as day_name,
    extract(week from spine_dates.date_day) as iso_week,
    -- Fiscal year assumed to align with the calendar year (Jan-Dec) -- a
    -- documented simplification, not a real fiscal calendar. A company with
    -- an offset fiscal year (e.g. starting April) would need these computed
    -- from a shifted month instead of the raw calendar month/quarter.
    (isodow(spine_dates.date_day) in (6, 7)) as is_weekend,
    extract(year from spine_dates.date_day) as fiscal_year,
    extract(quarter from spine_dates.date_day) as fiscal_quarter,
    (holidays.holiday_date is not null) as is_holiday
from spine_dates
left join holidays on spine_dates.date_day = holidays.holiday_date
