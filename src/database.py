from datetime import datetime
import sqlite3

from typing import List, Tuple

from app_types import IssuerClassification, ReadTransaction, Transaction


def query(database_path, query):
    with sqlite3.connect(database_path) as conn:
        c = conn.cursor()
        c.execute(query)
        results = c.fetchall()
        print(results)
        return results


def create_tables(database_path: str):
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


def update_transaction(database_path: str, transaction_id: int, main_category: str | None = None, sub_category: str | None = None, date: datetime | None  = None):
    with sqlite3.connect(database_path) as conn:
        c = conn.cursor()
        query = 'UPDATE transactions SET '
        params = []

        if main_category is not None:
            query += 'main_category = ?, '
            params.append(main_category)

        if sub_category is not None:
            query += 'sub_category = ?, '
            params.append(sub_category)

        if date is not None:
            query += 'date = ?, '
            params.append(date.strftime('%Y-%m-%d'))

        query = query.rstrip(', ')  # Remove trailing comma and space
        query += ' WHERE id = ?'
        params.append(transaction_id)

        c.execute(query, params)
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


def get_transactions(database_path, start_date: datetime | None = None, end_date: datetime | None = None, main_category: str | None = None, sub_category: str | None = None) -> list[ReadTransaction]:
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
        
        if main_category:
            query += ' AND main_category = ?'
            params.append(main_category)

        if sub_category:
            query += ' AND sub_category = ?'
            params.append(sub_category)

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


def get_unclassified_transactions(database_path: str) -> list[ReadTransaction]:
    with sqlite3.connect(database_path) as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM transactions WHERE main_category IS NULL OR sub_category IS NULL')
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
    

def get_issuer_classification(database_path, issuer) -> IssuerClassification | None:
    with sqlite3.connect(database_path) as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM issuer_classifications WHERE issuer = ?', (issuer,))
        row = c.fetchone()
        if row:
            return IssuerClassification(
                issuer=row[1],
                main_category=row[2],
                sub_category=row[3]
            )
        return None
    

def get_issuer_classification_by_id(database_path, issuer_id: int) -> IssuerClassification | None:
    with sqlite3.connect(database_path) as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM issuer_classifications WHERE id = ?', (issuer_id,))
        row = c.fetchone()
        if row:
            return IssuerClassification(
                issuer=row[1],
                main_category=row[2],
                sub_category=row[3]
            )
        return None


def get_issuer_classifications(database_path: str) -> List[Tuple[str, IssuerClassification]]:
    with sqlite3.connect(database_path) as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM issuer_classifications')
        rows = c.fetchall()
        classifications = []
        for row in rows:
            classifications.append(
                (
                    row[0],
                    IssuerClassification(
                        issuer=row[1],
                        main_category=row[2],
                        sub_category=row[3]
                    )
                )
            )
        return classifications


def remove_issuer_classification(database_path: str, issuer_id: int):
    with sqlite3.connect(database_path) as conn:
        c = conn.cursor()
        c.execute('DELETE FROM issuer_classifications WHERE id = ?', (issuer_id,))
        conn.commit()


def modify_issuer_classification(database_path: str, issuer_id: int, main_category: str, sub_category: str):
    with sqlite3.connect(database_path) as conn:
        c = conn.cursor()
        c.execute('''UPDATE issuer_classifications
                     SET main_category = ?, sub_category = ?
                     WHERE id = ?''',
                  (main_category, sub_category, issuer_id))
        conn.commit()