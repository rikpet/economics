from datetime import datetime
import sqlite3

from app_types import IssuerClassification, ReadTransaction, Transaction


def create_tables(database_path='transactions.db'):
    with sqlite3.connect(database_path) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT NOT NULL,
                        issuer TEXT NOT NULL,
                        amount REAL NOT NULL,
                        origin TEXT NOT NULL,
                        main_category TEXT,
                        sub_category TEXT
                    )''')
        c.execute('''CREATE TABLE IF NOT EXISTS issuer_classifications (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        issuer TEXT UNIQUE NOT NULL,
                        main_category TEXT NOT NULL,
                        sub_category TEXT NOT NULL
                    )''')
        conn.commit()


def insert_transaction(database_path: str, transaction: Transaction):
    with sqlite3.connect(database_path) as conn:
        c = conn.cursor()
        c.execute('''INSERT INTO transactions (date, issuer, amount, origin, main_category, sub_category)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (transaction.date,
                   transaction.issuer,
                   transaction.amount,
                   transaction.origin,
                   transaction.main_category,
                   transaction.sub_category))
        conn.commit()


def update_transaction(database_path: str, transaction_id: int, main_category: str, sub_category: str):
    with sqlite3.connect(database_path) as conn:
        c = conn.cursor()
        c.execute('''UPDATE transactions
                     SET main_category = ?, sub_category = ?
                     WHERE id = ?''',
                  (main_category, sub_category, transaction_id))
        conn.commit()


def classify_issuer(database_path, classification: IssuerClassification):
    with sqlite3.connect(database_path) as conn:
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO issuer_classifications (issuer, main_category, sub_category)
                     VALUES (?, ?, ?)''',
                  (classification.issuer,
                   classification.main_category,
                   classification.sub_category))
        conn.commit()


def get_transactions(database_path, start_date: datetime | None = None, end_date: datetime | None = None) -> list[ReadTransaction]:
    with sqlite3.connect(database_path) as conn:
        c = conn.cursor()
        query = 'SELECT * FROM transactions'
        params = []
        if start_date:
            query += ' WHERE date >= ?'
            params.append(start_date.strftime('%Y-%m-%d'))
        if end_date:
            query += ' AND date <= ?'
            params.append(end_date.strftime('%Y-%m-%d'))
        c.execute(query, params)
        rows = c.fetchall()
        transactions = []
        for row in rows:
            transactions.append(
                ReadTransaction(
                    id=row[0],
                    date=row[1],
                    issuer=row[2],
                    amount=row[3],
                    origin=row[4],
                    main_category=row[5],
                    sub_category=row[6]
                )
            )
        return transactions


def get_unclassified_transactions() -> list[ReadTransaction]:
    with sqlite3.connect('transactions.db') as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM transactions WHERE main_category IS NULL OR sub_category IS NULL')
        rows = c.fetchall()
        transactions = []
        for row in rows:
            transactions.append(
                ReadTransaction(
                    id=row[0],
                    date=datetime.strptime(row[1], '%Y-%m-%d'),
                    issuer=row[2],
                    amount=row[3],
                    origin=row[4],
                    main_category=row[5],
                    sub_category=row[6]
                )
            )
        return transactions


def get_transaction(database_path, dataid):
    with sqlite3.connect(database_path) as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM transactions WHERE id = ?', (dataid,))
        row = c.fetchone()
        if row:
            return Transaction(
                date=row[1],
                issuer=row[2],
                amount=row[3],
                origin=row[4],
                main_category=row[5],
                sub_category=row[6]
            )
        return None
    

def get_issuer_classification(database_path, issuer) -> tuple:
    with sqlite3.connect(database_path) as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM issuer_classifications WHERE issuer = ?', (issuer,))
        row = c.fetchone()
        if row:
            return row[2], row[3] # main_category, sub_category
        return None, None