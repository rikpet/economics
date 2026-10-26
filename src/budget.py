import calendar
from dataclasses import dataclass, field
from datetime import datetime

import database as db
from app_types import Account
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


def budget_table(balances: dict[int, Balance], show_sub_category: bool = False,
                 categories: list[str] | None = None) -> list[BudgetRow]:
    """Rows of (category, value per month) in the order of the category tree."""
    first = next(iter(balances.values()))
    rows: list[BudgetRow] = []
    for main in (categories or first.categories()):
        main = main.lower()
        rows.append(BudgetRow(main.capitalize(), main, None,
                              [b.get(main) for b in balances.values()]))
        if show_sub_category:
            for sub in first.sub_categories(main):
                rows.append(BudgetRow(sub.capitalize(), main, sub,
                                      [b.get_sub_category(main, sub) for b in balances.values()]))
    return rows
