
from app_types import ReadTransaction


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
    def __init__(self, year: int, month: int, dept: float | None = 0):
        self.year = year
        self.month = month
        self.dept = dept

        self.balance = {
            "inkomst": {
                "månadspeng": SubCategory(),
                "ränta": SubCategory(),
                "övrigt": SubCategory()
            },
            "hushåll": {
                "inredning/renovering": SubCategory(True),
                "landet": SubCategory(True),
                "övrigt": SubCategory(True)
            },
            "transport": {
                "bensin": SubCategory(True),
                "parkering": SubCategory(True),
                "taxi": SubCategory(True),
                "kollektivtrafik": SubCategory(True),
                "övrigt": SubCategory(True)
            },
            "försäkring": {
                "övrigt": SubCategory(True)
            },
            "nöje": {
                "kultur": SubCategory(True),
                "aktivitet": SubCategory(True),
                "prenumerationstjänster": SubCategory(True),
                "resa": SubCategory(True),
                "restaurang": SubCategory(True),
                "grabbresa": SubCategory(True),
                "övrigt": SubCategory(True)
            },
            "kläder": {
                "övrigt": SubCategory(True)
            },
            "mat": {
                "fika": SubCategory(True),
                "butik": SubCategory(True),
                "systembolaget": SubCategory(True),
                "lunch": SubCategory(True),
                "övrigt": SubCategory(True)
            },
            "lån": {
                "övrigt": SubCategory(True)
            },
            "övrigt": {
                "facket": SubCategory(True),
                "bankkostnader": SubCategory(True),
                "apotek": SubCategory(True),
                "träning": SubCategory(True),
                "övrigt": SubCategory(True)
            },
            "sparande": {
                "övrigt": SubCategory(True)
            },
            "bokföring": {
                "familjekonto": SubCategory(True),
                "familjeutlägg": SubCategory(True),
                "inkomst": SubCategory(),
                "utlägg/skuld": SubCategory(True),
                "internöverföring": SubCategory(True)
            }
        }

    def add_several(self, transactions: list[ReadTransaction]):
        if len(transactions) == 0:
            return
        
        for  t in transactions:
            self.add(t)

    def set_dept(self, amount: float):
        self.dept = amount

    def add(self, transaction: ReadTransaction):
        if transaction.main_category is None or transaction.main_category.lower() not in self.balance:
            raise ValueError(f'Unknown main category: {transaction.main_category}')

        if transaction.sub_category is None or transaction.sub_category.lower() not in self.balance[transaction.main_category.lower()]:
            raise ValueError(f'Unknown sub-category: {transaction.sub_category}. Main category: {transaction.main_category}')

        self.balance[transaction.main_category.lower()][transaction.sub_category.lower()].add(transaction.amount)

    def get(self, category: str) -> float:
        category = category.lower()
        if category not in self.balance:
            raise ValueError(f"Unknown category: {category}")
        
        if category == "inkomst":
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