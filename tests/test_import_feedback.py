import io
import sqlite3

import pytest

import database as db
import operations
from app_types import IssuerClassification, Transaction
from parser import clean_issuer, parse_seb_transactions
from webapp import create_app

SEB_HEADER = 'Bokföringsdatum;Valutadatum;Verifikationsnummer;Text;Belopp;Saldo\n'


@pytest.fixture
def path(tmp_path):
    p = str(tmp_path / 'import.db')
    db.create_tables(p)
    return p


@pytest.fixture
def client(path):
    app = create_app(path)
    app.testing = True
    return app.test_client()


def seb_file(tmp_path, *rows: str) -> str:
    file = tmp_path / 'seb.csv'
    file.write_text(SEB_HEADER + ''.join(r + '\n' for r in rows), encoding='utf-8-sig')
    return str(file)


def post_file(client, account_id, name, content: bytes):
    return client.post(f'/{account_id}/import', data={
        'file': (io.BytesIO(content), name), 'origin': 'auto',
    }, content_type='multipart/form-data', follow_redirects=True).get_data(as_text=True)


@pytest.mark.parametrize('text, issuer', [
    ('TESTBUTIKEN STO/25-12-30', 'TESTBUTIKEN STO'),
    ('TESTBUTIKEN STO /25-12-30 ', 'TESTBUTIKEN STO'),
    ('TESTBUTIKEN AB/2025-12-30', 'TESTBUTIKEN AB'),
    ('PANT        ', 'PANT'),
    ('A/B TESTSSON', 'A/B TESTSSON'),     # a slash alone is part of the name
    ('/25-12-30', '/25-12-30'),           # nothing would be left
])
def test_clean_issuer(text, issuer):
    assert clean_issuer(text) == issuer


def test_purchase_date_is_not_part_of_the_issuer(path, tmp_path):
    file = seb_file(tmp_path,
                    '2025-12-31;2025-12-30;5000000001;TESTBUTIKEN STO/25-12-30;-250.00;1000.00',
                    '2026-01-05;2026-01-04;5000000002;TESTBUTIKEN STO/26-01-04;-99.50;750.00')
    assert [t.issuer for t in parse_seb_transactions(file)] == ['TESTBUTIKEN STO'] * 2

    # A rule typed with a date is saved without it, and matches every purchase.
    db.classify_issuer(path, 1, IssuerClassification('TESTBUTIKEN STO/25-12-30', 'mat', 'butik'))
    assert [r.issuer for _, r in db.get_issuer_classifications(path, 1)] == ['TESTBUTIKEN STO']
    result = operations.import_file(path, 1, file, 'seb')
    assert (result.added, result.classified, result.unclassified) == (2, 2, 0)

    # The file's text still identifies the rows, so importing it again adds nothing.
    again = operations.import_file(path, 1, file, 'seb')
    assert (again.added, again.skipped_duplicates) == (0, 2)
    assert again.period == ('2025-12-30', '2026-01-04')


def test_migration_drops_purchase_dates(path):
    with sqlite3.connect(path) as conn:
        conn.executescript('DROP TABLE allowance_months; DROP TABLE person_months; DROP TABLE people; PRAGMA user_version = 7;')
        for issuer in ('TESTBUTIKEN STO/25-12-30', 'TESTBUTIKEN STO/26-01-04', 'A/B TESTSSON'):
            conn.execute("INSERT INTO transactions (account_id, date, issuer, amount, origin) "
                         "VALUES (1, '2025-12-30', ?, -1, 'SEB')", (issuer,))
        # Two dated rules for one issuer: the newest wins. A rule without a date always wins.
        conn.executemany('INSERT INTO issuer_classifications '
                         '(account_id, issuer, main_category, sub_category) VALUES (1, ?, ?, ?)', [
                             ('TESTBUTIKEN STO/25-12-30', 'mat', 'butik'),
                             ('TESTBUTIKEN STO/26-01-04', 'mat', 'restaurang'),
                             ('TESTBUTIKEN AB', 'hem', 'inredning'),
                             ('TESTBUTIKEN AB/25-11-02', 'mat', 'butik'),
                         ])
    db.create_tables(path)

    assert db.schema_version(path) == len(db.MIGRATIONS)
    assert sorted(t.issuer for t in db.get_transactions(path, 1)) == \
        ['A/B TESTSSON', 'TESTBUTIKEN STO', 'TESTBUTIKEN STO']
    rules = {r.issuer: r.sub_category for _, r in db.get_issuer_classifications(path, 1)}
    assert rules == {'TESTBUTIKEN STO': 'restaurang', 'TESTBUTIKEN AB': 'inredning'}


def test_import_shows_what_was_added(client, path):
    db.classify_issuer(path, 1, IssuerClassification('PANT', 'mat', 'butik'))
    content = (SEB_HEADER + '2025-09-29;2025-09-28;1;PANT;-127.00;0\n'
                            '2025-09-30;2025-09-29;2;TESTBUTIKEN STO/25-09-29;-50.00;0\n').encode()
    html = post_file(client, 1, 'seb.csv', content)
    assert 'seb.csv imported' in html
    assert 'SEB · 2 transactions dated <span class="nowrap">2025-09-28</span>' in html
    assert '<strong>1</strong> classified by issuer rules' in html
    assert 'Classify 1 transaction<' in html
    assert '<td class="c-issuer">TESTBUTIKEN STO</td>' in html
    assert 'Mat › Butik' in html

    html = post_file(client, 1, 'seb.csv', content)
    assert 'Nothing new in seb.csv' in html and 'Already imported, skipped (2)' in html


def test_import_explains_a_wrong_file(client):
    html = post_file(client, 1, 'other.csv', b'Datum;Belopp\n2025-01-01;-1\n')
    assert 'Could not import other.csv as SEB' in html
    assert 'does not look like a SEB export' in html
    assert 'Valutadatum' in html

    html = post_file(client, 1, 'empty.csv', SEB_HEADER.encode())
    assert 'No transactions in empty.csv' in html


def test_classify_several_at_once(client, path):
    family = db.create_account(path, 'Familj', 'family')
    for issuer in ('PANT', 'PANT', 'ICA', 'APOTEK'):
        db.insert_transaction(path, family, Transaction('2025-01-01', issuer, -1.0, 'SEB'))
    pant, pant2, ica, apotek = db.get_transactions(path, family)
    el = next(c.id for c in db.get_categories(path, family) if c.sub_category == 'el')

    html = client.get(f'/{family}/classify').get_data(as_text=True)
    assert html.count('id="classify-form"') == 1 and f'name="category_{ica.id}"' in html

    html = client.post(f'/{family}/classify', data={
        f'category_{pant.id}': str(el), f'remember_{pant.id}': '1',
        f'category_{ica.id}': str(el), f'comment_{ica.id}': 'test',
        f'category_{apotek.id}': '', f'comment_{apotek.id}': '',
    }, follow_redirects=True).get_data(as_text=True)
    assert 'Saved 2 transactions and 1 issuer rule; the rules also classified 1 more' in html
    assert '1 left to classify' in html
    assert db.get_transaction(path, family, pant2.id).sub_category == 'el'
    assert db.get_transaction(path, family, ica.id).comment == 'test'
    assert db.get_transaction(path, family, apotek.id).main_category is None

    html = client.post(f'/{family}/classify', data={f'category_{apotek.id}': ''},
                       follow_redirects=True).get_data(as_text=True)
    assert 'Choose a category for at least one transaction' in html
