"""The allowance calculation: how much each person transfers to the joint account.

    to the joint account = income − shared expenses − allowance

Shared expenses are what the person paid for the household with their own money, so they
transfer that much less. The allowance is what everyone keeps on their private account:
one amount per month for the household, DEFAULT_ALLOWANCE (or the account's own default)
unless the month has its own. Pension savings are not part of the calculation.

A person can be linked to their own account in the app (Rikard). Then their income is
Bokföring › Inkomst of the month unless they enter one, and the debt in that account -
Bokföring › Familjeutlägg, what they paid for the family - is added to their shared
expenses the month after, as the account's derived allowance does. Bokföring ›
Familjekonto shows what was actually transferred.
"""

import re
from dataclasses import dataclass

import database as db
from app_types import Person, PersonMonth
from balance import Balance
from budget import monthly_balances

DEFAULT_ALLOWANCE = 12000.0
ALLOWANCE_SETTING = "default_allowance"

LINKED_INCOME = ("bokföring", "inkomst")
LINKED_DEBT = ("bokföring", "familjeutlägg")        # of the previous month
LINKED_TRANSFERRED = ("bokföring", "familjekonto")


def default_allowance(database_path: str, account_id: int) -> float:
    value = db.get_setting(database_path, account_id, ALLOWANCE_SETTING)
    return float(value) if value is not None else DEFAULT_ALLOWANCE


def month_allowances(database_path: str, account_id: int, year: int) -> list[tuple[float, bool]]:
    """(allowance, set for that month) for the 12 months of a year."""
    default = default_allowance(database_path, account_id)
    own = db.get_allowance_months(database_path, account_id, year)
    return [(own[m], True) if m in own else (default, False) for m in range(1, 13)]


@dataclass
class TransferMonth:
    person: Person
    year: int
    month: int
    allowance: float
    entered: PersonMonth | None = None   # what was typed in for this month
    linked_income: float | None = None   # from the linked account
    debt: float | None = None            # the linked account's debt from the month before
    transferred: float | None = None     # actually transferred, from the linked account

    @property
    def income(self) -> float:
        if self.entered and self.entered.income is not None:
            return self.entered.income
        return self.linked_income or 0.0

    @property
    def entered_costs(self) -> float:
        return (self.entered.costs if self.entered else None) or 0.0

    @property
    def costs(self) -> float:
        """Shared expenses: what was entered plus last month's debt in the linked account."""
        return self.entered_costs + (self.debt or 0.0)

    @property
    def has_data(self) -> bool:
        """Something is known about the month, so the result means something."""
        entered = self.entered and (self.entered.income is not None
                                    or self.entered.costs is not None)
        return bool(entered or self.linked_income or self.debt)

    @property
    def to_account(self) -> float:
        return self.income - self.costs - self.allowance


def _linked_figures(database_path: str, account_id: int, year: int):
    """{month: (income, debt from the month before, transferred)} from a linked account, or
    {} when it doesn't have the Bokföring categories."""
    account = db.get_account(database_path, account_id)
    if account is None:
        return {}
    names = {(c.main_category, c.sub_category) for c in db.get_categories(database_path, account_id)}
    if not {LINKED_INCOME, LINKED_DEBT, LINKED_TRANSFERRED} <= names:
        return {}
    balances = monthly_balances(database_path, account, year)
    december: Balance = monthly_balances(database_path, account, year - 1, [12])[12]

    def value(b: Balance, key: tuple[str, str]) -> float:
        return b.get_sub_category(*key)

    return {
        m: (value(b, LINKED_INCOME),
            value(balances[m - 1] if m > 1 else december, LINKED_DEBT),
            value(b, LINKED_TRANSFERRED))
        for m, b in balances.items()
    }


def transfer_year(database_path: str, account_id: int, year: int) -> dict[int, list[TransferMonth]]:
    """{person id: the 12 months of the year} for the account's people."""
    people = db.get_people(database_path, account_id)
    stored = db.get_person_months(database_path, account_id, year)
    allowances = month_allowances(database_path, account_id, year)
    result: dict[int, list[TransferMonth]] = {}
    for person in people:
        entered = {s.month: s for s in stored if s.person_id == person.id}
        linked = (_linked_figures(database_path, person.linked_account_id, year)
                  if person.linked_account_id else {})
        result[person.id] = [
            TransferMonth(person, year, m, allowances[m - 1][0], entered.get(m),
                          *linked.get(m, (None, None, None)))
            for m in range(1, 13)
        ]
    return result


_TERM = re.compile(r"[+-]?[^+-]+")


def parse_sum(text: str | None) -> float | None:
    """An amount or a sum as typed in a spreadsheet: '1 234,50', '=100+250-50'.
    Empty -> None."""
    text = (text or "").strip().lstrip("=").replace("−", "-")
    for space in (" ", " ", " "):
        text = text.replace(space, "")
    if not text:
        return None
    terms = _TERM.findall(text)
    if "".join(terms) != text:
        raise ValueError(f"Not an amount: {text!r}")
    try:
        return round(sum(float(t.replace(",", ".").replace("kr", "")) for t in terms), 2)
    except ValueError:
        raise ValueError(f"Not an amount: {text!r}") from None
