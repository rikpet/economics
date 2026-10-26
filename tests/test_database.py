import sqlite3
import os
from app_types import IssuerClassification, Transaction
import database

MOCK_DB_PATH = 'mock.db'

def setup_module(module):
    # Remove the test database if it exists
    if os.path.exists(MOCK_DB_PATH):
        os.remove(MOCK_DB_PATH)
    database.create_tables(MOCK_DB_PATH)

def teardown_module(module):
    if os.path.exists(MOCK_DB_PATH):
        try:
            os.remove(MOCK_DB_PATH)
        except Exception as e:
            print(f"Error removing {MOCK_DB_PATH}: {e}")

def test_create_tables():
    database.create_tables(MOCK_DB_PATH)
    with sqlite3.connect(MOCK_DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in c.fetchall()]
        assert 'transactions' in tables
        assert 'issuer_classifications' in tables

def test_insert_and_get_transaction():
    t = Transaction(
        date='2025-10-28',
        issuer='TestIssuer',
        amount=123.45,
        origin='TestOrigin',
        main_category='TestMain',
        sub_category='TestSub',
        comment='TestComment'
    )

    database.insert_transaction(MOCK_DB_PATH, 1, t)
    transactions = database.get_transactions(MOCK_DB_PATH, 1)
    assert any(tr.issuer == 'TestIssuer' for tr in transactions)
    tr = database.get_transaction(MOCK_DB_PATH, 1, 1)
    assert tr is not None
    assert tr.issuer == 'TestIssuer'
    assert tr.amount == 123.45
    assert tr.origin == 'TestOrigin'
    assert tr.main_category == 'TestMain'
    assert tr.sub_category == 'TestSub'
    assert tr.comment == 'TestComment'

def test_duplicate_verification_number_rejected():
    t1 = Transaction(
        date='2025-11-01', issuer='X', amount=10.0, origin='SEB',
        verification_number='SEB_dup_test'
    )
    t2 = Transaction(
        date='2025-11-02', issuer='Y', amount=20.0, origin='SEB',
        verification_number='SEB_dup_test'
    )
    database.insert_transaction(MOCK_DB_PATH, 1, t1)
    try:
        database.insert_transaction(MOCK_DB_PATH, 1, t2)
    except sqlite3.IntegrityError:
        return
    raise AssertionError('Expected IntegrityError on duplicate verification_number')


def test_null_verification_numbers_allowed():
    t1 = Transaction(date='2025-11-03', issuer='A', amount=1.0, origin='SEB')
    t2 = Transaction(date='2025-11-04', issuer='B', amount=2.0, origin='SEB')
    database.insert_transaction(MOCK_DB_PATH, 1, t1)
    database.insert_transaction(MOCK_DB_PATH, 1, t2)


def test_classify_issuer_and_get_issuer_classification():
    ic = IssuerClassification(
        issuer='TestIssuer',
        main_category='MainCat',
        sub_category='SubCat'
    )
    database.classify_issuer(MOCK_DB_PATH, 1, ic)
    issuer = database.get_issuer_classification(MOCK_DB_PATH, 1, 'TestIssuer')
    assert issuer is not None
    assert issuer.main_category == 'MainCat'
    assert issuer.sub_category == 'SubCat'
    
    issuer_none = database.get_issuer_classification(MOCK_DB_PATH, 1, 'UnknownIssuer')
    assert issuer_none is  None