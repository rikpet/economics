import json
import re
import sqlite3
from datetime import datetime

import pytest
from click.testing import CliRunner

import database as db
from app import cli
from app_types import Transaction
from budget import cash_flow, completed_months, monthly_balances, summary_rows, zero_check_flags
from ha_sensors import account_states
from webapp import create_app


@pytest.fixture
def path(tmp_path):
    p = str(tmp_path / 'summary.db')
    db.create_tables(p)
    return p


def add(path, date, amount, main=None, sub=None, account_id=1):
    db.insert_transaction(path, account_id, Transaction(date, 'X', amount, 'SEB', main, sub))


def category(path, main, sub, account_id=1):
    return next(c for c in db.get_categories(path, account_id)
                if c.main_category == main and c.sub_category == sub)


def test_defaults(path):
    assert category(path, 'sparande', 'övrigt').kind == 'transfer'
    assert category(path, 'hushåll', 'landet').kind == 'fixed'
    assert category(path, 'mat', 'butik').kind == 'expense'
    assert category(path, 'inkomst', 'ränta').kind == 'income'
    assert category(path, 'bokföring', 'utlägg/skuld').zero_check
    assert category(path, 'bokföring', 'internöverföring').kind == 'transfer'
    assert category(path, 'bokföring', 'familjekonto').kind == 'expense'
    assert not category(path, 'mat', 'butik').zero_check

    family = db.create_account(path, 'Familj', 'family')
    assert category(path, 'sparande', 'övrigt', family).kind == 'transfer'
    new = db.add_category(path, 1, 'Sparande', 'Fonder')
    assert db.get_category(path, 1, new).kind == 'transfer'


def test_migration_sets_defaults_on_an_existing_database(tmp_path):
    p = str(tmp_path / 'v4.db')
    db.create_tables(p)
    conn = sqlite3.connect(p)
    # Pretend the database is at version 4: drop the columns migration 5 adds.
    conn.executescript('''
        CREATE TABLE c2 AS SELECT id, account_id, main_category, sub_category, invert_sign,
            position, hidden FROM categories;
        DROP TABLE categories; ALTER TABLE c2 RENAME TO categories;
        DROP TABLE budgets;
        PRAGMA user_version = 4;
    ''')
    conn.close()
    db.create_tables(p)
    assert db.schema_version(p) == len(db.MIGRATIONS)
    assert category(p, 'sparande', 'övrigt').kind == 'transfer'
    assert category(p, 'hushåll', 'övrigt').kind == 'fixed'
    assert category(p, 'bokföring', 'utlägg/skuld').zero_check


def test_summary_rows(path):
    add(path, '2025-03-01', -500, 'mat', 'butik')
    add(path, '2025-03-02', -1000, 'hushåll', 'landet')       # fixed
    add(path, '2025-03-03', -3000, 'sparande', 'övrigt')      # transfer: not an expense
    add(path, '2025-03-04', 20000, 'inkomst', 'övrigt')       # income
    add(path, '2025-03-05', -40, None, None)                  # unclassified: an expense
    add(path, '2025-03-06', -60, 'nöje', 'kultur')
    db.set_category_hidden(path, 1, True, category_id=category(path, 'nöje', 'kultur').id)

    balances = monthly_balances(path, db.get_account(path, 1), 2025)
    categories = db.get_categories(path, 1)
    expenses, variable = summary_rows(balances, categories)
    assert expenses.values[2] == 500 + 1000 + 40
    assert variable.values[2] == 500 + 40
    assert 'Hushåll' in variable.hint

    flow = cash_flow(balances, categories)
    assert flow.expenses[2] == 500 + 1000 + 40
    assert 'sparande' not in flow.expenses_by_main
    assert flow.income[2] == 20000


def test_zero_check(path):
    add(path, '2025-02-10', -300, 'bokföring', 'utlägg/skuld')
    add(path, '2025-02-20', 300, 'bokföring', 'utlägg/skuld')   # paid back: 0 in February
    add(path, '2025-03-10', -700, 'bokföring', 'utlägg/skuld')  # not paid back in March
    add(path, '2025-04-10', -50, 'bokföring', 'utlägg/skuld')   # April is still running

    balances = monthly_balances(path, db.get_account(path, 1), 2025)
    flags = zero_check_flags(balances, db.get_categories(path, 1),
                             completed_months(2025, datetime(2025, 4, 15)))
    assert [(f.month, f.value) for f in flags] == [(3, 700)]
    assert completed_months(2024, datetime(2025, 4, 15)) == 12
    assert completed_months(2026, datetime(2025, 4, 15)) == 0


@pytest.fixture
def client(path):
    app = create_app(path)
    app.testing = True
    return app.test_client()


def test_budget_page(client, path):
    add(path, '2024-03-01', -500, 'mat', 'butik')
    add(path, '2024-03-02', -1000, 'hushåll', 'landet')
    add(path, '2024-08-10', -300, 'bokföring', 'utlägg/skuld')

    html = client.get('/1/?year=2024').get_data(as_text=True)
    expenses = re.search(r'<th scope="row"[^>]*>Expenses</th>(.*?)</tr>', html, re.S).group(1)
    assert re.findall(r'<td class="num">([^<]+)</td>', expenses)[0] == '1 500'
    variable = re.search(r'Expenses excl. fixed costs</th>(.*?)</tr>', html, re.S).group(1)
    assert re.findall(r'<td class="num">([^<]+)</td>', variable)[0] == '500'

    assert 'Should be 0 every month' in html
    assert 'Bokföring › Utlägg/skuld is' in html and 'in Aug' in html
    assert html.count('class="num flag"') == 1  # the Bokföring cell for August

    html = client.get('/1/?year=2024&subs=1').get_data(as_text=True)
    assert html.count('class="num flag"') == 2  # and the Utlägg/skuld cell


def test_categories_page_types(client, path):
    butik = category(path, 'mat', 'butik')
    client.post(f'/1/categories/{butik.id}', data={'main': 'mat', 'sub': 'butik', 'kind': 'fixed',
                                                  'visible': '1', 'zero_check': '1'})
    butik = db.get_category(path, 1, butik.id)
    assert butik.kind == 'fixed' and butik.zero_check and not butik.hidden

    client.post('/1/categories/group', data={'main': 'nöje', 'kind': 'transfer', 'action': 'kind'})
    assert {c.kind for c in db.get_categories(path, 1) if c.main_category == 'nöje'} == {'transfer'}

    client.post('/1/categories', data={'main': 'Barn', 'sub': 'Bidrag', 'kind': 'income'})
    assert category(path, 'barn', 'bidrag').kind == 'income'

    html = client.get('/1/categories').get_data(as_text=True)
    assert 'Fixed expense' in html and 'Transfer / savings' in html and '0 monthly' in html


def test_sensors(path):
    add(path, '2025-03-01', -500, 'mat', 'butik')
    add(path, '2025-03-02', -1000, 'hushåll', 'landet')
    add(path, '2025-02-02', -200, 'mat', 'butik')
    add(path, '2025-02-10', -300, 'bokföring', 'utlägg/skuld')
    states = account_states(path, db.get_account(path, 1), now=datetime(2025, 3, 15))

    expenses = states['sensor.economics_privat_expenses']
    assert expenses['state'] == 1500
    assert expenses['attributes']['excl_fixed_costs'] == 500
    assert expenses['attributes']['previous_month'] == 200 + 300
    assert expenses['attributes']['year_to_date'] == 2000

    check = states['sensor.economics_privat_debt_check']
    assert check['state'] == 1
    assert check['attributes']['not_zero'] == [
        {'category': 'bokföring/utlägg/skuld', 'month': '2025-02', 'amount': 300}]


def test_cli_balance(path):
    add(path, '2024-03-01', -500, 'mat', 'butik')
    add(path, '2024-08-10', -300, 'bokföring', 'utlägg/skuld')
    result = CliRunner().invoke(cli, ['--db', path, 'balance', '--year', '2024'])
    assert result.exit_code == 0, result.output
    assert re.search(r'^Expenses\s+0\s+0\s+500\s', result.output, re.M)
    assert 'Expenses excl. fixed costs' in result.output
    assert 'WARNING: bokföring/utlägg/skuld is 300, not 0, in August' in result.output
