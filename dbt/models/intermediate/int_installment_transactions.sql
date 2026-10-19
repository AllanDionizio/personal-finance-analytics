-- Installment debits of stg_transactions, each tagged with the purchase it
-- belongs to. Credits are left out: an income received in installments is
-- not something owed. A purchase is identified by what every one of its rows
-- shares: description, category, payment method, installment count,
-- amount and the month of the first installment. The date is left out: a
-- bill paid in installments (e.g. IPTU) carries each payment's own date.

with

installments as (

    select
        *,
        cast(budget_month - to_months(installment_number - 1) as date) as first_budget_month
    from {{ ref('stg_transactions') }}
    where is_installment and side = 'debit'

)

select
    transaction_id,
    {{ dbt_utils.generate_surrogate_key([
        'description',
        'category',
        'payment_method',
        'installment_count',
        'amount',
        'first_budget_month',
    ]) }} as purchase_id,
    installment_number,
    installment_count,
    first_budget_month,
    budget_month,
    transaction_date,
    description,
    category_key,
    category,
    payment_method,
    amount,
    is_settled
from installments
