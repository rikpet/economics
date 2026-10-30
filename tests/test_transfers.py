import sqlite3

import pytest

import database as db
from app_types import PersonMonth, Transaction
from transfers import ALLOWANCE_SETTING, parse_sum, transfer_year
from webapp import create_app

PRIVAT = 1  # the account called Rikard


@pytest.fixture
def path(tmp_path):
    p = str(tmp_path / 'transfers.db')
    db.create_tables(p)
    return p


@pytest.fixture
def family(path):
    return db.create_account(path, 'Familj', 'family')


@pytest.fixture
def client(path):
    app = create_app(path)
    app.testing = True
    return app.test_client()


def booked(path, date, sub, amount):
    db.insert_transaction(path, PRIVAT, Transaction(date, 'TEST TESTSSON', amount, 'SEB',
                                                    main_category='bokföring', sub_category=sub))


@pytest.mark.parametrize('text, value', [
    ('', None), ('  ', None), ('40000', 40000), ('1 234,50', 1234.5), ('=700+500', 1200),
    ('=-150+100+700+250', 900), ('50000-8000', 42000), ('−500', -500), ('1000 kr', 1000),
])
def test_parse_sum(text, value):
    assert parse_sum(text) == value


@pytest.mark.parametrize('text', ['abc', '12+', '1++2', '=SUM(A1:A2)'])
def test_parse_sum_rejects(text):
    with pytest.raises(ValueError):
        parse_sum(text)


def test_transfer_is_income_minus_expenses_minus_allowance(path, family):
    sara = db.add_person(path, family, 'TEST TESTSSON')
    db.set_person_month(path, family, PersonMonth(sara, 2025, 3, income=40000, costs=1200))
    db.set_person_month(path, family, PersonMonth(sara, 2025, 4, income=40000))

    months = transfer_year(path, family, 2025)[sara]
    assert (months[2].allowance, months[2].to_account) == (12000, 26800)  # the default
    assert not months[0].has_data and not months[5].has_data

    # A month can have its own allowance; the others keep the default.
    db.set_allowance_month(path, family, 2025, 3, 10000)
    months = transfer_year(path, family, 2025)[sara]
    assert (months[2].allowance, months[2].to_account) == (10000, 28800)
    assert months[3].allowance == 12000

    # The default can be changed.
    db.set_setting(path, family, ALLOWANCE_SETTING, '11000')
    db.set_person_month(path, family, PersonMonth(sara, 2025, 5, income=2000))
    months = transfer_year(path, family, 2025)[sara]
    assert (months[3].allowance, months[2].allowance) == (11000, 10000)
    assert months[4].to_account == -9000  # negative: the joint account pays

    db.set_allowance_month(path, family, 2025, 3, None)
    assert transfer_year(path, family, 2025)[sara][2].allowance == 11000


def test_debt_in_the_linked_account_is_added_the_month_after(path, family):
    rikard = db.add_person(path, family, 'Rikard', linked_account_id=PRIVAT)
    booked(path, '2025-02-20', 'familjeutlägg', -600)
    booked(path, '2025-03-25', 'inkomst', 42000)
    booked(path, '2025-03-26', 'familjekonto', -30000)

    march = transfer_year(path, family, 2025)[rikard][2]
    assert (march.income, march.debt, march.costs, march.transferred) == (42000, 600, 600, 30000)
    assert march.has_data and march.to_account == 42000 - 600 - 12000

    # Shared expenses typed in come on top of the debt; an income typed in wins.
    db.set_person_month(path, family, PersonMonth(rikard, 2025, 3, costs=1000, costs_input='=600+400'))
    assert transfer_year(path, family, 2025)[rikard][2].costs == 1600
    db.set_person_month(path, family, PersonMonth(rikard, 2025, 3, income=41000, costs=1000))
    assert transfer_year(path, family, 2025)[rikard][2].to_account == 41000 - 1600 - 12000

    # January uses the debt of December the year before.
    booked(path, '2024-12-10', 'familjeutlägg', -300)
    booked(path, '2025-01-25', 'inkomst', 41000)
    january = transfer_year(path, family, 2025)[rikard][0]
    assert (january.costs, january.to_account) == (300, 41000 - 300 - 12000)


def test_people_are_scoped_to_their_account(path, family):
    person = db.add_person(path, family, 'TEST TESTSSON')
    assert db.get_people(path, PRIVAT) == []
    assert db.get_person(path, PRIVAT, person) is None
    with pytest.raises(ValueError):
        db.set_person_month(path, PRIVAT, PersonMonth(person, 2025, 1, income=1))
    with pytest.raises(ValueError):
        db.add_person(path, family, 'test testsson')  # already there
    with pytest.raises(ValueError):
        db.add_person(path, family, 'Other', linked_account_id=family)  # not to itself

    db.set_person_month(path, family, PersonMonth(person, 2025, 1, income=1))
    db.set_allowance_month(path, family, 2025, 1, 5000)
    assert db.get_allowance_months(path, PRIVAT, 2025) == {}
    db.delete_account(path, family)
    assert db.get_person_months(path, family, 2025) == []
    assert db.get_allowance_months(path, family, 2025) == {}


def test_allowance_page(client, path, family):
    html = client.get(f'/{PRIVAT}/').get_data(as_text=True)
    assert f'href="/{family}/transfers" >Allowance</a>' in html  # the nav goes to the joint account

    html = client.get(f'/{family}/transfers').get_data(as_text=True)
    assert 'Add the people who transfer money to Familj' in html

    client.post(f'/{family}/transfers/people', data={'name': 'TEST TESTSSON'})
    client.post(f'/{family}/transfers/people', data={'name': 'Rikard', 'linked_account_id': str(PRIVAT)})
    sara, rikard = (p.id for p in db.get_people(path, family))
    booked(path, '2025-02-20', 'familjeutlägg', -600)
    booked(path, '2025-03-25', 'inkomst', 42000)

    html = client.post(f'/{family}/transfers', data={
        'year': '2025', 'month': '3', 'allowance': '10 000',
        f'income_{sara}': '40000', f'costs_{sara}': '=700+500',
        f'income_{rikard}': '', f'costs_{rikard}': '',
    }, follow_redirects=True).get_data(as_text=True)
    assert 'Saved March 2025' in html
    assert 'value="=700+500"' in html                # what was typed is kept
    assert 'placeholder="42000"' in html             # income from Rikard's account
    assert 'debt from February in Rikard' in html
    assert db.get_allowance_months(path, family, 2025) == {3: 10000}
    # 40 000 − 1 200 − 10 000 and 42 000 − 600 − 10 000
    assert all(f'>{n}<' in html for n in ('28\xa0800', '31\xa0400', '60\xa0200'))

    html = client.post(f'/{family}/transfers', data={
        'year': '2025', 'month': '4', 'allowance': '', f'income_{sara}': 'lots',
        f'costs_{sara}': '', f'income_{rikard}': '1', f'costs_{rikard}': '',
    }, follow_redirects=True).get_data(as_text=True)
    assert 'is not an amount' in html and 'Nothing was saved' in html
    assert [m.month for m in db.get_person_months(path, family, 2025)] == [3]

    # An empty allowance goes back to the default, which can be changed.
    client.post(f'/{family}/transfers', data={'year': '2025', 'month': '3', 'allowance': ''})
    assert db.get_allowance_months(path, family, 2025) == {}
    html = client.post(f'/{family}/transfers/default', data={'default': '11 000'},
                       follow_redirects=True).get_data(as_text=True)
    assert 'The default allowance is now 11\xa0000 kr' in html
    assert transfer_year(path, family, 2025)[sara][2].allowance == 11000

    # People belong to their account.
    assert client.post(f'/{PRIVAT}/transfers/people/{sara}', data={'action': 'delete'}).status_code == 404
    client.post(f'/{family}/transfers/people/{sara}', data={'action': 'delete'})
    assert [p.name for p in db.get_people(path, family)] == ['Rikard']


def test_sensor_and_cli(path, family):
    from datetime import datetime

    from click.testing import CliRunner

    import ha_sensors
    from app import cli

    person = db.add_person(path, family, 'TEST TESTSSON')
    runner = CliRunner()
    # The calculation is in the joint account whichever account is selected.
    result = runner.invoke(cli, ['--db', path, 'transfer', 'set', 'test testsson', '3',
                                 '--year', '2025', '--income', '40000', '--costs', '700+500'])
    assert result.exit_code == 0, result.output
    assert '40000 − 1200 − 12000 = 26800 to Familj' in result.output
    result = runner.invoke(cli, ['--db', path, 'transfer', 'allowance', '10000', '--month', '3',
                                 '--year', '2025'])
    assert result.exit_code == 0, result.output
    assert runner.invoke(cli, ['--db', path, 'transfer', 'allowance', '11000', '--default']).exit_code == 0
    result = runner.invoke(cli, ['--db', path, 'transfer', 'show', '--year', '2025'])
    assert 'March' in result.output and '28800' in result.output

    states = ha_sensors.account_states(path, db.get_account(path, family), now=datetime(2025, 3, 15))
    sensor = states['sensor.economics_familj_transfer_test_testsson']
    assert sensor['state'] == 28800
    assert sensor['attributes']['shared_expenses'] == 1200
    assert sensor['attributes']['allowance'] == 10000
    assert sensor['attributes']['previous_month'] is None
    april = ha_sensors.account_states(path, db.get_account(path, family), now=datetime(2025, 4, 2))
    assert april['sensor.economics_familj_transfer_test_testsson']['state'] == 'unknown'


def as_version_9(path):
    """Turn a new database back into one at schema version 9."""
    with sqlite3.connect(path) as conn:
        conn.executescript("DROP TABLE allowance_months; DELETE FROM people; "
                           "UPDATE accounts SET name = 'Privat' WHERE id = 1; "
                           "PRAGMA user_version = 9;")


def test_migration_renames_and_sets_up_the_household(path, family):
    as_version_9(path)
    db.create_tables(path)
    assert [a.name for a in db.get_accounts(path)] == ['Rikard', 'Familj']
    people = db.get_people(path, family)
    assert [(p.name, p.linked_account_id) for p in people] == [('Rikard', PRIVAT), ('Sara', None)]


def test_migration_keeps_existing_people_and_their_allowance(path, family):
    person = db.add_person(path, family, 'TEST TESTSSON')
    as_version_9(path)
    with sqlite3.connect(path) as conn:
        conn.execute('INSERT INTO people (id, account_id, name) VALUES (?, ?, ?)',
                     (person, family, 'TEST TESTSSON'))
        conn.execute('INSERT INTO person_months (account_id, person_id, year, month, income, '
                     'allowance) VALUES (?, ?, 2025, 2, 40000, 9000)', (family, person))
    db.create_tables(path)
    assert [p.name for p in db.get_people(path, family)] == ['TEST TESTSSON']
    assert db.get_allowance_months(path, family, 2025) == {2: 9000}
    assert transfer_year(path, family, 2025)[person][1].to_account == 31000
