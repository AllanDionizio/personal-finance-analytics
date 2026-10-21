-- The required path ends on the independence target in the target month,
-- and the current pace path crosses the target in the projected month (when
-- that comes before the target month, inside fct_goal_tracking).

with

goals as (

    select * from {{ ref('fct_goals') }}

),

tracking as (

    select * from {{ ref('fct_goal_tracking') }}

)

select
    'required path misses the target' as failure,
    tracking.month
from tracking
cross join goals
where
    goals.months_to_target > 0
    and tracking.month = goals.fi_target_month
    and abs(tracking.required_path - goals.fi_target_value) > 1

union all

select
    'current pace crosses the target in another month' as failure,
    tracking.month
from tracking
cross join goals
where
    goals.projected_fi_month <= goals.fi_target_month
    and goals.projected_fi_month > goals.projection_from
    and (
        (tracking.month = goals.projected_fi_month
            and tracking.current_pace_path < goals.fi_target_value)
        or (tracking.month = goals.projected_fi_month - interval 1 month
            and tracking.current_pace_path >= goals.fi_target_value)
    )
