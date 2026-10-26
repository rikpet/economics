import pytest
from src.app_types import Category, ReadTransaction
from src.balance import Balance, SubCategory

def test_subcategory_add_and_invert():
    sub = SubCategory()
    sub.add(100)
    assert sub() == 100
    sub.reset()
    assert sub() == 0
    sub_inv = SubCategory(invert_sign=True)
    sub_inv.add(100)
    assert sub_inv() == -100

def test_subcategory_set():
    sub = SubCategory()
    sub.set(42)
    assert sub() == 42

def test_balance_add_and_get():
    balance = Balance(2025, 2)
    t = ReadTransaction(
        id=1,
        date='2025-02-15',
        issuer='Test Issuer',
        amount=1000,
        origin='Test Origin',
        main_category='inkomst',
        sub_category='övrigt'
    )
    balance.add(t)
    assert balance.get('inkomst') == 1000

def test_balance_add_several():
    balance = Balance(2025, 2)
    txs = [
        ReadTransaction(1, '2025-02-01', 'A', 100, 'O', 'mat', 'butik'),
        ReadTransaction(2, '2025-02-02', 'B', 200, 'O', 'mat', 'butik'),
    ]
    balance.add_several(txs)
    assert balance.get('mat') == -300

def test_balance_set_dept_and_income_calc():
    balance = Balance(2025, 2)
    # Set up for income calculation
    balance.balance['bokföring']['inkomst'].set(2000)
    balance.balance['bokföring']['familjekonto'].set(500)
    balance.set_dept(100)
    # This should set 'månadspeng' in 'inkomst' to 2000-500-100 = 1400
    result = balance.get('inkomst')
    assert balance.balance['inkomst']['månadspeng']() == 1400
    assert result == 1400

def test_balance_get_sub_category():
    balance = Balance(2025, 2)
    balance.balance['mat']['butik'].set(-123)
    assert balance.get_sub_category('mat', 'butik') == -123

def test_balance_categories_and_subcategories():
    balance = Balance(2025, 2)
    cats = balance.categories()
    assert 'mat' in cats
    subcats = balance.sub_categories('mat')
    assert 'butik' in subcats

def test_balance_add_invalid_main_category():
    balance = Balance(2025, 2)
    t = ReadTransaction(1, '2025-02-01', 'A', 100, 'O', 'invalid', 'butik')
    balance.add(t)
    assert balance.get('uncategorized') == 100

def test_balance_add_invalid_sub_category():
    balance = Balance(2025, 2)
    t = ReadTransaction(1, '2025-02-01', 'A', 100, 'O', 'mat', 'invalid')
    balance.add(t)
    assert balance.get('mat') == 0
    assert balance.get('uncategorized') == 100

def test_balance_category_names_are_case_insensitive():
    balance = Balance(2025, 2)
    balance.add(ReadTransaction(1, '2025-02-01', 'A', -50, 'O', 'Övrigt', 'Bankkostnader'))
    assert balance.get_sub_category('övrigt', 'bankkostnader') == 50

def test_balance_with_custom_categories():
    categories = [
        Category(1, 'boende', 'el', True),
        Category(2, 'inkomst', 'lön', False),
    ]
    balance = Balance(2025, 2, categories=categories)
    balance.add(ReadTransaction(1, '2025-02-01', 'A', -400, 'O', 'boende', 'el'))
    balance.add(ReadTransaction(2, '2025-02-25', 'B', 30000, 'O', 'inkomst', 'lön'))
    assert balance.categories() == ['boende', 'inkomst', 'uncategorized']
    assert balance.get('boende') == 400
    # No bokföring categories, so the allowance is not derived.
    assert balance.derive_allowance is False
    assert balance.get('inkomst') == 30000

def test_balance_derive_allowance_disabled():
    balance = Balance(2025, 2, dept=100, derive_allowance=False)
    balance.balance['bokföring']['inkomst'].set(2000)
    assert balance.get('inkomst') == 0

def test_balance_get_invalid_category():
    balance = Balance(2025, 2)
    with pytest.raises(ValueError, match='Unknown category'):
        balance.get('invalid')

def test_balance_get_income_missing_dept():
    balance = Balance(2025, 2, dept=None)
    balance.balance['bokföring']['inkomst'].set(1000)
    balance.balance['bokföring']['familjekonto'].set(100)
    with pytest.raises(ValueError, match="Missing 'dept' argument"):
        balance.get('inkomst')

def test_balance_get_sub_category_invalid_main():
    balance = Balance(2025, 2)
    with pytest.raises(ValueError, match='Unknown category'):
        balance.get_sub_category('invalid', 'butik')

def test_balance_get_sub_category_invalid_sub():
    balance = Balance(2025, 2)
    with pytest.raises(ValueError, match='Unknown sub-category'):
        balance.get_sub_category('mat', 'invalid')

def test_balance_sub_categories_invalid_main():
    balance = Balance(2025, 2)
    with pytest.raises(ValueError, match='Unknown category'):
        balance.sub_categories('invalid')