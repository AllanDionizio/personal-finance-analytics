-- One row per day, 2020-01-01 to 2030-12-31: covers the workbooks and the
-- installments that run past the last one.

with

days as (

    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('2020-01-01' as date)",
        end_date="cast('2031-01-01' as date)",
    ) }}

)

select
    cast(date_day as date) as date_day,
    year(date_day) as year,
    quarter(date_day) as quarter,
    month(date_day) as month,
    strftime(date_day, '%B') as month_name,
    cast(date_trunc('month', date_day) as date) as first_day_of_month,
    cast(last_day(date_day) as date) as last_day_of_month,
    isodow(date_day) as day_of_week,
    strftime(date_day, '%A') as day_name,
    isodow(date_day) in (6, 7) as is_weekend
from days
