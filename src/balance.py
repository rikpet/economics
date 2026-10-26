from app_types import Category, ReadTransaction
from category_templates import PRIVATE


class SubCategory():

    def __init__(self, invert_sign: bool = False, visible: bool = True):
        self.amount = 0
        self.invert_sign = invert_sign
        self.visible = visible

    def add(self, amount: float):
        if self.invert_sign:
            self.amount -= amount
        else:
            self.amount += amount

    def set(self, amount: float):
        self.amount = amount

    def __call__(self) -> float:
        return self.amount
    
    def reset(self):
        self.amount = 0


class Balance():
    def __init__(self, year: int, month: int, dept: float | None = 0,
                 categories: list[Category] | None = None, derive_allowance: bool = True):
        """Monthly balance per category.

        Args:
            categories: The account's category tree. Defaults to the private template.
            derive_allowance: Calculate 'inkomst/månadspeng' as bokföring/inkomst minus
                bokföring/familjekonto minus last month's family outlays (dept).
        """
        self.year = year
        self.month = month
        self.dept = dept

        if categories is None:
            categories = [Category(0, m, s, invert) for m, s, invert in PRIVATE]

        self.balance: dict[str, dict[str, SubCategory]] = {}
        for c in categories:
            subs = self.balance.setdefault(c.main_category.lower(), {})
            subs[c.sub_category.lower()] = SubCategory(c.invert_sign)
        self.balance.setdefault("uncategorized", {}).setdefault("övrigt", SubCategory())

        self.derive_allowance = derive_allowance and all(
            sub in self.balance.get(main, {})
            for main, sub in (("inkomst", "månadspeng"), ("bokföring", "inkomst"),
                              ("bokföring", "familjekonto"),
                              ("bokföring", "familjeutlägg"))
        )

    def add_several(self, transactions: list[ReadTransaction]):
        if len(transactions) == 0:
            return
        
        for  t in transactions:
            self.add(t)

    def set_dept(self, amount: float):
        self.dept = amount

    def add(self, transaction: ReadTransaction):
        main = (transaction.main_category or "").lower()
        sub = (transaction.sub_category or "").lower()

        # Unknown categories (e.g. deleted or never classified) count as uncategorized so the
        # totals still add up.
        if main not in self.balance or sub not in self.balance[main]:
            self.balance["uncategorized"]["övrigt"].add(transaction.amount)
            return

        self.balance[main][sub].add(transaction.amount)

    def get(self, category: str) -> float:
        category = category.lower()
        if category not in self.balance:
            raise ValueError(f"Unknown category: {category}")
        
        if category == "inkomst" and self.derive_allowance:
            if self.dept is None:
                raise ValueError("Missing 'dept' argument for income calculation")

            self.balance["inkomst"]["månadspeng"].set(
                self.balance["bokföring"]["inkomst"]() - self.balance["bokföring"]["familjekonto"]() - self.dept
            )

        subs = self.balance[category]
        balance = sum(sub() for sub in subs.values())
        return balance
    
    def get_sub_category(self, main_category: str, sub_category: str) -> float:
        main_category = main_category.lower()
        sub_category = sub_category.lower()

        if main_category not in self.balance:
            raise ValueError(f"Unknown category. Main category: {main_category}")

        if sub_category not in self.balance[main_category]:
            raise ValueError(f"Unknown sub-category. Main category: {main_category}, Sub-category: {sub_category}")

        return self.balance[main_category][sub_category]()
        
    
    def categories(self) -> list[str]:
        return [c for c in self.balance.keys()]
        
    def sub_categories(self, main_category: str) -> list[str]:
        main_category = main_category.lower()
        if main_category not in self.balance:
            raise ValueError(f"Unknown category. Main category: {main_category}")

        return list(self.balance[main_category].keys())