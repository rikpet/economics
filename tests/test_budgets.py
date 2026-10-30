import re
from datetime import datetime

import pytest
from click.testing import CliRunner

import database as db
from app import cli
from app_types import Transaction
from budget import average_months, budget_checks, budget_table, monthly_balances
from ha_sensors import account_states
from webapp import create_app


@pytest.fixture
def path(tmp_path):
    p = str(tmp_path / 'budgets.db')
    db.create_tables(p)
    return p


def add(path, date, amount, main, sub, account_id=1):
    db.insert_transaction(path, account_id, Transaction(date, 'X', amount, 'SEB', main, sub))


def test_store_budgets(path):
    assert db.get_budgets(path, 1) == {}
    db.set_budget(path, 1, 'Mat', 3000)
    db.set_budget(path, 1, 'mat', 3500)
    assert db.get_budgets(path, 1) == {'mat': 3500}
    with pytest.raises(ValueError, match='negative'):
        db.set_budget(path, 1, 'mat', -1)

    db.rename_main_category(path, 1, 'mat', 'livsmedel')
    assert db.get_budgets(path, 1) == {'livsmedel': 3500}

    family = db.create_account(path, 'Familj', 'family')
    db.set_budget(path, family, 'boende', 9000)
    assert db.get_budgets(path, 1) == {'livsmedel': 3500}  # per account
    db.delete_account(path, family)

    db.set_budget(path, 1, 'livsmedel', None)
    assert db.get_budgets(path, 1) == {}


def checks_for(path, year, now):
    account = db.get_account(path, 1)
    balances = monthly_balances(path, account, year)
    rows = budget_table(balances)
    return budget_checks(rows, db.get_budgets(path, 1), db.get_categories(path, 1), year,
                         list(balances), now=now)


def test_expense_budget(path):
    db.set_budget(path, 1, 'mat', 3000)
    add(path, '2025-01-10', -2500, 'mat', 'butik')
    add(path, '2025-02-10', -3200, 'mat', 'butik')   # over
    add(path, '2025-03-10', -3000, 'mat', 'butik')   # exactly on budget: not over
    add(path, '2025-04-10', -3400, 'mat', 'butik')   # the running month, already over

    check = checks_for(path, 2025, datetime(2025, 4, 15))['mat']
    assert check.red_months == {2, 4}
    assert not check.is_income
    assert not check.average_red  # 2 900 a month over Jan–Mar, the finished months
    assert check.describe(2, 3200) == '200 kr over the budget of 3 000 kr'

    # Over budget on average: the average turns red.
    add(path, '2025-01-20', -600, 'mat', 'butik')
    assert checks_for(path, 2025, datetime(2025, 4, 15))['mat'].average_red  # 3 100 a month


def test_average_months():
    assert average_months(2025, datetime(2025, 4, 15)) == 3   # Jan–Mar are over
    assert average_months(2025, datetime(2025, 1, 15)) == 1   # January: the running month
    assert average_months(2024, datetime(2025, 1, 15)) == 12
    assert average_months(2026, datetime(2025, 1, 15)) == 0   # nothing has started


def test_income_budget(path):
    db.set_budget(path, 1, 'inkomst', 1000)
    add(path, '2025-01-25', 1200, 'inkomst', 'ränta')
    add(path, '2025-02-25', 800, 'inkomst', 'ränta')   # under: red
    # March is running and still empty: not judged yet.
    check = checks_for(path, 2025, datetime(2025, 3, 10))['inkomst']
    assert check.is_income and check.red_months == {2}
    assert not check.average_red  # 1 000 a month over Jan–Feb


def test_without_budgets_nothing_is_red(path):
    assert checks_for(path, 2025, datetime(2025, 4, 15)) == {}


@pytest.fixture
def client(path):
    app = create_app(path)
    app.testing = True
    return app.test_client()


def test_budget_page(client, path):
    add(path, '2024-02-10', -3200, 'mat', 'butik')
    add(path, '2024-03-10', -1000, 'mat', 'butik')

    html = client.get('/1/?year=2024').get_data(as_text=True)
    assert ' over"' not in html and 'over budget' not in html
    assert '>Budget</th>' not in html

    client.post('/1/categories/group', data={'main': 'mat', 'action': 'budget', 'budget': '3 000'})
    assert db.get_budgets(path, 1) == {'mat': 3000}

    html = client.get('/1/?year=2024').get_data(as_text=True)
    assert '>Budget</th>' in html
    mat = re.search(r'<th scope="row">Mat</th>(.*?)</tr>', html, re.S).group(1)
    red = re.findall(r'<td class="num m m\d+ over" title="([^"]+)">', mat)
    assert red == ['200 kr over the budget of 3 000 kr']
    assert 'class="num total over"' not in mat  # 350 a month on average
    assert '<td class="num total">350</td>' in mat  # 4 200 over the 12 months of 2024
    assert 'title="Average per month, Jan–Dec">Average</th>' in html

    html = client.get('/1/categories').get_data(as_text=True)
    assert 'value="3000"' in html

    client.post('/1/categories/group', data={'main': 'mat', 'action': 'budget', 'budget': ''})
    assert db.get_budgets(path, 1) == {}
    assert ' over"' not in client.get('/1/?year=2024').get_data(as_text=True)


def test_cli(path):
    runner = CliRunner()
    result = runner.invoke(cli, ['--db', path, 'category', 'budget', 'mat', '3000'])
    assert result.exit_code == 0, result.output
    assert db.get_budgets(path, 1) == {'mat': 3000}
    assert 'Budget for mat: 3000 a month' in runner.invoke(
        cli, ['--db', path, 'category', 'budget', 'mat']).output
    assert runner.invoke(cli, ['--db', path, 'category', 'budget', 'nope', '1']).exit_code != 0

    add(path, '2024-02-10', -3200, 'mat', 'butik')
    result = runner.invoke(cli, ['--db', path, 'balance', '--year', '2024'])
    assert result.exit_code == 0, result.output
    assert re.search(r'^Mat\s+3000\s+0\s+3200\s', result.output, re.M)
    assert '3000' in runner.invoke(cli, ['--db', path, 'category', 'list']).output

    runner.invoke(cli, ['--db', path, 'category', 'budget', 'mat', '--clear'])
    assert db.get_budgets(path, 1) == {}


def test_sensor_attributes(path):
    db.set_budget(path, 1, 'mat', 3000)
    db.set_budget(path, 1, 'inkomst', 1000)
    add(path, '2025-03-02', -3500, 'mat', 'butik')
    states = account_states(path, db.get_account(path, 1), now=datetime(2025, 3, 15))
    mat = states['sensor.economics_rikard_mat']['attributes']
    assert (mat['budget'], mat['over_budget'], mat['budget_left']) == (3000, True, -500)
    inkomst = states['sensor.economics_rikard_inkomst']['attributes']
    assert inkomst['budget'] == 1000 and 'over_budget' not in inkomst
    assert 'budget' not in states['sensor.economics_rikard_hushall']['attributes']
