import io
import json
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
    assert 'Boende' in html and '>El<' not in html  # sub-categories are hidden by default
    html = client.get(f'/{family}/?year={trans.date[:4]}&subs=1').get_data(as_text=True)
    assert '>El<' in html

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


def test_edit_redirects_back_through_ingress(client, path):
    """Saving must return to the list under the Ingress prefix, not to the HA root."""
    db.insert_transaction(path, 1, Transaction('2025-01-01', 'ICA', -1.0, 'SEB'))
    trans = db.get_transactions(path, 1)[0]
    prefix = '/api/hassio_ingress/abc123'
    headers = {'X-Ingress-Path': prefix}

    listing = client.get('/1/transactions?year=2025&month=1', headers=headers).get_data(as_text=True)
    edit_url = re.search(r'href="([^"]*/transactions/%d[^"]*)"' % trans.id, listing).group(1)
    assert edit_url.startswith(prefix)
    edit_url = edit_url[len(prefix):].replace('&amp;', '&')

    page = client.get(edit_url, headers=headers).get_data(as_text=True)
    assert f'href="{prefix}/1/transactions?year=2025&amp;month=1"' in page  # Cancel

    response = client.post(edit_url, headers=headers, data={'comment': 'x'})
    assert response.status_code == 302
    assert response.headers['Location'] == f'{prefix}/1/transactions?year=2025&month=1'

    response = client.post(edit_url, headers=headers, data={'date': 'nope'})
    assert response.headers['Location'].startswith(f'{prefix}/1/transactions/{trans.id}?')

    # Only the list's own filters are carried over.
    response = client.post(f'/1/transactions/{trans.id}?back=evil%3D1%26year%3D2024',
                           headers=headers, data={'comment': 'y'})
    assert response.headers['Location'] == f'{prefix}/1/transactions?year=2024'


# Home Assistant's security filter (homeassistant/components/http/security_filter.py)
# answers "400: Bad Request" before the add-on is reached when a URL matches this.
HA_SECURITY_FILTER = re.compile(
    r"(?:proc/self/environ|(\.\.//?)+|[a-zA-Z0-9_]=/([a-z0-9_.]//?)+"
    r"|(?m:^(?>[^\n]*?union)(?>[^\n]*?select)(?>[^\n]*?\())"
    r"|(?m:^(?>[^\n]*?concat)(?>[^\n]*?\()))",
    flags=re.IGNORECASE,
)


def test_no_url_is_blocked_by_home_assistant(client, path):
    from html import unescape
    from urllib.parse import unquote

    family = db.create_account(path, 'Familj', 'family')
    for account_id, main, sub in ((1, 'bokföring', 'utlägg/skuld'), (family, 'barn', 'förskola/skola')):
        db.insert_transaction(path, account_id, Transaction('2025-03-01', 'A/B', -10.0, 'SEB', main, sub))
        db.insert_transaction(path, account_id, Transaction('2025-03-02', 'C', -5.0, 'SEB'))

    def unquote_all(value):
        while (once := unquote(value)) != value:
            value = once
        return value

    pages = ['/accounts']
    for account_id in (1, family):
        tx = f'/{account_id}/transactions'
        pages += [f'/{account_id}/', f'/{account_id}/?year=2025&subs=1', f'/{account_id}/charts?year=2025',
                  tx, f'{tx}?year=2025&month=3', f'{tx}?year=2025&category=bokföring&sub=utlägg/skuld',
                  f'{account_id}/classify', f'/{account_id}/issuers', f'/{account_id}/categories']
    pages += [f'/1/transactions/{t.id}?back=year%3D2025' for t in db.get_transactions(path, 1)]

    checked = 0
    for page in pages:
        page = page if page.startswith('/') else '/' + page
        html = client.get(page).get_data(as_text=True)
        for url in re.findall(r'(?:href|action)="([^"]+)"', html):
            url = unescape(url)
            assert not HA_SECURITY_FILTER.search(unquote_all(url)), (page, url)
            checked += 1
    assert checked > 200


def test_hide_categories(client, path):
    db.insert_transaction(path, 1, Transaction('2025-03-01', 'ICA', -100.0, 'SEB', 'mat', 'butik'))
    db.insert_transaction(path, 1, Transaction('2025-03-02', 'SBO', -40.0, 'SEB', 'mat', 'systembolaget'))
    db.insert_transaction(path, 1, Transaction('2025-03-03', 'X', -7.0, 'SEB', 'bokföring', 'internöverföring'))

    def budget():
        return client.get('/1/?year=2025&subs=1').get_data(as_text=True)

    assert '<th scope="row">Bokföring</th>' in budget()
    client.post('/1/categories/group', data={'main': 'bokföring', 'action': 'hide'})
    html = budget()
    assert '<th scope="row">Bokföring</th>' not in html and 'not shown' in html

    sbo = category_id(path, 1, 'mat', 'systembolaget')
    client.post(f'/1/categories/{sbo}', data={'main': 'mat', 'sub': 'systembolaget', 'kind': 'expense'})
    assert db.get_category(path, 1, sbo).hidden
    html = budget()
    assert '<th scope="row">Systembolaget</th>' not in html
    # Mat in March now only counts butik.
    assert re.search(r'category=mat&amp;sub="[^>]*>100<', html)

    client.post('/1/categories/group', data={'main': 'bokföring', 'action': 'show'})
    assert '<th scope="row">Bokföring</th>' in budget()

    client.post('/1/categories/group', data={'main': 'mat', 'name': 'Livsmedel', 'action': 'rename'})
    assert db.get_transactions(path, 1, main_category=['livsmedel'])
    assert 'Livsmedel' in client.get('/1/categories').get_data(as_text=True)


def test_charts_page(client, path):
    db.insert_transaction(path, 1, Transaction('2025-03-01', 'ICA', -100.0, 'SEB', 'mat', 'butik'))
    db.insert_transaction(path, 1, Transaction('2025-03-25', 'LON', 2000.0, 'SEB', 'inkomst', 'övrigt'))
    db.insert_transaction(path, 1, Transaction('2024-03-01', 'ICA', -80.0, 'SEB', 'mat', 'butik'))
    db.insert_transaction(path, 1, Transaction('2025-04-01', 'NEW', -5.0, 'SEB'))

    html = client.get('/1/charts?year=2025').get_data(as_text=True)
    data = json.loads(re.search(r'id="chart-data">(.*?)</script>', html, re.S).group(1))
    assert data['flow']['income'][2] == 2000
    assert data['flow']['expenses'][2] == 100
    assert data['flow']['expenses'][3] == 5  # unclassified counts as an expense
    assert data['selected'] == 'mat'
    assert data['trend']['previous'][2] == 80
    assert data['subs'][0] == {'label': 'Butik', 'key': 'butik', 'value': 100}
    assert [s['key'] for s in data['stack']] == ['mat', 'uncategorized']
    assert 'charts.js?v=' in html
    assert 'vendor/plotly-basic.min.js?v=' in html
    assert client.get('/static/vendor/plotly-basic.min.js').status_code == 200

    html = client.get('/1/charts?year=2025&category=inkomst').get_data(as_text=True)
    data = json.loads(re.search(r'id="chart-data">(.*?)</script>', html, re.S).group(1))
    assert data['selected'] == 'inkomst' and data['trend']['current'][2] == 2000

    assert client.get('/1/charts?year=2030').status_code == 200
    db.set_category_hidden(path, 1, True, main_category='mat')
    html = client.get('/1/charts?year=2025').get_data(as_text=True)
    data = json.loads(re.search(r'id="chart-data">(.*?)</script>', html, re.S).group(1))
    assert 'mat' not in [t['key'] for t in data['totals']]


def test_period_label():
    from webapp import period_label
    assert period_label([1, 2, 3, 7]) == 'Jan–Mar, Jul'
    assert period_label([12]) == 'Dec'
    assert period_label(list(range(1, 13))) == 'Jan–Dec'


def chart_data(client, url):
    html = client.get(url).get_data(as_text=True)
    return json.loads(re.search(r'id="chart-data">(.*?)</script>', html, re.S).group(1)), html


def test_charts_month_filter(client, path):
    for month, amount in ((1, -100.0), (2, -200.0), (7, -5000.0)):
        db.insert_transaction(path, 1, Transaction(f'2025-{month:02d}-05', 'ICA', amount, 'SEB', 'mat', 'butik'))

    data, html = chart_data(client, '/1/charts?year=2025&f=1&m=1&m=2&offered=mat&c=mat')
    assert data['months'] == ['Jan', 'Feb']
    assert data['flow']['expenses'] == [100, 200]
    assert data['totals'][0] == {'key': 'mat', 'label': 'Mat', 'value': 300}
    assert data['trend']['current'] == [100, 200]
    assert 'Jan–Feb' in html

    # No months ticked means the whole year.
    data, _ = chart_data(client, '/1/charts?year=2025&f=1&offered=mat&c=mat')
    assert len(data['months']) == 12 and data['totals'][0]['value'] == 5300


def test_charts_hide_categories(client, path):
    db.insert_transaction(path, 1, Transaction('2025-03-01', 'ICA', -100.0, 'SEB', 'mat', 'butik'))
    db.insert_transaction(path, 1, Transaction('2025-03-02', 'BANK', -900.0, 'SEB', 'lån', 'övrigt'))
    db.insert_transaction(path, 1, Transaction('2025-03-25', 'LON', 2000.0, 'SEB', 'inkomst', 'övrigt'))

    offered = '&'.join(f'offered={m}' for m in ('inkomst', 'mat', 'lån'))
    response = client.get(f'/1/charts?year=2025&f=1&{offered}&c=inkomst&c=mat')
    data = json.loads(re.search(r'id="chart-data">(.*?)</script>', response.get_data(as_text=True), re.S).group(1))
    assert [t['key'] for t in data['totals']] == ['mat']
    assert data['flow']['expenses'][2] == 100
    assert 'economics_charts_1=l%C3%A5n;' in response.headers['Set-Cookie']

    # The choice is remembered for the account, and only affects the charts.
    data, _ = chart_data(client, '/1/charts?year=2025')
    assert [t['key'] for t in data['totals']] == ['mat']
    assert '<th scope="row">Lån</th>' in client.get('/1/?year=2025').get_data(as_text=True)

    # A category the form didn't offer keeps its state.
    data, _ = chart_data(client, '/1/charts?year=2025&f=1&offered=mat&c=mat')
    assert [t['key'] for t in data['totals']] == ['mat']

    data, _ = chart_data(client, f'/1/charts?year=2025&f=1&{offered}&c=inkomst&c=mat&c=l%C3%A5n')
    assert [t['key'] for t in data['totals']] == ['lån', 'mat']
