-- One row per closed budget month. The metrics are defined and tested in
-- dbt (fct_monthly_cashflow); this only adds the year label pages group by.
select
    *,
    strftime(budget_month, '%Y') as budget_year
from marts.fct_monthly_cashflow
order by budget_month
