import pytest

import database as db
from app_types import Transaction
from budget import budget_table, monthly_balances


@pytest.fixture
def path(tmp_path):
    p = str(tmp_path / 'test.db')
    db.create_tables(p)
    return p


def add(path, account_id, date, amount, main, sub):
    db.insert_transaction(path, account_id, Transaction(date, 'X', amount, 'SEB', main, sub))


def test_allowance_is_derived_from_bookkeeping(path):
    private = db.get_account(path, 1)
    # Family outlays paid from the private account in December and January.
    add(path, 1, '2024-12-10', -300, 'bokföring', 'familjeutlägg')
    add(path, 1, '2025-01-10', -200, 'bokföring', 'familjeutlägg')
    for month in ('01', '02'):
        add(path, 1, f'2025-{month}-25', 10000, 'bokföring', 'inkomst')
        add(path, 1, f'2025-{month}-26', -6000, 'bokföring', 'familjekonto')

    balances = monthly_balances(path, private, 2025)

    # January: 10000 - 6000 - December's outlays (300)
    assert balances[1].get('inkomst') == 3700
    # February: 10000 - 6000 - January's outlays (200)
    assert balances[2].get('inkomst') == 3800

    # A single month gives the same result.
    assert monthly_balances(path, private, 2025, [2])[2].get('inkomst') == 3800


def test_family_account_budget(path):
    family = db.get_account(path, db.create_account(path, 'Familj', 'family'))
    add(path, family.id, '2025-03-01', -1200, 'boende', 'el')
    add(path, family.id, '2025-03-02', 15000, 'inkomst', 'insättning rikard')
    add(path, family.id, '2025-03-03', -99, 'gammal', 'kategori')

    balances = monthly_balances(path, family, 2025)
    assert balances[3].get('boende') == 1200
    assert balances[3].get('inkomst') == 15000
    assert balances[3].get('uncategorized') == -99

    rows = budget_table(balances, show_sub_category=True)
    el = next(r for r in rows if r.main_category == 'boende' and r.sub_category == 'el')
    assert el.values[2] == 1200 and el.total == 1200
    assert [r.main_category for r in rows if not r.is_sub][-1] == 'uncategorized'

    # The private account is unaffected.
    assert monthly_balances(path, db.get_account(path, 1), 2025)[3].get('mat') == 0


def test_hidden_categories_and_cash_flow(path):
    from budget import cash_flow, hidden_categories
    private = db.get_account(path, 1)
    add(path, 1, '2025-05-01', -300, 'mat', 'butik')
    add(path, 1, '2025-05-02', -50, 'mat', 'fika')
    add(path, 1, '2025-05-03', 1000, 'inkomst', 'ränta')
    add(path, 1, '2025-05-04', -20, None, None)
    fika = next(c for c in db.get_categories(path, 1) if c.sub_category == 'fika')
    db.set_category_hidden(path, 1, True, category_id=fika.id)
    db.set_category_hidden(path, 1, True, main_category='bokföring')

    categories = db.get_categories(path, 1)
    hidden = hidden_categories(categories)
    balances = monthly_balances(path, private, 2025)
    rows = budget_table(balances, show_sub_category=True, hidden=hidden)
    mains = [r.main_category for r in rows if not r.is_sub]
    assert 'bokföring' not in mains
    mat = next(r for r in rows if r.main_category == 'mat' and not r.is_sub)
    assert mat.values[4] == 300
    assert ('mat', 'fika') not in {(r.main_category, r.sub_category) for r in rows}
    # Uncategorized shows up only when it has transactions.
    assert mains[-1] == 'uncategorized'
    assert 'uncategorized' not in [r.main_category for r in
                                   budget_table(monthly_balances(path, private, 2024), hidden=hidden)]

    flow = cash_flow(balances, categories)
    assert flow.income[4] == 1000
    assert flow.expenses[4] == 300 + 20
    assert flow.expenses_by_main['mat'][4] == 300
    assert flow.expenses_by_main['uncategorized'][4] == 20


def test_rename_main_category(path):
    add(path, 1, '2025-05-01', -300, 'Mat', 'butik')
    db.rename_main_category(path, 1, 'mat', 'Livsmedel')
    assert db.get_transactions(path, 1)[0].main_category == 'livsmedel'
    assert {c.main_category for c in db.get_categories(path, 1)} >= {'livsmedel'}
    assert 'mat' not in {c.main_category for c in db.get_categories(path, 1)}
    db.add_category(path, 1, 'nöje', 'butik')
    with pytest.raises(ValueError, match='already exists'):
        db.rename_main_category(path, 1, 'livsmedel', 'nöje')
