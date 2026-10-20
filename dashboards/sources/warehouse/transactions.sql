-- One row per transaction, with the dimension labels joined in so pages
-- can filter and group without repeating the joins.
select
    f.transaction_id,
    f.transaction_date,
    f.budget_month,
    f.side,
    f.description,
    c.category,
    c.category_type,
    c.macro_category,
    o.owner,
    p.payment_method,
    f.amount,
    f.effective_amount,
    f.is_settled,
    f.is_effective,
    f.is_investment_contribution,
    f.is_dividend,
    f.is_card_adjustment,
    f.is_installment
from marts.fct_transactions as f
left join marts.dim_category as c on f.category_key = c.category_key
left join marts.dim_owner as o on f.owner_key = o.owner_key
left join marts.dim_payment_method as p on f.payment_method_key = p.payment_method_key
