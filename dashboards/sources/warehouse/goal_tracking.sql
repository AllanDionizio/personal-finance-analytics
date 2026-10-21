-- One row per month up to the independence target: value in today's money,
-- new money against its goal, and the projections. Defined and tested in dbt
-- (fct_goal_tracking).
select *
from marts.fct_goal_tracking
order by month
