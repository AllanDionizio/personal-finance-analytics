-- The English source (dashboards/sources/warehouse/transactions.sql) with
-- the marts' labels in Portuguese, and owners and cards under their display
-- names (DISPLAY_NAMES, see .env.real.example).
select
    f.transaction_id,
    f.transaction_date,
    f.budget_month,
    f.side,
    f.description,
    c.category,
    c.category_type,
    case c.macro_category
        when 'Fixed' then 'Fixo'
        when 'Variable' then 'Variável'
        when 'Not applicable' then 'Não se aplica'
        when 'Unknown' then 'Sem classificação'
        else c.macro_category
    end as macro_category,
    case c.income_group
        when 'Salary' then 'Salário'
        when 'Variable pay' then 'Remuneração variável'
        when 'Benefits' then 'Benefícios'
        when 'Business' then 'Empresa'
        when 'Dividends' then 'Proventos'
        when 'Asset sales' then 'Venda de ativos'
        when 'Other' then 'Outros'
        else c.income_group
    end as income_group,
    c.is_operating,
    case when o.owner = 'Other' then 'Outros' else o.display_name end as owner,
    case when p.payment_method = 'Other' then 'Outros' else p.display_name end as payment_method,
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
