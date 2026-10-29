"""How much each person transfers to a shared account per month.

    to the account = income − one-off costs − allowance

One-off costs are what the person paid for the shared account out of their own money, so
they transfer that much less. The allowance is what they keep; it carries over from the
month it was set until it is changed. Pension savings are not part of the calculation.

A person can be linked to their own account in the app (e.g. Privat). Months they have not
filled in then use that account's figures, as its derived allowance does: income is
Bokföring › Inkomst of the month, one-off costs are Bokföring › Familjeutlägg of the month
before (paid back this month), and Bokföring › Familjekonto is what was actually
transferred.
"""

import re
from dataclasses import dataclass

import database as db
from app_types import Person, PersonMonth
from balance import Balance
from budget import monthly_balances

LINKED_INCOME = ("bokföring", "inkomst")
LINKED_COSTS = ("bokföring", "familjeutlägg")       # of the previous month
LINKED_TRANSFERRED = ("bokföring", "familjekonto")


@dataclass
class TransferMonth:
    person: Person
    year: int
    month: int
    entered: PersonMonth | None = None   # what was typed in for this month
    linked_income: float | None = None   # from the linked account
    linked_costs: float | None = None
    transferred: float | None = None     # actually transferred, from the linked account
    carried_allowance: float = 0.0       # the allowance set in an earlier month

    @property
    def income(self) -> float:
        if self.entered and self.entered.income is not None:
            return self.entered.income
        return self.linked_income or 0.0

    @property
    def costs(self) -> float:
        if self.entered and self.entered.costs is not None:
            return self.entered.costs
        return self.linked_costs or 0.0

    @property
    def allowance(self) -> float:
        if self.entered and self.entered.allowance is not None:
            return self.entered.allowance
        return self.carried_allowance

    @property
    def has_data(self) -> bool:
        """Something is known about the month, so the result means something."""
        entered = self.entered and (self.entered.income is not None
                                    or self.entered.costs is not None)
        return bool(entered or self.linked_income or self.linked_costs)

    @property
    def to_account(self) -> float:
        return self.income - self.costs - self.allowance


def _linked_figures(database_path: str, account_id: int, year: int):
    """{month: (income, costs, transferred)} from a linked account, or {} when it doesn't
    have the Bokföring categories."""
    account = db.get_account(database_path, account_id)
    if account is None:
        return {}
    names = {(c.main_category, c.sub_category) for c in db.get_categories(database_path, account_id)}
    if not {LINKED_INCOME, LINKED_COSTS, LINKED_TRANSFERRED} <= names:
        return {}
    balances = monthly_balances(database_path, account, year)
    december: Balance = monthly_balances(database_path, account, year - 1, [12])[12]

    def value(b: Balance, key: tuple[str, str]) -> float:
        return b.get_sub_category(*key)

    return {
        m: (value(b, LINKED_INCOME),
            value(balances[m - 1] if m > 1 else december, LINKED_COSTS),
            value(b, LINKED_TRANSFERRED))
        for m, b in balances.items()
    }


def transfer_year(database_path: str, account_id: int, year: int) -> dict[int, list[TransferMonth]]:
    """{person id: the 12 months of the year} for the account's people."""
    people = db.get_people(database_path, account_id)
    stored = db.get_person_months(database_path, account_id, year)
    result: dict[int, list[TransferMonth]] = {}
    for person in people:
        mine = [s for s in stored if s.person_id == person.id]
        entered = {s.month: s for s in mine if s.year == year}
        allowance = next((s.allowance for s in reversed(mine)
                          if s.year < year and s.allowance is not None), 0.0)
        linked = (_linked_figures(database_path, person.linked_account_id, year)
                  if person.linked_account_id else {})
        months = []
        for m in range(1, 13):
            income, costs, transferred = linked.get(m, (None, None, None))
            tm = TransferMonth(person, year, m, entered.get(m), income, costs, transferred,
                               carried_allowance=allowance)
            allowance = tm.allowance
            months.append(tm)
        result[person.id] = months
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
