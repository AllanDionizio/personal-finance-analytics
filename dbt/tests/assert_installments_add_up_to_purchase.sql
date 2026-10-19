-- The installments laid out for a purchase add up to its total, so no
-- installment is missing or doubled in fct_installments.

with

laid_out as (

    select
        purchase_id,
        count(*) as n_installments,
        sum(amount) as total_amount
    from {{ ref('fct_installments') }}
    group by purchase_id

)

select
    purchases.purchase_id,
    purchases.installment_count,
    laid_out.n_installments,
    purchases.total_amount,
    laid_out.total_amount as laid_out_amount
from {{ ref('int_installment_purchases') }} as purchases
left join laid_out
    on purchases.purchase_id = laid_out.purchase_id
where
    laid_out.n_installments is distinct from purchases.installment_count
    or laid_out.total_amount is distinct from purchases.total_amount
