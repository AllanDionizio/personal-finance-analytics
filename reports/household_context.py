"""
A Markdown summary of the household's finances, in Portuguese, to give a
chat assistant the context behind a question (a fund to buy, a CDB to
compare) without explaining it again.

Reads the marts of a built warehouse and writes one file: profile and goals,
the last 12 closed months of income and spending, the portfolio, the liquid
reserve in the order to withdraw from, and the installments still owed. The
profile is a hand-written Markdown file (who the household is, what it wants)
included as is.

On the real warehouse the output holds real values: write it under
``data/personal/`` (gitignored), never anywhere committed.

CLI::

    python -m reports.household_context --db data/real.duckdb \\
        --profile data/personal/perfil.md --out data/personal/contexto.md
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import duckdb

MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

INCOME_GROUPS = {
    "Salary": "Salário",
    "Variable pay": "Remuneração variável",
    "Benefits": "Benefícios",
    "Business": "Empresa",
    "Dividends": "Proventos",
    "Asset sales": "Venda de ativos",
    "Other": "Outros",
}

ASSET_CLASSES = {
    "Fixed income": "Renda fixa",
    "Multimarket fund": "Multimercado",
    "Real estate fund": "FII",
    "Crypto": "Cripto",
    "Cash": "Saldo em conta",
    "Other": "Outros",
}


def brl(value: float | None) -> str:
    """R$ with Brazilian separators and no cents: ``R$ 1.234``."""
    if value is None:
        return "-"
    return "R$ " + f"{value:,.0f}".replace(",", ".")


def pct(value: float | None, digits: int = 1) -> str:
    """A rate as a percentage with a decimal comma: ``12,5%``."""
    if value is None:
        return "-"
    return f"{value * 100:.{digits}f}".replace(".", ",") + "%"


def month_label(value: date | None) -> str:
    """``set/2026``."""
    if value is None:
        return "-"
    return f"{MONTHS[value.month - 1]}/{value.year}"


def day_label(value: date | None) -> str:
    """``19/10/2026``, or empty."""
    return value.strftime("%d/%m/%Y") if value else ""


def _year_label(year: int, first: date, last: date) -> str:
    """``2026``, or ``2022 (desde set)`` / ``2026 (até out)`` for a partial year."""
    if year == first.year and first.month > 1:
        return f"{year} (desde {MONTHS[first.month - 1]})"
    if last.month < 12:
        return f"{year} (até {MONTHS[last.month - 1]})"
    return str(year)


def table(headers: list[str], rows: list[list[str]]) -> str:
    """A Markdown table."""
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def _goals(con: duckdb.DuckDBPyConnection) -> str:
    g = con.sql("select * from marts.fct_goals").fetchone()
    cols = [c[0] for c in con.sql("describe marts.fct_goals").fetchall()]
    g = dict(zip(cols, g, strict=True))
    next_goal = con.sql(
        """
        select month, new_money_goal
        from marts.fct_goal_tracking
        where new_money_goal is not null and month >= ?
        order by month
        limit 1
        """,
        params=[g["projection_from"]],
    ).fetchone()
    if g["new_money_goal"] is not None:
        goal_line = (
            f"- **Dinheiro novo por mês**: meta atual de {brl(g['new_money_goal'])}, subindo "
            "todo ano até o que a independência pede."
        )
    elif next_goal:
        goal_line = (
            f"- **Dinheiro novo por mês**: meta de {brl(next_goal[1])} a partir de "
            f"{month_label(next_goal[0])}, subindo todo ano até o que a independência pede."
        )
    else:
        goal_line = "- **Dinheiro novo por mês**: sem meta definida."

    return "\n".join(
        [
            "## Metas",
            "",
            f"- **Independência financeira**: meta de {brl(g['fi_target_value'])} "
            f"(custo de vida de {brl(g['fi_monthly_spending'])}/mês, retirando "
            f"{pct(g['fi_withdrawal_rate'], 0)} ao ano), em {month_label(g['fi_target_month'])}. "
            f"Patrimônio hoje: {brl(g['wealth'])} ({pct(g['fi_progress'])} da meta). "
            f"Pede {brl(g['required_monthly_new_money'])}/mês de dinheiro novo, com a carteira "
            f"rendendo {pct(g['fi_real_return'])} ao ano acima da inflação. A média dos últimos "
            f"12 meses é {brl(g['current_monthly_new_money'])}/mês; nesse ritmo chega em "
            f"{month_label(g['projected_fi_month'])}.",
            goal_line,
            f"- **Reserva de emergência**: {brl(g['reserve'])} de {brl(g['reserve_target'])} "
            f"({pct(g['reserve_progress'], 0)}); a meta é 6 meses do gasto médio.",
            "",
            "Valores a preços de hoje. Dinheiro novo é o que entra no patrimônio vindo de fora da "
            "carteira: poupança mais vendas de bens, menos proventos.",
        ]
    )


def _cashflow(con: duckdb.DuckDBPyConnection) -> str:
    first, last, income, dividends, spending, fixed, variable, savings, new_money = con.sql(
        """
        with recent as (
            select * from marts.fct_monthly_cashflow
            qualify row_number() over (order by budget_month desc) <= 12
        )
        select
            min(budget_month), max(budget_month), sum(income), sum(dividends),
            sum(spending), sum(fixed_spending), sum(variable_spending), sum(savings),
            sum(new_money)
        from recent
        """
    ).fetchone()
    summary = table(
        ["", "12 meses", "Por mês"],
        [
            [label, brl(value), brl(value / 12)]
            for label, value in [
                ("Renda (inclui proventos)", income),
                ("Proventos", dividends),
                ("Gastos", spending),
                ("Gastos fixos", fixed),
                ("Gastos variáveis", variable),
                ("Poupança (renda - gastos)", savings),
                ("Dinheiro novo", new_money),
            ]
        ],
    )
    by_group = con.sql(
        """
        select categories.income_group, sum(facts.effective_amount) as amount
        from marts.fct_transactions as facts
        inner join marts.dim_category as categories using (category_key)
        where facts.side = 'credit' and facts.budget_month between ? and ?
        group by 1
        order by 2 desc
        """,
        params=[first, last],
    ).fetchall()
    movers = con.sql(
        """
        select
            categories.category,
            sum(facts.effective_amount) filter (where facts.budget_month > ? - interval 12 months)
                as current_12m,
            sum(facts.effective_amount) filter (where facts.budget_month <= ? - interval 12 months)
                as prior_12m
        from marts.fct_transactions as facts
        inner join marts.dim_category as categories using (category_key)
        where facts.side = 'debit'
            and facts.budget_month <= ?
            and facts.budget_month > ? - interval 24 months
        group by 1
        order by current_12m desc nulls last
        limit 12
        """,
        params=[last, last, last, last],
    ).fetchall()
    return "\n".join(
        [
            f"## Renda e gastos, {month_label(first)} a {month_label(last)}",
            "",
            summary,
            "",
            f"Taxa de poupança: {pct(savings / income if income else None)}.",
            "",
            "### Renda por origem",
            "",
            table(
                ["Origem", "12 meses"],
                [
                    [INCOME_GROUPS.get(group, group or "-"), brl(amount)]
                    for group, amount in by_group
                ],
            ),
            "",
            "### Maiores categorias de gasto",
            "",
            table(
                ["Categoria", "12 meses", "12 meses anteriores"],
                [[category, brl(current), brl(prior)] for category, current, prior in movers],
            ),
        ]
    )


def _portfolio(con: duckdb.DuckDBPyConnection) -> str:
    latest, total, real_12m, return_12m, inflation_12m = con.sql(
        """
        select
            max(reference_date),
            arg_max(total_value, reference_date),
            arg_max(real_return_12m, reference_date) filter (where real_return_12m is not null),
            arg_max(return_12m, reference_date) filter (where return_12m is not null),
            arg_max(inflation_12m, reference_date) filter (where return_12m is not null)
        from marts.fct_net_worth
        """
    ).fetchone()
    by_class = con.sql(
        """
        select asset_class, sum(gross_value)
        from marts.fct_portfolio_snapshots
        where reference_date = ?
        group by 1
        order by 2 desc
        """,
        params=[latest],
    ).fetchall()
    by_year = con.sql(
        """
        -- a partial year says where it starts or ends
        select
            year(reference_date),
            (select min(reference_date) from marts.fct_net_worth) as first_date,
            reference_date,
            return_ytd,
            inflation_ytd
        from marts.fct_net_worth
        where return_ytd is not null
        qualify reference_date = max(reference_date) over (partition by year(reference_date))
        order by 1
        """
    ).fetchall()
    holdings = con.sql(
        """
        select bank, asset, asset_class, gross_value, maturity_date, is_liquid
        from marts.fct_portfolio_snapshots
        where reference_date = ? and gross_value > 0
        order by gross_value desc
        """,
        params=[latest],
    ).fetchall()
    return "\n".join(
        [
            f"## Carteira em {day_label(latest)}",
            "",
            f"Total: {brl(total)}. Retorno nos últimos 12 meses: {pct(return_12m)}, contra "
            f"{pct(inflation_12m)} de IPCA ({pct(real_12m)} acima da inflação).",
            "",
            "### Por classe",
            "",
            table(
                ["Classe", "Valor", "Participação"],
                [
                    [ASSET_CLASSES.get(asset_class, asset_class), brl(value), pct(value / total)]
                    for asset_class, value in by_class
                ],
            ),
            "",
            "### Retorno por ano",
            "",
            table(
                ["Ano", "Carteira", "IPCA"],
                [
                    [_year_label(year, first, last), pct(ret), pct(ipca)]
                    for year, first, last, ret, ipca in by_year
                ],
            ),
            "",
            "### Ativos",
            "",
            table(
                ["Banco", "Ativo", "Classe", "Valor", "Vencimento", "Liquidez diária"],
                [
                    [
                        bank,
                        asset,
                        ASSET_CLASSES.get(asset_class, asset_class),
                        brl(value),
                        day_label(maturity),
                        "sim" if liquid else "não",
                    ]
                    for bank, asset, asset_class, value, maturity, liquid in holdings
                ],
            ),
        ]
    )


def _reserve(con: duckdb.DuckDBPyConnection) -> str:
    rows = con.sql(
        """
        select withdrawal_order, bank, asset, gross_value, maturity_date, liquidity_note
        from marts.fct_portfolio_snapshots
        where reference_date = (select max(reference_date) from marts.fct_portfolio_snapshots)
            and withdrawal_order is not null
        order by withdrawal_order
        """
    ).fetchall()
    return "\n".join(
        [
            "## Reserva: de onde sacar, em ordem",
            "",
            table(
                ["Ordem", "Banco", "Ativo", "Valor", "Vencimento", "Observação"],
                [
                    [str(order), bank, asset, brl(value), day_label(maturity), note or ""]
                    for order, bank, asset, value, maturity, note in rows
                ],
            ),
        ]
    )


def _installments(con: duckdb.DuckDBPyConnection) -> str:
    owed, purchases, last = con.sql(
        """
        select
            sum(outstanding_amount),
            count(distinct purchase_id) filter (where outstanding_amount > 0),
            max(budget_month) filter (where outstanding_amount > 0)
        from marts.fct_installments
        """
    ).fetchone()
    return "\n".join(
        [
            "## Parcelas em aberto",
            "",
            f"{brl(owed)} em {purchases} compras; a última parcela cai em {month_label(last)}.",
        ]
    )


def build_context(con: duckdb.DuckDBPyConnection, profile: str | None, today: date) -> str:
    """The whole summary, from the marts of ``con``."""
    last_month = con.sql("select max(budget_month) from marts.fct_monthly_cashflow").fetchone()[0]
    sections = [
        "# Finanças da casa: contexto",
        "",
        f"Gerado em {day_label(today)} a partir das planilhas da casa, com os meses fechados até "
        f"{month_label(last_month)}. Valores em reais.",
        "",
        "## Perfil e objetivos",
        "",
        profile.strip() if profile else "(sem arquivo de perfil)",
        "",
        _goals(con),
        "",
        _cashflow(con),
        "",
        _portfolio(con),
        "",
        _reserve(con),
        "",
        _installments(con),
    ]
    return "\n".join(sections) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m reports.household_context",
        description="Write a Markdown summary of the household's finances from the marts.",
    )
    parser.add_argument("--db", type=Path, required=True, help="built DuckDB warehouse")
    parser.add_argument("--out", type=Path, required=True, help="Markdown file to write")
    parser.add_argument("--profile", type=Path, help="hand-written profile, included as is")
    args = parser.parse_args(argv)

    profile = args.profile.read_text() if args.profile and args.profile.exists() else None
    with duckdb.connect(str(args.db), read_only=True) as con:
        text = build_context(con, profile, date.today())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
