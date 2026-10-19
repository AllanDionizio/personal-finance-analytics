-- One row per installment of every purchase, including the ones that fall
-- outside the workbooks' years. Answers "how much is still owed": the sum of
-- `outstanding_amount`. An installment not in the workbooks is settled if it
-- comes before the first recorded one (paid before 2021) and outstanding if
-- it comes after the last (due after the newest workbook).

with

purchases as (

    select * from {{ ref('int_installment_purchases') }}

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
        coalesce(
            recorded.is_settled,
            schedule.installment_number < schedule.first_recorded_installment
        ) as is_settled
    from schedule
    left join recorded
        on
            schedule.purchase_id = recorded.purchase_id
            and schedule.installment_number = recorded.installment_number

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
from installments
