import json
from datetime import datetime

import pytest

import database as db
import ha_sensors
from app_types import Transaction
from ha_sensors import SensorPublisher, account_states, all_states, slugify


@pytest.fixture
def path(tmp_path):
    p = str(tmp_path / 'ha.db')
    db.create_tables(p)
    return p


def test_slugify():
    assert slugify('Familj') == 'familj'
    assert slugify('Hushåll') == 'hushall'
    assert slugify('Övrigt & Nöje') == 'ovrigt_noje'


def test_account_states(path):
    db.insert_transaction(path, 1, Transaction('2025-03-02', 'ICA', -250.0, 'SEB', 'mat', 'butik'))
    db.insert_transaction(path, 1, Transaction('2025-02-02', 'ICA', -100.0, 'SEB', 'mat', 'butik'))
    db.insert_transaction(path, 1, Transaction('2025-03-03', 'NEW', -1.0, 'SEB'))

    states = account_states(path, db.get_account(path, 1), now=datetime(2025, 3, 15))

    mat = states['sensor.economics_privat_mat']
    assert mat['state'] == 250
    assert mat['attributes']['previous_month'] == 100
    assert mat['attributes']['year_to_date'] == 350
    assert mat['attributes']['sub_categories']['butik'] == 250
    assert mat['attributes']['unit_of_measurement'] == 'SEK'
    assert 'sensor.economics_privat_hushall' in states
    assert states['sensor.economics_privat_unclassified']['state'] == 1
    assert states['sensor.economics_privat_latest_transaction']['state'] == '2025-03-03'


def test_january_compares_with_previous_december(path):
    db.insert_transaction(path, 1, Transaction('2024-12-02', 'ICA', -70.0, 'SEB', 'mat', 'butik'))
    states = account_states(path, db.get_account(path, 1), now=datetime(2025, 1, 10))
    assert states['sensor.economics_privat_mat']['attributes']['previous_month'] == 70


def test_all_states_covers_every_account(path):
    db.create_account(path, 'Familj', 'family')
    states = all_states(path, currency='EUR')
    assert 'sensor.economics_familj_boende' in states
    assert 'sensor.economics_privat_mat' in states
    assert states['sensor.economics_familj_boende']['attributes']['unit_of_measurement'] == 'EUR'


def test_publish_posts_to_supervisor(path, monkeypatch):
    sent = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{}'

    def fake_urlopen(request, timeout):
        sent.append((request.full_url, request.headers['Authorization'], json.loads(request.data)))
        return Response()

    monkeypatch.setattr(ha_sensors.urllib.request, 'urlopen', fake_urlopen)
    SensorPublisher(path, 'secret').publish()

    urls = [url for url, _, _ in sent]
    assert 'http://supervisor/core/api/states/sensor.economics_privat_mat' in urls
    assert all(auth == 'Bearer secret' for _, auth, _ in sent)
    assert all('state' in body and 'attributes' in body for _, _, body in sent)
