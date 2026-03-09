from datetime import datetime
import sqlite3
import os
from typing import List, Tuple

from app_types import IssuerClassification, ReadTransaction, Transaction

def query(database_path: str, query: str) -> List[Tuple]:
    with sqlite3.connect(database_path) as conn:
        c = conn.cursor()
        c.execute(query)
        results = c.fetchall()
        return results


def run_custom_query(database_path: str):
    with open('src/queries/new_schema.sql', "r", encoding="utf-8") as f:
        schema_sql = f.read()
    with sqlite3.connect(database_path) as conn:
        c = conn.cursor()
        c.executescript(schema_sql)
        conn.commit()


def create_tables(database_path: str):
    with open('src/queries/db_schema.sql', "r", encoding="utf-8") as f:
        schema_sql = f.read()
    with sqlite3.connect(database_path) as conn:
        c = conn.cursor()
        c.executescript(schema_sql)
        conn.commit()


def insert_transaction(database_path: str, transaction: Transaction):
    with open('src/queries/insert_transaction.sql', 'r', encoding='utf-8') as f:
        sql = f.read()
    with sqlite3.connect(database_path) as conn:
        c = conn.cursor()
        c.execute(sql,
                  (transaction.date,
                   transaction.issuer,
                   transaction.amount,
                   transaction.origin,
                   transaction.main_category,
                   transaction.sub_category, 
                   transaction.comment))
        conn.commit()


def update_transaction(database_path: str, transaction_id: int, main_category: str | None = None, sub_category: str | None = None, date: datetime | None  = None, comment: str | None = None):
    with sqlite3.connect(database_path) as conn, open('src/queries/update_transaction.sql', 'r', encoding='utf-8') as f:
        c = conn.cursor()
        template = f.read()
        fields = []
        params = []

        if main_category is not None:
            fields.append('main_category = ?')
            params.append(main_category)

        if sub_category is not None:
            fields.append('sub_category = ?')
            params.append(sub_category)

        if date is not None:
            fields.append('date = ?')
            params.append(date.strftime('%Y-%m-%d'))

        if comment is not None:
            fields.append('comment = ?')
            params.append(comment)

        fields_str = ', '.join(fields)
        query = template.replace('{fields}', fields_str)
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


def get_transactions(database_path: str, start_date: datetime | None = None, end_date: datetime | None = None, main_category: list[str] | None = None, sub_category: list[str] | None = None) -> list[ReadTransaction]:
    with sqlite3.connect(database_path) as conn:
        c = conn.cursor()
        query = 'SELECT * FROM transactions'
        params = []

        conditions = []

        if start_date:
            conditions.append('date >= ?')
            params.append(start_date.strftime('%Y-%m-%d'))
        
        if end_date:
            conditions.append('date <= ?')
            params.append(end_date.strftime('%Y-%m-%d'))
        
        if main_category:
            placeholders = ', '.join(['?'] * len(main_category))
            conditions.append(f"main_category IN ({placeholders})")
            params.extend(main_category)

        if sub_category:
            placeholders = ', '.join(['?'] * len(sub_category))
            conditions.append(f"sub_category IN ({placeholders})")
            params.extend(sub_category)

        if len(conditions) > 0:
            query += ' WHERE ' + ' AND '.join(conditions)

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
                    sub_category=row[6],
                    comment=row[7]
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
                    sub_category=row[6],
                    comment=row[7]
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
                sub_category=row[6],
                comment=row[7]
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