-- The English source (dashboards/sources/warehouse/installments.sql) with
-- cards under their display names.
select
    i.installment_id,
    i.purchase_id,
    i.description,
    i.installment_number,
    i.installment_count,
    i.budget_month,
    c.category,
    case when p.payment_method = 'Other' then 'Outros' else p.display_name end as payment_method,
    i.amount,
    i.outstanding_amount,
    i.is_recorded,
    i.is_settled
from marts.fct_installments as i
left join marts.dim_category as c on i.category_key = c.category_key
left join marts.dim_payment_method as p on i.payment_method_key = p.payment_method_key
