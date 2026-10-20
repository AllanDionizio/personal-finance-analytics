-- One row per installment of every purchase, including the ones that fall
-- outside the workbooks' years. Answers "how much is still owed": the sum of
-- `outstanding_amount`.
--
-- Every installment before the as-of month (the newest month with a settled
-- transaction) counts as paid: in the sheets a past installment is always
-- paid, so a leftover 'Não' is a typing slip, and installments before 2021
-- aren't in any workbook. From the as-of month on, a recorded installment
-- keeps its status, and one past the newest workbook is outstanding.

with

purchases as (

    select * from {{ ref('int_installment_purchases') }}

),

as_of as (

    {{ as_of_month() }}

),

recorded as (

    select
        transaction_id,
        purchase_id,
        installment_number,
        is_settled
    from {{ ref('int_installment_transactions') }}

),

schedule as (

    select
        *,
        unnest(range(1, installment_count + 1)) as installment_number
    from purchases

),

installments as (

    select
        schedule.purchase_id,
        schedule.installment_number,
        schedule.installment_count,
        cast(
            schedule.first_budget_month + to_months(schedule.installment_number - 1) as date
        ) as budget_month,
        schedule.description,
        schedule.category_key,
        schedule.payment_method,
        schedule.installment_amount as amount,
        recorded.transaction_id,
        recorded.transaction_id is not null as is_recorded,
        recorded.is_settled as recorded_is_settled
    from schedule
    left join recorded
        on
            schedule.purchase_id = recorded.purchase_id
            and schedule.installment_number = recorded.installment_number

),

settled as (

    select
        installments.*,
        installments.budget_month < as_of.as_of_month
        or coalesce(installments.recorded_is_settled, false) as is_settled
    from installments
    cross join as_of

)

select
    {{ dbt_utils.generate_surrogate_key(['purchase_id', 'installment_number']) }}
        as installment_id,
    purchase_id,
    installment_number,
    installment_count,
    budget_month,
    description,
    coalesce(category_key, 'unknown') as category_key,
    {{ dbt_utils.generate_surrogate_key(['payment_method']) }} as payment_method_key,
    transaction_id,
    amount,
    case when is_settled then 0 else amount end as outstanding_amount,
    is_recorded,
    is_settled
from settled
