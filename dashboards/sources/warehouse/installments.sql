-- One row per installment of every purchase, including the ones that fall
-- after the last workbook; outstanding_amount is what is still owed.
select
    i.installment_id,
    i.purchase_id,
    i.description,
    i.installment_number,
    i.installment_count,
    i.budget_month,
    c.category,
    p.payment_method,
    i.amount,
    i.outstanding_amount,
    i.is_recorded,
    i.is_settled
from marts.fct_installments as i
left join marts.dim_category as c on i.category_key = c.category_key
left join marts.dim_payment_method as p on i.payment_method_key = p.payment_method_key
