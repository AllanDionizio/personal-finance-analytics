"""
Static reference data for the synthetic workbooks.

Everything here mirrors the *shape* of the real spreadsheets (sheet and
header names, category list, color codes) without any of their content.
Text that ends up inside the workbooks stays in Portuguese on purpose: the
source system is Portuguese, and translating it is the staging layer's job.
"""

from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------------------
# Cell colors (ARGB). Owner and card are encoded as background colors.
# --------------------------------------------------------------------------

PERSON_A_RGB = "FF4BACC6"
PERSON_A_THEME = 8  # accent5 in the default Office theme → 4BACC6
PERSON_B_RGB = "FFF79646"
PERSON_B_THEME = 9  # accent6 → F79646
NEUTRAL_RGB = "FFFFFFFF"

CARD_A_RGB = "FFB4A7D6"
CARD_B_RGB = "FF8E7CC3"
CARD_C_RGB = "FF9FC5E8"
CARD_C_SINCE_YEAR = 2022

# A manual highlight the owners sometimes left on cells. It maps to no
# dimension, so the ingestion logs it as an unrecognized color.
STRAY_HIGHLIGHT_RGB = "FFFFFF00"

# --------------------------------------------------------------------------
# Calendar
# --------------------------------------------------------------------------

MONTH_SHEETS = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]
MONTH_NAMES = [
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
]

# --------------------------------------------------------------------------
# Category configuration ("Configurações" sheet of the newest workbook)
# --------------------------------------------------------------------------

INCOME_CATEGORIES = [
    "Salário",
    "Décimo Terceiro",
    "Férias",
    "Vale",
    "Emprestimos",
    "Diversos",
    "Investimentos",
    "Presentes",
    "Comissão",
    "Auxílio",
    "Seguro",
    "PLR",
    "Freelance",
    "Cashback",
    "Proventos",
    "Empresa",
]

#: Expense category → macro-category, in the order of the config sheet.
EXPENSE_CATEGORIES: dict[str, str] = {
    "Luz": "Fixo",
    "Água": "Fixo",
    "Telefone": "Fixo",
    "Internet": "Fixo",
    "Aluguel": "Fixo",
    "Mercado": "Fixo",
    "Condomínio": "Fixo",
    "Emprestimos": "Variável",
    "Estudos": "Fixo",
    "Transporte": "Variável",
    "Juros": "Variável",
    "Multa": "Variável",
    "Diversos": "Variável",
    "Plano de Saúde": "Fixo",
    "Cartão de Crédito": "Variável",
    "Lazer": "Variável",
    "Alimentação": "Variável",
    "Saúde": "Variável",
    "Livros": "Variável",
    "Viagem": "Variável",
    "Vestuário": "Variável",
    "Pets Saúde": "Variável",
    "Casa": "Variável",
    "Empresa": "Fixo",
    "Filhos": "Variável",
    "Streaming": "Fixo",
    "Doação": "Variável",
    "Jogo": "Variável",
    "Imposto": "Fixo",
    "Investimento": "n/a",
    "Gás": "Variável",
    "Presente": "Variável",
    "Faxina": "Fixo",
    "Estética": "Variável",
    "Pets Necessidades": "Fixo",
}

#: Merchant → category used for it in the oldest workbooks. These categories
#: were later merged into others and are absent from the canonical config, so
#: staging has to handle them.
LEGACY_CATEGORY_BY_MERCHANT: dict[str, str] = {"Farmácia": "Farmácia", "App de transporte": "Uber"}
LEGACY_MACRO = "Variável"
LEGACY_UNTIL_YEAR = 2022


# --------------------------------------------------------------------------
# Card purchases
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Merchant:
    """A kind of card purchase: where, what category, how much."""

    description: str
    category: str
    low: float
    high: float
    weight: float = 1.0
    installments: tuple[int, ...] = ()
    """Possible installment counts; empty means always paid at once."""
    items: tuple[str, ...] = ()
    """Optional item suffixes, e.g. 'Marketplace - Luminária'."""


MERCHANTS: list[Merchant] = [
    Merchant("Supermercado Central", "Mercado", 60, 480, 6),
    Merchant("Feira livre", "Mercado", 30, 140, 3),
    Merchant("Hortifruti", "Mercado", 25, 120, 3),
    Merchant("Padaria do bairro", "Mercado", 12, 60, 4),
    Merchant("Açougue", "Mercado", 50, 220, 2),
    Merchant("Restaurante", "Alimentação", 45, 220, 3),
    Merchant("App de delivery", "Alimentação", 35, 140, 4),
    Merchant("Cafeteria", "Alimentação", 15, 55, 2),
    Merchant("App de transporte", "Transporte", 12, 70, 4),
    Merchant("Posto de combustível", "Transporte", 120, 320, 3),
    Merchant("Estacionamento", "Transporte", 15, 45, 1),
    Merchant("Farmácia", "Saúde", 20, 180, 3),
    Merchant("Consulta médica", "Saúde", 250, 600, 0.5, (2, 3)),
    Merchant("Natação", "Saúde", 900, 1700, 0.15, (10, 12)),
    Merchant("Cinema", "Lazer", 40, 120, 1.5),
    Merchant("Ingressos show", "Lazer", 150, 700, 0.4, (2, 3, 4)),
    Merchant("Bar", "Lazer", 60, 250, 1.5),
    Merchant(
        "Marketplace",
        "Casa",
        40,
        900,
        2,
        (2, 3, 4, 5, 6),
        ("Luminária", "Organizadores", "Tapete", "Cortina", "Prateleira", "Utensílios"),
    ),
    Merchant("Loja de material de construção", "Casa", 150, 2400, 0.8, (4, 6, 8, 10)),
    Merchant("Loja de móveis", "Casa", 600, 4500, 0.2, (8, 10, 12)),
    Merchant("Loja de roupas", "Vestuário", 70, 450, 1.2, (2, 3, 4)),
    Merchant("Loja de calçados", "Vestuário", 120, 500, 0.6, (2, 3, 6)),
    Merchant("Loja de brinquedos", "Presente", 50, 300, 0.8, (2,)),
    Merchant(
        "Marketplace", "Presente", 40, 250, 0.8, (2, 3), ("Presente aniversário", "Lembrança")
    ),
    Merchant("Livraria", "Livros", 35, 160, 0.6),
    Merchant("Curso online", "Estudos", 80, 900, 0.3, (3, 6, 12)),
    Merchant("Pet shop - Ração", "Pets Necessidades", 90, 260, 1.2),
    Merchant("Pet shop - Areia", "Pets Necessidades", 45, 110, 0.8),
    Merchant("Clínica veterinária", "Pets Saúde", 120, 900, 0.4, (2, 3)),
    Merchant("Loja de games", "Jogo", 60, 350, 0.4, (2, 3)),
    Merchant("Salão de beleza", "Estética", 60, 280, 0.8),
    Merchant("Barbearia", "Estética", 40, 90, 0.8),
    Merchant("Hotel", "Viagem", 600, 3500, 0.15, (3, 4, 6, 10)),
    Merchant("Passagem aérea", "Viagem", 700, 3200, 0.12, (5, 6, 10)),
    Merchant("Loja infantil", "Filhos", 60, 400, 1.0, (2, 3)),
    Merchant("Fraldas e higiene", "Filhos", 60, 220, 1.2),
    Merchant("Papelaria", "Diversos", 10, 90, 0.8),
    Merchant("Doação ONG", "Doação", 30, 120, 0.3),
    Merchant("Notebook para familiar", "Emprestimos", 1800, 3600, 0.04, (10, 12)),
]

#: Monthly subscriptions charged on a card: (description, category, amount,
#: first year).
SUBSCRIPTIONS: list[tuple[str, str, float, int]] = [
    ("Streaming de vídeo", "Streaming", 39.90, 2021),
    ("Streaming de música", "Streaming", 21.90, 2021),
    ("Academia", "Saúde", 109.90, 2023),
]

# --------------------------------------------------------------------------
# Bills paid outside the cards (no cell color): (description, category,
# base amount, monthly jitter as a fraction of the base, first year).
# --------------------------------------------------------------------------

BILLS: list[tuple[str, str, float, float, int]] = [
    ("Aluguel", "Aluguel", 1500.00, 0.0, 2021),
    ("Condomínio", "Condomínio", 420.00, 0.03, 2021),
    ("Conta de luz", "Luz", 160.00, 0.35, 2021),
    ("Conta de água", "Água", 80.00, 0.25, 2021),
    ("Gás encanado", "Gás", 55.00, 0.3, 2021),
    ("Internet fibra", "Internet", 99.90, 0.0, 2021),
    ("Plano celular", "Telefone", 59.90, 0.0, 2021),
    ("Plano de saúde", "Plano de Saúde", 380.00, 0.0, 2021),
    ("Diarista", "Faxina", 360.00, 0.15, 2021),
    ("Escola", "Estudos", 850.00, 0.0, 2023),
]

# --------------------------------------------------------------------------
# Investment portfolio ("Situação Atual" sheet)
# --------------------------------------------------------------------------

# Fictional real-estate notes for the crowdfunding platform. Names are built
# by pairing a prefix and a project name.
NOTE_PREFIXES = ["CRI", "CCB", "Recebíveis", "CRI Residencial"]
NOTE_PROJECTS = [
    "Aurora",
    "Boreal",
    "Cedro",
    "Dunas",
    "Estrela do Vale",
    "Figueira",
    "Girassol",
    "Horizonte",
    "Ipê Amarelo",
    "Jardim das Águas",
    "Lagoa Azul",
    "Mirante",
    "Nascente",
    "Oásis",
    "Pedra Branca",
    "Quinta Verde",
    "Recanto",
    "Serra Alta",
    "Terra Nova",
    "Vale Sereno",
]

#: Fictional real-estate fund tickers that pay monthly dividends.
FUND_TICKERS = [
    "FIIA11",
    "FIIB11",
    "FIIC11",
    "FIID11",
    "FIIE11",
    "FIIF11",
    "FIIG11",
    "FIIH11",
    "FIIJ11",
    "FIIK11",
    "FIIL11",
    "FIIM11",
    "FIIN11",
    "FIIP11",
    "FIIR11",
]
