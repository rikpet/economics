import sqlite3

import pytest

import database as db
from app_types import IssuerClassification, Transaction

LEGACY_SCHEMA = '''
CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    issuer TEXT NOT NULL,
    amount REAL NOT NULL,
    origin TEXT NOT NULL,
    main_category TEXT COLLATE NOCASE,
    sub_category TEXT COLLATE NOCASE,
    comment TEXT
);
CREATE TABLE issuer_classifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issuer TEXT UNIQUE NOT NULL,
    main_category TEXT NOT NULL COLLATE NOCASE,
    sub_category TEXT NOT NULL COLLATE NOCASE
);
CREATE TABLE allowances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    rikard_allowance REAL NOT NULL,
    sara_allowance REAL NOT NULL,
    UNIQUE(year, month)
);
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO transactions (date, issuer, amount, origin, main_category, sub_category)
    VALUES ('2024-01-31', 'CENTRALA STUDIESTÖDSNÄMN', -729, 'SEB', 'Lån', 'CSN');
INSERT INTO transactions (date, issuer, amount, origin, main_category, sub_category)
    VALUES ('2024-01-30', 'ENKLA VARDAG', -50, 'SEB', 'Övrigt', 'Bankkostnader');
INSERT INTO transactions (date, issuer, amount, origin) VALUES ('2024-02-01', 'X', -1, 'SEB');
INSERT INTO issuer_classifications (issuer, main_category, sub_category)
    VALUES ('ENKLA VARDAG', 'Övrigt', 'Bankkostnader');
INSERT INTO allowances (year, month, rikard_allowance, sara_allowance) VALUES (2024, 1, 10, 20);
INSERT INTO settings (key, value) VALUES ('rikard_allowance', '10');
'''


@pytest.fixture
def path(tmp_path):
    p = str(tmp_path / 'test.db')
    db.create_tables(p)
    return p


def test_new_database_has_private_account(path):
    accounts = db.get_accounts(path)
    assert [a.name for a in accounts] == ['Rikard']
    assert accounts[0].derive_allowance is True
    cats = {(c.main_category, c.sub_category) for c in db.get_categories(path, 1)}
    assert ('mat', 'butik') in cats
    assert ('bokföring', 'familjeutlägg') in cats
    assert db.schema_version(path) == len(db.MIGRATIONS)


def test_legacy_database_is_migrated_to_private_account(tmp_path):
    p = str(tmp_path / 'legacy.db')
    conn = sqlite3.connect(p)
    conn.executescript(LEGACY_SCHEMA)
    conn.close()

    db.create_tables(p)
    db.create_tables(p)  # idempotent

    assert [a.name for a in db.get_accounts(p)] == ['Rikard']
    transactions = db.get_transactions(p, 1)
    assert len(transactions) == 3
    assert transactions[0].main_category == 'Övrigt'
    assert db.get_issuer_classification(p, 1, 'ENKLA VARDAG').sub_category == 'Bankkostnader'
    assert db.get_allowances(p, 1, 2024)[0]['sara_allowance'] == 20
    assert db.get_setting(p, 1, 'rikard_allowance') == '10'

    # A sub-category in use but missing from the template is kept, as an expense.
    cats = {(c.main_category, c.sub_category): c.invert_sign for c in db.get_categories(p, 1)}
    assert cats[('lån', 'csn')] is True

    # Filtering works regardless of case, also for non-ASCII letters.
    assert len(db.get_transactions(p, 1, main_category=['övrigt'])) == 1


def test_create_account_from_template(path):
    family = db.create_account(path, 'Familj', 'family')
    cats = {(c.main_category, c.sub_category) for c in db.get_categories(path, family)}
    assert ('barn', 'förskola/skola') in cats
    assert ('bokföring', 'familjeutlägg') not in cats
    assert db.find_account(path, 'familj').id == family
    assert db.find_account(path, str(family)).name == 'Familj'
    assert db.find_account(path, '').name == 'Rikard'
    assert db.find_account(path, 'nope') is None

    with pytest.raises(ValueError, match='already exists'):
        db.create_account(path, 'familj', 'family')
    with pytest.raises(ValueError, match='Unknown template'):
        db.create_account(path, 'Other', 'nope')


def test_accounts_are_isolated(path):
    family = db.create_account(path, 'Familj', 'family')
    t = Transaction(date='2025-01-01', issuer='ICA', amount=-100.0, origin='SEB',
                    verification_number='SEB_same')
    db.insert_transaction(path, 1, t)
    # The same bank row may exist in both accounts...
    db.insert_transaction(path, family, t)
    # ...but only once per account.
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_transaction(path, family, t)

    db.classify_issuer(path, family, IssuerClassification('ICA', 'mat', 'butik'))
    assert db.get_issuer_classification(path, family, 'ICA') is not None
    assert db.get_issuer_classification(path, 1, 'ICA') is None

    private_id = db.get_transactions(path, 1)[0].id
    assert db.get_transaction(path, family, private_id) is None
    db.update_transaction(path, family, private_id, 'mat', 'butik')
    assert db.get_transaction(path, 1, private_id).main_category is None


def test_rename_category_updates_transactions_and_rules(path):
    db.insert_transaction(path, 1, Transaction('2025-01-01', 'ICA', -1.0, 'SEB', 'Mat', 'Butik'))
    db.classify_issuer(path, 1, IssuerClassification('ICA', 'mat', 'butik'))
    cat = next(c for c in db.get_categories(path, 1) if c.sub_category == 'butik')

    db.update_category(path, 1, cat.id, 'mat', 'Matbutik', True)

    assert db.get_transactions(path, 1)[0].sub_category == 'matbutik'
    assert db.get_issuer_classification(path, 1, 'ICA').sub_category == 'matbutik'
    assert db.category_usage(path, 1, 'mat', 'matbutik') == 1

    with pytest.raises(ValueError, match='already exists'):
        db.update_category(path, 1, cat.id, 'mat', 'fika', True)


def test_add_category_is_grouped_with_its_main_category(path):
    db.add_category(path, 1, 'Mat', 'Hämtmat')
    cats = [(c.main_category, c.sub_category) for c in db.get_categories(path, 1)]
    mains = [m for m, _ in cats]
    # All 'mat' entries are contiguous.
    first, last = mains.index('mat'), len(mains) - 1 - mains[::-1].index('mat')
    assert set(mains[first:last + 1]) == {'mat'}
    assert ('mat', 'hämtmat') in cats


def test_delete_account(path):
    family = db.create_account(path, 'Familj', 'family')
    db.insert_transaction(path, family, Transaction('2025-01-01', 'ICA', -1.0, 'SEB'))
    with pytest.raises(ValueError, match='cannot be deleted'):
        db.delete_account(path, family)

    empty = db.create_account(path, 'Tom')
    db.delete_account(path, empty)
    assert db.get_account(path, empty) is None


def test_backup_and_restore(path, tmp_path):
    db.insert_transaction(path, 1, Transaction('2025-01-01', 'ICA', -1.0, 'SEB'))
    backup = str(tmp_path / 'backup.db')
    db.backup_database(path, backup)

    db.insert_transaction(path, 1, Transaction('2025-01-02', 'COOP', -2.0, 'SEB'))
    db.restore_database(backup, path)
    assert [t.issuer for t in db.get_transactions(path, 1)] == ['ICA']

    junk = tmp_path / 'junk.db'
    junk.write_text('not a database')
    with pytest.raises(ValueError):
        db.restore_database(str(junk), path)
