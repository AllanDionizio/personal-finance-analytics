-- One row per portfolio snapshot: value, flows, return against inflation and
-- the liquid reserve. Defined and tested in dbt (fct_net_worth).
select *
from marts.fct_net_worth
order by reference_date
