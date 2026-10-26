import io
import re
import sqlite3

import pytest

import database as db
from app_types import Transaction
from webapp import create_app, format_money

SEB_FILE = 'tests/input_data/seb_transactions.csv'


@pytest.fixture
def path(tmp_path):
    return str(tmp_path / 'web.db')


@pytest.fixture
def changes():
    return []


@pytest.fixture
def client(path, changes):
    app = create_app(path, on_change=lambda: changes.append(1))
    app.testing = True
    return app.test_client()


def upload(client, account_id, file_path, origin='auto'):
    with open(file_path, 'rb') as f:
        return client.post(f'/{account_id}/import', data={
            'file': (io.BytesIO(f.read()), file_path.rsplit('/', 1)[-1]),
            'origin': origin,
        }, content_type='multipart/form-data', follow_redirects=True)


def category_id(path, account_id, main, sub):
    return next(c.id for c in db.get_categories(path, account_id)
                if c.main_category == main and c.sub_category == sub)


def test_format_money():
    assert format_money(1234567.4) == '1 234 567'
    assert format_money(-5) == '−5'


def test_index_redirects_to_first_account(client):
    response = client.get('/')
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/1/')


def test_pages_render(client):
    for url in ('/1/', '/1/?subs=0&year=2024', '/1/transactions', '/1/classify', '/1/import',
                '/1/issuers', '/1/categories', '/accounts'):
        response = client.get(url)
        assert response.status_code == 200, url
    assert client.get('/99/').status_code == 404


def test_links_use_ingress_prefix(client):
    prefix = '/api/hassio_ingress/abc123'
    html = client.get('/1/', headers={'X-Ingress-Path': prefix}).get_data(as_text=True)
    links = re.findall(r'(?:href|action)="([^"#]+)"', html)
    assert links
    assert all(link.startswith(prefix) for link in links), links


def test_import_classify_and_budget(client, path, changes):
    family = db.create_account(path, 'Familj', 'family')

    html = upload(client, family, SEB_FILE).get_data(as_text=True)
    assert 'added 8 transactions' in html
    assert len(db.get_transactions(path, family)) == 8
    assert db.get_transactions(path, 1) == []
    assert changes

    # Importing the same file again only adds duplicates.
    html = upload(client, family, SEB_FILE).get_data(as_text=True)
    assert 'added 0 transactions' in html and 'skipped 8 duplicates' in html

    pant = next(t for t in db.get_transactions(path, family) if t.issuer == 'PANT')
    el = category_id(path, family, 'boende', 'el')
    client.post(f'/{family}/classify/{pant.id}',
                data={'category': str(el), 'comment': 'test', 'remember': '1'})
    trans = db.get_transaction(path, family, pant.id)
    assert (trans.main_category, trans.sub_category, trans.comment) == ('boende', 'el', 'test')
    assert db.get_issuer_classification(path, family, 'PANT').sub_category == 'el'

    html = client.get(f'/{family}/?year={trans.date[:4]}').get_data(as_text=True)
    assert 'Boende' in html and 'El' in html

    html = client.get(f'/{family}/transactions?year={trans.date[:4]}&category=boende&sub=el').get_data(as_text=True)
    assert 'PANT' in html


def test_classify_rejects_category_from_other_account(client, path):
    family = db.create_account(path, 'Familj', 'family')
    db.insert_transaction(path, family, Transaction('2025-01-01', 'ICA', -1.0, 'SEB'))
    trans = db.get_transactions(path, family)[0]
    private_category = category_id(path, 1, 'mat', 'butik')

    client.post(f'/{family}/classify/{trans.id}', data={'category': str(private_category)})
    assert db.get_transaction(path, family, trans.id).main_category is None


def test_edit_transaction(client, path):
    db.insert_transaction(path, 1, Transaction('2025-01-01', 'ICA', -1.0, 'SEB'))
    trans = db.get_transactions(path, 1)[0]
    fika = category_id(path, 1, 'mat', 'fika')
    client.post(f'/1/transactions/{trans.id}',
                data={'category': str(fika), 'date': '2025-01-05', 'comment': 'kaffe'})
    trans = db.get_transaction(path, 1, trans.id)
    assert (trans.sub_category, trans.date, trans.comment) == ('fika', '2025-01-05', 'kaffe')
    assert 'sub_category: None -> fika' in trans.modification_log


def test_category_and_account_management(client, path):
    client.post('/accounts', data={'name': 'Familj', 'template': 'family'})
    family = db.find_account(path, 'Familj')
    assert family is not None and family.derive_allowance is False

    client.post(f'/{family.id}/categories', data={'main': 'Husdjur', 'sub': 'Foder', 'kind': 'expense'})
    assert any(c.main_category == 'husdjur' for c in db.get_categories(path, family.id))

    client.post(f'/accounts/{family.id}', data={'name': 'Familjen', 'derive_allowance': '1'})
    family = db.get_account(path, family.id)
    assert family.name == 'Familjen' and family.derive_allowance

    client.post(f'/accounts/{family.id}', data={'action': 'delete'})
    assert db.get_account(path, family.id) is None


def test_backup_and_restore_legacy_database(client, path, tmp_path):
    response = client.get('/backup')
    assert response.status_code == 200
    assert response.data.startswith(b'SQLite format 3')

    legacy = tmp_path / 'legacy.db'
    conn = sqlite3.connect(legacy)
    conn.executescript('''
        CREATE TABLE transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL,
            issuer TEXT NOT NULL, amount REAL NOT NULL, origin TEXT NOT NULL,
            main_category TEXT, sub_category TEXT, comment TEXT);
        INSERT INTO transactions (date, issuer, amount, origin) VALUES ('2025-01-01', 'OLD', -5, 'SEB');
    ''')
    conn.close()

    # Without confirmation nothing happens.
    client.post('/restore', data={'file': (io.BytesIO(legacy.read_bytes()), 'legacy.db')},
                content_type='multipart/form-data')
    assert db.get_transactions(path, 1) == []

    client.post('/restore', data={'file': (io.BytesIO(legacy.read_bytes()), 'legacy.db'),
                                  'confirm': '1'}, content_type='multipart/form-data')
    assert [t.issuer for t in db.get_transactions(path, 1)] == ['OLD']
    assert db.get_accounts(path)[0].name == 'Privat'


def test_cookies_are_scoped_to_the_ingress_path(client):
    """Under Ingress all add-ons share Home Assistant's origin; cookies must not leak to '/'."""
    prefix = '/api/hassio_ingress/abc123'
    response = client.get('/1/', headers={'X-Ingress-Path': prefix})
    cookie = response.headers['Set-Cookie']
    assert cookie.startswith('economics_account=1')
    assert f'Path={prefix}/' in cookie

    response = client.post('/1/classify/apply-rules', headers={'X-Ingress-Path': prefix})
    session_cookie = next(c for c in response.headers.getlist('Set-Cookie')
                          if c.startswith('economics_session='))
    assert f'Path={prefix}/' in session_cookie


def test_static_assets_are_versioned(client):
    from version import __version__
    html = client.get('/1/').get_data(as_text=True)
    assert f'style.css?v={__version__}' in html
