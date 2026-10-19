-- One row per transaction, keyed to the dimensions. `effective_amount` is
-- the amount when the transaction is settled real cash (not money moved
-- into investments), else 0.

with

transactions as (

    select
        stg.*,
        installments.purchase_id
    from {{ ref('stg_transactions') }} as stg
    left join {{ ref('int_installment_transactions') }} as installments
        on stg.transaction_id = installments.transaction_id

)

select
    transaction_id,
    transaction_date,
    budget_month,
    side,
    description,
    coalesce(category_key, 'unknown') as category_key,
    case
        when owner is not null then {{ dbt_utils.generate_surrogate_key(['owner']) }}
    end as owner_key,
    case
        when payment_method is not null
            then {{ dbt_utils.generate_surrogate_key(['payment_method']) }}
    end as payment_method_key,
    purchase_id,
    amount,
    case when is_effective then amount else 0 end as effective_amount,
    case
        when not is_effective then 0
        when side = 'credit' then amount
        else -amount
    end as signed_effective_amount,
    is_settled,
    is_effective,
    is_dividend,
    is_investment_contribution,
    is_card_adjustment,
    is_installment,
    installment_number,
    installment_count,
    source_file,
    source_sheet,
    source_row
from transactions
