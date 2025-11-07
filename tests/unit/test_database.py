import sqlite3
import os
from app_types import IssuerClassification, Transaction
import database

def setup_module(module):
    # Remove the test database if it exists
    if os.path.exists('transactions.db'):
        os.remove('transactions.db')
    database.create_tables()

def teardown_module(module):
    if os.path.exists('transactions.db'):
        os.remove('transactions.db')

def test_create_tables():
    database.create_tables()
    conn = sqlite3.connect('transactions.db')
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in c.fetchall()]
    assert 'transactions' in tables
    assert 'issuer_classifications' in tables
    conn.close()

def test_insert_and_get_transaction():
    t = Transaction(
        date='2025-10-28',
        issuer='TestIssuer',
        amount=123.45,
        origin='TestOrigin',
        main_category='TestMain',
        sub_category='TestSub'
    )
    database.insert_transaction(t)
    transactions = database.get_transactions()
    assert any(tr.issuer == 'TestIssuer' for tr in transactions)
    tr = database.get_transaction(1)
    assert tr is not None
    assert tr.issuer == 'TestIssuer'
    assert tr.amount == 123.45
    assert tr.origin == 'TestOrigin'
    assert tr.main_category == 'TestMain'
    assert tr.sub_category == 'TestSub'

def test_classify_issuer_and_get_issuer_classification():
    ic = IssuerClassification(
        issuer='TestIssuer',
        main_category='MainCat',
        sub_category='SubCat'
    )
    database.classify_issuer(ic)
    main_cat, sub_cat = database.get_issuer_classification('TestIssuer')
    assert main_cat == 'MainCat'
    assert sub_cat == 'SubCat'
    main_cat_none, sub_cat_none = database.get_issuer_classification('UnknownIssuer')
    assert main_cat_none is None
    assert sub_cat_none is None
