import pytest

import database as db
from app_types import PersonMonth, Transaction
from transfers import parse_sum, transfer_year
from webapp import create_app

PRIVAT = 1


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


def test_transfer_is_income_minus_costs_minus_allowance(path, family):
    sara = db.add_person(path, family, 'TEST TESTSSON')
    db.set_person_month(path, family, PersonMonth(sara, 2024, 12, allowance=10000))
    db.set_person_month(path, family, PersonMonth(sara, 2025, 3, income=40000, costs=1200))
    db.set_person_month(path, family, PersonMonth(sara, 2025, 5, income=2000, allowance=8000))

    months = transfer_year(path, family, 2025)[sara]
    march, may, june = months[2], months[4], months[5]
    assert (march.allowance, march.to_account) == (10000, 28800)  # carried over from 2024
    assert (may.allowance, may.to_account) == (8000, -6000)       # negative: paid back
    assert june.allowance == 8000 and not june.has_data
    assert not months[0].has_data


def test_linked_account_fills_in_empty_fields(path, family):
    rikard = db.add_person(path, family, 'Rikard', linked_account_id=PRIVAT)
    booked(path, '2025-02-20', 'familjeutlägg', -600)
    booked(path, '2025-03-25', 'inkomst', 42000)
    booked(path, '2025-03-26', 'familjekonto', -30000)
    db.set_person_month(path, family, PersonMonth(rikard, 2025, 1, allowance=10000))

    march = transfer_year(path, family, 2025)[rikard][2]
    assert (march.income, march.costs, march.transferred) == (42000, 600, 30000)
    assert march.has_data and march.to_account == 31400

    # What is typed in wins over the linked account.
    db.set_person_month(path, family, PersonMonth(rikard, 2025, 3, costs=1000, costs_input='=600+400'))
    assert transfer_year(path, family, 2025)[rikard][2].to_account == 31000

    # January uses the outlays of December the year before.
    booked(path, '2024-12-10', 'familjeutlägg', -300)
    booked(path, '2025-01-25', 'inkomst', 41000)
    january = transfer_year(path, family, 2025)[rikard][0]
    assert (january.costs, january.to_account) == (300, 30700)


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
    db.delete_account(path, family)
    assert db.get_person_months(path, family, 2025) == []


def test_transfers_page(client, path, family):
    html = client.get(f'/{family}/transfers').get_data(as_text=True)
    assert 'Add the people who transfer money to Familj' in html

    client.post(f'/{family}/transfers/people', data={'name': 'TEST TESTSSON'})
    client.post(f'/{family}/transfers/people', data={'name': 'Rikard', 'linked_account_id': str(PRIVAT)})
    sara, rikard = (p.id for p in db.get_people(path, family))
    booked(path, '2025-03-25', 'inkomst', 42000)

    html = client.post(f'/{family}/transfers', data={
        'year': '2025', 'month': '3',
        f'income_{sara}': '40000', f'costs_{sara}': '=700+500', f'allowance_{sara}': '10 000',
        f'income_{rikard}': '', f'costs_{rikard}': '', f'allowance_{rikard}': '10000',
    }, follow_redirects=True).get_data(as_text=True)
    assert 'Saved March 2025' in html
    assert 'value="=700+500"' in html                # what was typed is kept
    assert 'placeholder="42000"' in html             # from the linked account
    assert all(f'>{n}<' in html for n in ('28\xa0800', '32\xa0000', '60\xa0800'))

    html = client.post(f'/{family}/transfers', data={
        'year': '2025', 'month': '4', f'income_{sara}': 'lots', f'costs_{sara}': '',
        f'allowance_{sara}': '', f'income_{rikard}': '1', f'costs_{rikard}': '',
        f'allowance_{rikard}': '',
    }, follow_redirects=True).get_data(as_text=True)
    assert 'is not an amount' in html and 'Nothing was saved' in html
    assert [m.month for m in db.get_person_months(path, family, 2025)] == [3, 3]

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
    db.set_person_month(path, family, PersonMonth(person, 2025, 1, allowance=10000))
    runner = CliRunner()
    result = runner.invoke(cli, ['--db', path, '-a', 'Familj', 'transfer', 'set', 'test testsson',
                                 '3', '--year', '2025', '--income', '40000', '--costs', '700+500'])
    assert result.exit_code == 0, result.output
    assert '40000 − 1200 − 10000 = 28800 to Familj' in result.output
    result = runner.invoke(cli, ['--db', path, '-a', 'Familj', 'transfer', 'show', '--year', '2025'])
    assert 'March' in result.output and '28800' in result.output

    states = ha_sensors.account_states(path, db.get_account(path, family), now=datetime(2025, 3, 15))
    sensor = states['sensor.economics_familj_transfer_test_testsson']
    assert sensor['state'] == 28800
    assert sensor['attributes']['one_off_costs'] == 1200
    assert sensor['attributes']['previous_month'] is None
    april = ha_sensors.account_states(path, db.get_account(path, family), now=datetime(2025, 4, 2))
    assert april['sensor.economics_familj_transfer_test_testsson']['state'] == 'unknown'
