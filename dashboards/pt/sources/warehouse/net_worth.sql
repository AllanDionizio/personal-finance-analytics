-- The English source (dashboards/sources/warehouse/net_worth.sql) with the
-- reserve status in Portuguese.
select
    * replace (
        case reserve_status
            when 'Below target' then 'Abaixo da meta'
            when 'Within target' then 'Dentro da meta'
            when 'Above target' then 'Acima da meta'
            else reserve_status
        end as reserve_status
    )
from marts.fct_net_worth
order by reference_date
