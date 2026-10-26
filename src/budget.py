import calendar
from dataclasses import dataclass, field
from datetime import datetime

import database as db
from app_types import Account, Category
from balance import Balance


def monthly_balances(database_path: str, account: Account, year: int,
                     months: list[int] | None = None) -> dict[int, Balance]:
    """Build one Balance per month of the year for the account."""
    months = list(months) if months else list(range(1, 13))
    categories = db.get_categories(database_path, account.id)

    def build(y: int, m: int) -> Balance:
        b = Balance(y, m, categories=categories, derive_allowance=account.derive_allowance)
        b.add_several(db.get_transactions(
            database_path,
            account.id,
            datetime(y, m, 1),
            datetime(y, m, calendar.monthrange(y, m)[1])
        ))
        return b

    balances = {m: build(year, m) for m in months}

    # The family outlays of the previous month are paid back this month, and are not part
    # of this month's allowance.
    for m in months:
        if not balances[m].derive_allowance:
            continue
        previous = balances.get(m - 1) or (build(year - 1, 12) if m == 1 else build(year, m - 1))
        balances[m].set_dept(previous.get_sub_category("bokföring", "familjeutlägg"))
    return balances


@dataclass
class BudgetRow:
    label: str
    main_category: str
    sub_category: str | None
    values: list[float] = field(default_factory=list)

    @property
    def total(self) -> float:
        return sum(self.values)

    @property
    def is_sub(self) -> bool:
        return self.sub_category is not None


def hidden_categories(categories: list[Category]) -> set[tuple[str, str]]:
    return {(c.main_category, c.sub_category) for c in categories if c.hidden}


def visible_subs(balance: Balance, main: str, hidden: set[tuple[str, str]]) -> list[str]:
    return [sub for sub in balance.sub_categories(main) if (main, sub) not in hidden]


def main_value(balance: Balance, main: str, hidden: set[tuple[str, str]]) -> float:
    """The main category's value, without its hidden sub-categories."""
    value = balance.get(main)  # also derives inkomst/månadspeng
    subs = visible_subs(balance, main, hidden)
    if len(subs) < len(balance.sub_categories(main)):
        value = sum(balance.get_sub_category(main, sub) for sub in subs)
    return value


def budget_table(balances: dict[int, Balance], show_sub_category: bool = False,
                 categories: list[str] | None = None,
                 hidden: set[tuple[str, str]] | None = None) -> list[BudgetRow]:
    """Rows of (category, value per month) in the order of the category tree.

    Hidden sub-categories are left out, and so is their share of the main category. A main
    category whose sub-categories are all hidden is left out entirely, and Uncategorized is
    only shown when it has transactions.
    """
    hidden = hidden or set()
    first = next(iter(balances.values()))
    rows: list[BudgetRow] = []
    for main in (categories or first.categories()):
        main = main.lower()
        subs = visible_subs(first, main, hidden)
        if not subs:
            continue

        values = [main_value(b, main, hidden) for b in balances.values()]
        if main == "uncategorized" and not any(values):
            continue

        rows.append(BudgetRow(main.capitalize(), main, None, values))
        if show_sub_category:
            for sub in subs:
                rows.append(BudgetRow(sub.capitalize(), main, sub,
                                      [b.get_sub_category(main, sub) for b in balances.values()]))
    return rows


@dataclass
class CashFlow:
    """Income and expenses per month, for charts. Hidden categories are left out."""
    income: list[float]
    expenses: list[float]
    expenses_by_main: dict[str, list[float]]


def cash_flow(balances: dict[int, Balance], categories: list[Category]) -> CashFlow:
    for b in balances.values():
        if b.derive_allowance:
            b.get("inkomst")  # sets the derived inkomst/månadspeng

    income = [0.0] * len(balances)
    expenses = [0.0] * len(balances)
    by_main: dict[str, list[float]] = {}
    for c in categories:
        if c.hidden:
            continue
        main, sub = c.main_category.lower(), c.sub_category.lower()
        for i, b in enumerate(balances.values()):
            value = b.get_sub_category(main, sub)
            if c.invert_sign:  # expense, already a positive cost
                expenses[i] += value
                by_main.setdefault(main, [0.0] * len(balances))[i] += value
            else:
                income[i] += value

    # Unclassified transactions are mostly purchases: count them as expenses (positive cost).
    uncategorized = [-b.get("uncategorized") for b in balances.values()]
    if any(uncategorized):
        by_main["uncategorized"] = uncategorized
        expenses = [e + u for e, u in zip(expenses, uncategorized)]
    return CashFlow(income, expenses, by_main)
