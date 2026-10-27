import re
from datetime import datetime

import pytest
from click.testing import CliRunner

import database as db
from app import cli
from app_types import Transaction
from budget import monthly_balances, split_acknowledged, zero_check_flags
from ha_sensors import account_states
from webapp import create_app


@pytest.fixture
def path(tmp_path):
    p = str(tmp_path / 'acks.db')
    db.create_tables(p)
    return p


def outlay(path, date, amount):
    db.insert_transaction(path, 1, Transaction(date, 'X', amount, 'SEB', 'bokföring', 'utlägg/skuld'))


def flags(path, year=2024):
    balances = monthly_balances(path, db.get_account(path, 1), year)
    return split_acknowledged(zero_check_flags(balances, db.get_categories(path, 1), 12),
                              db.get_zero_check_acks(path, 1, year))


def test_acknowledge_and_undo(path):
    outlay(path, '2024-03-10', -650)
    outlay(path, '2024-05-10', -100)
    open_flags, acked = flags(path)
    assert [f.month for f in open_flags] == [3, 5] and acked == []

    db.acknowledge_zero_check(path, 1, 'bokföring', 'utlägg/skuld', 2024, 3, 650)
    open_flags, acked = flags(path)
    assert [f.month for f in open_flags] == [5]
    assert [f.month for f in acked] == [3] and acked[0].acknowledged_at

    # A new outlay in March changes the amount: the warning is back.
    outlay(path, '2024-03-20', -50)
    open_flags, acked = flags(path)
    assert [f.month for f in open_flags] == [3, 5] and acked == []

    db.acknowledge_zero_check(path, 1, 'bokföring', 'utlägg/skuld', 2024, 3, 700)
    db.unacknowledge_zero_check(path, 1, 'bokföring', 'utlägg/skuld', 2024, 3)
    assert [f.month for f in flags(path)[0]] == [3, 5]


def test_acknowledgements_follow_renames(path):
    outlay(path, '2024-03-10', -650)
    db.acknowledge_zero_check(path, 1, 'bokföring', 'utlägg/skuld', 2024, 3, 650)
    sub = next(c for c in db.get_categories(path, 1) if c.sub_category == 'utlägg/skuld')
    db.update_category(path, 1, sub.id, 'bokföring', 'skulder', True)
    db.rename_main_category(path, 1, 'bokföring', 'konton')
    assert list(db.get_zero_check_acks(path, 1, 2024)) == [('konton', 'skulder', 3)]
    assert flags(path)[0] == []


@pytest.fixture
def client(path):
    app = create_app(path)
    app.testing = True
    return app.test_client()


def test_web(client, path):
    outlay(path, '2024-03-10', -650)
    html = client.get('/1/?year=2024').get_data(as_text=True)
    assert 'Should be 0 every month' in html and 'Acknowledge' in html
    assert len(re.findall(r'class="num m m3 flag"', html)) == 1

    response = client.post('/1/checks', data={
        'main': 'bokföring', 'sub': 'utlägg/skuld', 'year': '2024', 'month': '3',
        'amount': '650.00', 'subs': '1', 'm': '3', 'action': 'ack'})
    assert response.headers['Location'].endswith('/1/?year=2024&subs=1&m=3')
    html = client.get('/1/?year=2024').get_data(as_text=True)
    assert 'Should be 0 every month' not in html
    assert 'flag"' not in html
    assert '1 acknowledged warning' in html and 'Undo' in html

    client.post('/1/checks', data={'main': 'bokföring', 'sub': 'utlägg/skuld', 'year': '2024',
                                   'month': '3', 'action': 'undo'})
    assert 'Should be 0 every month' in client.get('/1/?year=2024').get_data(as_text=True)

    assert client.post('/1/checks', data={'year': '2024'}).status_code == 400


def test_sensor_counts_open_warnings_only(path):
    outlay(path, '2025-01-10', -650)
    outlay(path, '2025-02-10', -100)
    db.acknowledge_zero_check(path, 1, 'bokföring', 'utlägg/skuld', 2025, 1, 650)
    check = account_states(path, db.get_account(path, 1), now=datetime(2025, 3, 15))[
        'sensor.economics_privat_debt_check']
    assert check['state'] == 1
    assert check['attributes']['acknowledged'] == 1
    assert [x['month'] for x in check['attributes']['not_zero']] == ['2025-02']


def test_cli(path):
    outlay(path, '2024-03-10', -650)
    runner = CliRunner()
    run = lambda *args: runner.invoke(cli, ['--db', path, *args])

    assert 'WARNING' in run('check', 'list', '--year', '2024').output
    result = run('check', 'ack', 'bokföring/utlägg/skuld', '2024-03')
    assert result.exit_code == 0, result.output
    assert 'acknowledged' in run('check', 'list', '--year', '2024').output
    balance = run('balance', '--year', '2024').output
    assert 'WARNING' not in balance and '(1 acknowledged' in balance

    assert run('check', 'ack', 'bokföring/utlägg/skuld', '2024-03').exit_code != 0  # nothing open
    assert run('check', 'ack', 'bokföring', '2024-03').exit_code != 0
    assert run('check', 'undo', 'bokföring/utlägg/skuld', '2024-03').exit_code == 0
    assert 'WARNING' in run('balance', '--year', '2024').output
