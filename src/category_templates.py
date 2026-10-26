"""Category trees used when creating a new account.

Each entry is (main_category, sub_category, invert_sign). invert_sign=True means the
category is an expense: negative transaction amounts are shown as positive costs.
"""

CategoryTemplate = list[tuple[str, str, bool]]


def _expenses(main: str, *subs: str) -> CategoryTemplate:
    return [(main, sub, True) for sub in subs]


PRIVATE: CategoryTemplate = [
    ("inkomst", "månadspeng", False),
    ("inkomst", "ränta", False),
    ("inkomst", "övrigt", False),
    *_expenses("hushåll", "inredning/renovering", "landet", "övrigt"),
    *_expenses("transport", "bensin", "parkering", "taxi", "kollektivtrafik", "övrigt"),
    *_expenses("försäkring", "övrigt"),
    *_expenses(
        "nöje",
        "kultur",
        "aktivitet",
        "prenumerationstjänster",
        "resa",
        "restaurang",
        "grabbresa",
        "övrigt",
    ),
    *_expenses("kläder", "övrigt"),
    *_expenses("mat", "fika", "butik", "systembolaget", "lunch", "övrigt"),
    *_expenses("lån", "övrigt"),
    *_expenses("övrigt", "facket", "bankkostnader", "apotek", "träning", "övrigt"),
    *_expenses("sparande", "övrigt"),
    ("bokföring", "familjekonto", True),
    ("bokföring", "familjeutlägg", True),
    ("bokföring", "inkomst", False),
    ("bokföring", "utlägg/skuld", True),
    ("bokföring", "internöverföring", True),
]

FAMILY: CategoryTemplate = [
    ("inkomst", "insättning rikard", False),
    ("inkomst", "insättning sara", False),
    ("inkomst", "barnbidrag", False),
    ("inkomst", "övrigt", False),
    *_expenses("boende", "avgift/hyra", "el", "bredband", "inredning/renovering", "övrigt"),
    *_expenses("mat", "butik", "restaurang", "övrigt"),
    *_expenses("barn", "förskola/skola", "kläder", "aktiviteter", "övrigt"),
    *_expenses("transport", "bil", "bensin", "parkering", "kollektivtrafik", "övrigt"),
    *_expenses("nöje", "resa", "aktivitet", "prenumerationstjänster", "övrigt"),
    *_expenses("hälsa", "apotek", "vård", "övrigt"),
    *_expenses("försäkring", "övrigt"),
    *_expenses("lån", "bolån", "övrigt"),
    *_expenses("sparande", "övrigt"),
    *_expenses("övrigt", "bankkostnader", "övrigt"),
]

TEMPLATES: dict[str, CategoryTemplate] = {
    "private": PRIVATE,
    "family": FAMILY,
    "empty": [],
}
