-- One row per purchase paid in installments, rebuilt from its installment
-- rows. The workbooks only hold the installments that fall inside their
-- years: a purchase from late 2020 is missing its first installments, and
-- one from late 2026 its last ones. This model knows the whole plan, so
-- fct_installments can lay out every installment, recorded or not.

select
    purchase_id,
    description,
    category_key,
    category,
    payment_method,
    installment_count,
    amount as installment_amount,
    amount * installment_count as total_amount,
    first_budget_month,
    cast(first_budget_month + to_months(installment_count - 1) as date) as last_budget_month,
    min(transaction_date) as first_transaction_date,
    count(*) as recorded_installments,
    min(installment_number) as first_recorded_installment,
    max(installment_number) as last_recorded_installment
from {{ ref('int_installment_transactions') }}
group by all
