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


def cash_flow(balances: dict[int, Balance], categories: list[Category],
              exclude: set[str] | None = None) -> CashFlow:
    """Income and expenses per month. `exclude` lists main categories to leave out."""
    exclude = exclude or set()
    for b in balances.values():
        if b.derive_allowance:
            b.get("inkomst")  # sets the derived inkomst/månadspeng

    income = [0.0] * len(balances)
    expenses = [0.0] * len(balances)
    by_main: dict[str, list[float]] = {}
    for c in categories:
        main, sub = c.main_category.lower(), c.sub_category.lower()
        if c.hidden or main in exclude:
            continue
        for i, b in enumerate(balances.values()):
            value = b.get_sub_category(main, sub)
            if c.counts_as_expense:  # already a positive cost
                expenses[i] += value
                by_main.setdefault(main, [0.0] * len(balances))[i] += value
            elif not c.invert_sign:
                income[i] += value
            # Transfers (e.g. savings) are neither.

    # Unclassified transactions are mostly purchases: count them as expenses (positive cost).
    uncategorized = [-b.get("uncategorized") for b in balances.values()]
    if any(uncategorized) and "uncategorized" not in exclude:
        by_main["uncategorized"] = uncategorized
        expenses = [e + u for e, u in zip(expenses, uncategorized)]
    return CashFlow(income, expenses, by_main)


def completed_months(year: int, now: datetime | None = None) -> int:
    """How many months of the year are over; the current month is still running."""
    now = now or datetime.now()
    if year < now.year:
        return 12
    return now.month - 1 if year == now.year else 0


@dataclass
class SummaryRow:
    label: str
    key: str
    values: list[float]
    hint: str = ""

    @property
    def total(self) -> float:
        return sum(self.values)


def summary_rows(balances: dict[int, Balance], categories: list[Category]) -> list[SummaryRow]:
    """Totals under the budget table: all expenses, and expenses without fixed costs.

    Expenses are the categories of type Expense or Fixed expense that are not hidden, plus
    unclassified transactions (mostly purchases). Income and transfers such as savings are
    not expenses.
    """
    expenses = [0.0] * len(balances)
    fixed = [0.0] * len(balances)
    for c in categories:
        if c.hidden or not c.counts_as_expense:
            continue
        main, sub = c.main_category.lower(), c.sub_category.lower()
        for i, b in enumerate(balances.values()):
            value = b.get_sub_category(main, sub)
            expenses[i] += value
            if c.expense_role == "fixed":
                fixed[i] += value
    for i, b in enumerate(balances.values()):
        expenses[i] -= b.get("uncategorized")
    fixed_names = sorted({c.main_category.capitalize() for c in categories
                          if c.counts_as_expense and c.expense_role == "fixed" and not c.hidden})
    return [
        SummaryRow("Expenses", "expenses", expenses,
                   "Every expense category, plus unclassified transactions. Not income or "
                   "transfers such as savings."),
        SummaryRow("Expenses excl. fixed costs", "variable",
                   [e - f for e, f in zip(expenses, fixed)],
                   "Expenses without the fixed monthly costs"
                   + (f" ({', '.join(fixed_names)})." if fixed_names else
                      ". No category is marked as a fixed expense yet.")),
    ]


@dataclass
class ZeroCheckFlag:
    main_category: str
    sub_category: str
    month: int
    value: float

    @property
    def label(self) -> str:
        return f"{self.main_category.capitalize()} \u203a {self.sub_category.capitalize()}"


def zero_check_flags(balances: dict[int, Balance], categories: list[Category],
                     months_done: int) -> list[ZeroCheckFlag]:
    """Months where a category that should add up to zero (e.g. outlays/debt) does not.

    Only months that are over are checked; hidden categories are checked too.
    """
    flags = []
    for c in categories:
        if not c.zero_check:
            continue
        main, sub = c.main_category.lower(), c.sub_category.lower()
        for month, b in balances.items():
            value = b.get_sub_category(main, sub)
            if month <= months_done and abs(value) >= 0.005:
                flags.append(ZeroCheckFlag(main, sub, month, value))
    return flags
