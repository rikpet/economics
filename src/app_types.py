from dataclasses import dataclass

@dataclass
class Transaction():
    date: str
    issuer: str
    amount: float
    origin: str
    main_category: str | None = None
    sub_category: str | None = None
    comment: str | None = None
    verification_number: str | None = None
    modification_log: str | None = None

@dataclass
class ReadTransaction():
    id: int
    date: str
    issuer: str
    amount: float
    origin: str
    main_category: str | None = None
    sub_category: str | None = None
    comment: str | None = None
    verification_number: str | None = None
    modification_log: str | None = None
    parent_id: int | None = None   # set on the parts of a split transaction
    is_split: bool = False         # the original of a split; replaced by its parts

@dataclass
class SplitPart:
    amount: float
    main_category: str | None = None
    sub_category: str | None = None
    comment: str | None = None

@dataclass
class IssuerClassification:
    issuer: str
    main_category: str
    sub_category: str

@dataclass
class Account:
    id: int
    name: str
    derive_allowance: bool = False

@dataclass
class Category:
    id: int
    main_category: str
    sub_category: str
    invert_sign: bool = True
    hidden: bool = False
    # For expenses (invert_sign): 'variable', 'fixed' (a fixed monthly cost) or 'transfer'
    # (shown like an expense but not counted as one, e.g. savings).
    expense_role: str = 'variable'
    zero_check: bool = False  # should add up to 0 every month, e.g. outlays/debt

    @property
    def counts_as_expense(self) -> bool:
        return self.invert_sign and self.expense_role != 'transfer'

    @property
    def kind(self) -> str:
        """income, expense, fixed or transfer - what the Categories page shows."""
        if not self.invert_sign:
            return 'income'
        return {'fixed': 'fixed', 'transfer': 'transfer'}.get(self.expense_role, 'expense')


@dataclass
class Person:
    """Someone who transfers money to an account, e.g. to the family's joint account."""
    id: int
    name: str
    linked_account_id: int | None = None  # their own account, to read income and outlays from
    position: int = 0


@dataclass
class PersonMonth:
    """What a person entered for a month. None means not entered."""
    person_id: int
    year: int
    month: int
    income: float | None = None
    income_input: str | None = None  # as typed, e.g. '35000+5000'
    costs: float | None = None       # one-off costs paid for the joint account
    costs_input: str | None = None
    allowance: float | None = None   # carries over to later months until changed
