import re
from datetime import datetime

import pytest
from click.testing import CliRunner

import database as db
from app import cli
from app_types import Transaction
from budget import cash_flow, monthly_balances, summary_checks, summary_rows
from ha_sensors import account_states
from webapp import create_app


@pytest.fixture
def path(tmp_path):
    p = str(tmp_path / 'balance.db')
    db.create_tables(p)
    return p


def add(path, date, amount, main, sub, account_id=1):
    db.insert_transaction(path, account_id, Transaction(date, 'X', amount, 'SEB', main, sub))


def rows(path, account_id, year=2024, budgets=None):
    balances = monthly_balances(path, db.get_account(path, account_id), year)
    return {s.key: s for s in summary_rows(balances, db.get_categories(path, account_id), budgets)}


def test_balance_is_income_minus_expenses(path):
    family = db.create_account(path, 'Familj', 'family')
    add(path, '2024-03-25', 30000, 'inkomst', 'insättning rikard', family)
    add(path, '2024-03-10', -12000, 'boende', 'avgift/hyra', family)
    add(path, '2024-03-11', -3000, 'mat', 'butik', family)
    add(path, '2024-03-12', -5000, 'sparande', 'övrigt', family)   # a transfer: neither
    add(path, '2024-04-10', -500, 'mat', 'butik', family)          # a month with only costs

    balance = rows(path, family)['balance']
    assert balance.values[2] == 30000 - 15000
    assert balance.values[3] == -500
    assert balance.total == 14500
    assert balance.budget is None


def test_derived_allowance_is_not_counted_twice(path):
    # Privat: salary booked as bokföring/inkomst; inkomst/månadspeng is derived from it.
    add(path, '2024-03-25', 30000, 'bokföring', 'inkomst')
    add(path, '2024-03-26', -15000, 'bokföring', 'familjekonto')
    add(path, '2024-03-10', -1200, 'mat', 'butik')

    r = rows(path, 1)
    assert r['expenses'].values[2] == 16200
    assert r['balance'].values[2] == 30000 - 16200
    assert 'Månadspeng is not counted' in r['balance'].hint

    flow = cash_flow(monthly_balances(path, db.get_account(path, 1), 2024), db.get_categories(path, 1))
    assert flow.income[2] == 30000


def test_derived_allowance_is_the_income_when_bokforing_is_hidden(path):
    # Bokföring hidden from the budget: the salary isn't counted, so the månadspeng
    # (salary − family account − last month's family outlays) is the income.
    db.set_category_hidden(path, 1, True, main_category='bokföring')
    add(path, '2024-02-20', -800, 'bokföring', 'familjeutlägg')
    add(path, '2024-03-25', 30000, 'bokföring', 'inkomst')
    add(path, '2024-03-26', -15000, 'bokföring', 'familjekonto')
    add(path, '2024-03-10', -1200, 'mat', 'butik')
    add(path, '2024-03-11', 250, 'inkomst', 'ränta')

    r = rows(path, 1)
    assert r['expenses'].values[2] == 1200
    assert r['balance'].values[2] == (30000 - 15000 - 800) + 250 - 1200
    assert 'Inkomst › Månadspeng counts as income' in r['balance'].hint

    flow = cash_flow(monthly_balances(path, db.get_account(path, 1), 2024), db.get_categories(path, 1))
    assert flow.income[2] == 14450 and flow.expenses[2] == 1200

    # A hidden månadspeng is not income either.
    allowance = next(c.id for c in db.get_categories(path, 1)
                     if (c.main_category, c.sub_category) == ('inkomst', 'månadspeng'))
    db.set_category_hidden(path, 1, True, category_id=allowance)
    assert rows(path, 1)['balance'].values[2] == 250 - 1200


def test_budgets_on_the_summary_rows(path):
    family = db.create_account(path, 'Familj', 'family')
    db.set_group_kind(path, family, 'boende', True, 'fixed')
    budgets = {'boende': 12000, 'mat': 4000, 'inkomst': 30000}
    for main, amount in budgets.items():
        db.set_budget(path, family, main, amount)
    add(path, '2024-03-25', 30000, 'inkomst', 'insättning rikard', family)
    add(path, '2024-03-10', -12000, 'boende', 'avgift/hyra', family)
    add(path, '2024-03-11', -5000, 'mat', 'butik', family)          # 1 000 over the food budget
    add(path, '2024-04-25', 30000, 'inkomst', 'insättning rikard', family)
    add(path, '2024-04-10', -12000, 'boende', 'avgift/hyra', family)
    add(path, '2024-04-11', -3000, 'mat', 'butik', family)

    r = rows(path, family, budgets=db.get_budgets(path, family))
    assert r['expenses'].budget == 16000
    assert r['variable'].budget == 4000
    assert r['balance'].budget == 30000 - 16000

    checks = summary_checks(list(r.values()), 2024, list(range(1, 13)), now=datetime(2024, 5, 15))
    assert checks['expenses'].red_months == {3}
    assert checks['variable'].red_months == {3}
    assert checks['balance'].red_months == {1, 2, 3}  # under 14 000 (Jan, Feb had nothing)
    assert checks['balance'].describe(3, 13000) == '1 000 kr under the budget of 14 000 kr'

    # Without an income budget, the balance has none either.
    db.set_budget(path, family, 'inkomst', None)
    assert rows(path, family, budgets=db.get_budgets(path, family))['balance'].budget is None


@pytest.fixture
def client(path):
    app = create_app(path)
    app.testing = True
    return app.test_client()


def test_budget_page(client, path):
    add(path, '2024-03-10', -1200, 'mat', 'butik')
    add(path, '2024-03-11', 500, 'inkomst', 'ränta')
    html = client.get('/1/?year=2024').get_data(as_text=True)
    balance = re.search(r'<th scope="row"[^>]*>Balance</th>(.*?)</tr>', html, re.S).group(1)
    assert '−700' in balance and ' over"' not in balance
    assert '>Budget</th>' not in html

    db.set_budget(path, 1, 'mat', 1000)
    html = client.get('/1/?year=2024').get_data(as_text=True)
    expenses = re.search(r'<th scope="row"[^>]*>Expenses</th>(.*?)</tr>', html, re.S).group(1)
    assert '<td class="num budget-col">1 000</td>' in expenses
    assert re.search(r'class="num m m3 over" title="200 kr over the budget of 1 000 kr"', expenses)
    balance = re.search(r'<th scope="row"[^>]*>Balance</th>(.*?)</tr>', html, re.S).group(1)
    assert '<td class="num budget-col"></td>' in balance  # no income budget


def test_sensor_and_cli(path):
    add(path, '2025-03-10', -1200, 'mat', 'butik')
    add(path, '2025-03-11', 500, 'inkomst', 'ränta')
    add(path, '2025-02-11', 100, 'inkomst', 'ränta')
    sensor = account_states(path, db.get_account(path, 1), now=datetime(2025, 3, 15))[
        'sensor.economics_privat_balance']
    assert sensor['state'] == -700
    assert sensor['attributes']['previous_month'] == 100
    assert sensor['attributes']['year_to_date'] == -600

    result = CliRunner().invoke(cli, ['--db', path, 'balance', '--year', '2025'])
    assert result.exit_code == 0, result.output
    assert re.search(r'^Balance\s+0\s+100\s+-700\s', result.output, re.M)
