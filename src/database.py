from contextlib import contextmanager
from datetime import datetime
import os
import sqlite3
from typing import Iterator, List, Tuple

from app_types import Account, Category, IssuerClassification, ReadTransaction, SplitPart, Transaction
from category_templates import PRIVATE, TEMPLATES

DEFAULT_ACCOUNT_NAME = 'Privat'

TRANSACTION_COLUMNS = (
    'id, date, issuer, amount, origin, main_category, sub_category, comment, '
    'verification_number, modification_log, parent_id, is_split'
)

# A split transaction's original stays in the table, so a re-import of the bank file still
# sees its verification number, but only its parts count anywhere.
COUNTED = 'is_split = 0'



def _lower(value: str | None) -> str | None:
    return value.lower() if value is not None else None


@contextmanager
def _connect(database_path: str) -> Iterator[sqlite3.Connection]:
    """Open a connection that commits on success, rolls back on error and always closes."""
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    # SQLite's NOCASE only folds ASCII, so 'Övrigt' != 'övrigt'. Use Python's lower() instead.
    conn.create_function('py_lower', 1, _lower, deterministic=True)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query(database_path: str, query: str) -> List[Tuple]:
    with _connect(database_path) as conn:
        return [tuple(row) for row in conn.execute(query).fetchall()]


# --------------------------------------------------------------------------------------
# Schema migrations. PRAGMA user_version holds the number of applied migrations.
# --------------------------------------------------------------------------------------

def _migration_1_initial(c: sqlite3.Cursor):
    """The single-account schema, as used before accounts were introduced."""
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        issuer TEXT NOT NULL,
        amount REAL NOT NULL,
        origin TEXT NOT NULL,
        main_category TEXT COLLATE NOCASE,
        sub_category TEXT COLLATE NOCASE,
        comment TEXT,
        verification_number TEXT,
        modification_log TEXT
    )''')
    for column in ('verification_number', 'modification_log'):
        try:
            c.execute(f'ALTER TABLE transactions ADD COLUMN {column} TEXT')
        except sqlite3.OperationalError:
            pass
    c.execute('''CREATE TABLE IF NOT EXISTS issuer_classifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        issuer TEXT UNIQUE NOT NULL,
        main_category TEXT NOT NULL COLLATE NOCASE,
        sub_category TEXT NOT NULL COLLATE NOCASE
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS allowances (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        year INTEGER NOT NULL,
        month INTEGER NOT NULL,
        rikard_allowance REAL NOT NULL,
        sara_allowance REAL NOT NULL,
        UNIQUE(year, month)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )''')


def _migration_2_accounts(c: sqlite3.Cursor):
    """Introduce accounts. All existing data is moved to the default account."""
    c.execute('''CREATE TABLE accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL COLLATE NOCASE,
        derive_allowance INTEGER NOT NULL DEFAULT 0
    )''')
    c.execute('INSERT INTO accounts (id, name, derive_allowance) VALUES (1, ?, 1)',
              (DEFAULT_ACCOUNT_NAME,))

    c.execute('DROP INDEX IF EXISTS idx_transactions_verification_number')
    c.execute('''CREATE TABLE transactions_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL REFERENCES accounts(id),
        date TEXT NOT NULL,
        issuer TEXT NOT NULL,
        amount REAL NOT NULL,
        origin TEXT NOT NULL,
        main_category TEXT COLLATE NOCASE,
        sub_category TEXT COLLATE NOCASE,
        comment TEXT,
        verification_number TEXT,
        modification_log TEXT
    )''')
    columns = ('id, date, issuer, amount, origin, main_category, sub_category, comment, '
               'verification_number, modification_log')  # the columns as of this migration
    c.execute(f'INSERT INTO transactions_new (account_id, {columns}) '
              f'SELECT 1, {columns} FROM transactions')
    c.execute('DROP TABLE transactions')
    c.execute('ALTER TABLE transactions_new RENAME TO transactions')
    c.execute('CREATE UNIQUE INDEX idx_transactions_verification_number '
              'ON transactions(account_id, verification_number) '
              'WHERE verification_number IS NOT NULL')
    c.execute('CREATE INDEX idx_transactions_account_date ON transactions(account_id, date)')

    c.execute('''CREATE TABLE issuer_classifications_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL REFERENCES accounts(id),
        issuer TEXT NOT NULL,
        main_category TEXT NOT NULL COLLATE NOCASE,
        sub_category TEXT NOT NULL COLLATE NOCASE,
        UNIQUE(account_id, issuer)
    )''')
    c.execute('INSERT INTO issuer_classifications_new '
              '(id, account_id, issuer, main_category, sub_category) '
              'SELECT id, 1, issuer, main_category, sub_category FROM issuer_classifications')
    c.execute('DROP TABLE issuer_classifications')
    c.execute('ALTER TABLE issuer_classifications_new RENAME TO issuer_classifications')

    c.execute('''CREATE TABLE allowances_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL REFERENCES accounts(id),
        year INTEGER NOT NULL,
        month INTEGER NOT NULL,
        rikard_allowance REAL NOT NULL DEFAULT 0,
        sara_allowance REAL NOT NULL DEFAULT 0,
        UNIQUE(account_id, year, month)
    )''')
    c.execute('INSERT INTO allowances_new '
              '(id, account_id, year, month, rikard_allowance, sara_allowance) '
              'SELECT id, 1, year, month, rikard_allowance, sara_allowance FROM allowances')
    c.execute('DROP TABLE allowances')
    c.execute('ALTER TABLE allowances_new RENAME TO allowances')

    c.execute('''CREATE TABLE settings_new (
        account_id INTEGER NOT NULL REFERENCES accounts(id),
        key TEXT NOT NULL,
        value TEXT NOT NULL,
        PRIMARY KEY(account_id, key)
    )''')
    c.execute('INSERT INTO settings_new (account_id, key, value) '
              'SELECT 1, key, value FROM settings')
    c.execute('DROP TABLE settings')
    c.execute('ALTER TABLE settings_new RENAME TO settings')

    c.execute('''CREATE TABLE categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL REFERENCES accounts(id),
        main_category TEXT NOT NULL,
        sub_category TEXT NOT NULL,
        invert_sign INTEGER NOT NULL DEFAULT 1,
        position INTEGER NOT NULL DEFAULT 0,
        UNIQUE(account_id, main_category, sub_category)
    )''')
    _seed_categories(c, 1, PRIVATE)

    # Keep sub-categories already in use (e.g. 'lån/csn') so existing data still adds up,
    # as long as their main category is part of the tree.
    template = {(m, s): invert for m, s, invert in PRIVATE}
    main_invert = {m: invert for m, _, invert in PRIVATE}
    in_use = c.execute('''
        SELECT DISTINCT py_lower(main_category), py_lower(sub_category) FROM transactions
        WHERE main_category IS NOT NULL AND sub_category IS NOT NULL
        UNION
        SELECT DISTINCT py_lower(main_category), py_lower(sub_category) FROM issuer_classifications
    ''').fetchall()
    extra = sorted(
        (main, sub, main_invert[main]) for main, sub in in_use
        if main in main_invert and (main, sub) not in template
    )
    _seed_categories(c, 1, extra, start_position=len(PRIVATE))


def _migration_3_hidden_categories(c: sqlite3.Cursor):
    """Categories can be hidden from the budget, charts and sensors."""
    c.execute('ALTER TABLE categories ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0')


def _migration_4_split_transactions(c: sqlite3.Cursor):
    """A transaction can be split into parts that replace it in every sum."""
    c.execute('ALTER TABLE transactions ADD COLUMN parent_id INTEGER REFERENCES transactions(id)')
    c.execute('ALTER TABLE transactions ADD COLUMN is_split INTEGER NOT NULL DEFAULT 0')
    c.execute('CREATE INDEX idx_transactions_parent ON transactions(parent_id)')


# Append-only: users have live databases at every version.
MIGRATIONS = [_migration_1_initial, _migration_2_accounts, _migration_3_hidden_categories,
              _migration_4_split_transactions]


def _seed_categories(c: sqlite3.Cursor, account_id: int, template, start_position: int = 0):
    for position, (main, sub, invert) in enumerate(template, start=start_position):
        c.execute('INSERT OR IGNORE INTO categories '
                  '(account_id, main_category, sub_category, invert_sign, position) '
                  'VALUES (?, ?, ?, ?, ?)',
                  (account_id, main.lower(), sub.lower(), int(invert), position))


def create_tables(database_path: str):
    """Create the database or bring an existing one up to the latest schema. Idempotent."""
    directory = os.path.dirname(os.path.abspath(database_path))
    os.makedirs(directory, exist_ok=True)

    conn = sqlite3.connect(database_path, isolation_level=None)
    conn.create_function('py_lower', 1, _lower, deterministic=True)
    try:
        conn.execute('PRAGMA foreign_keys = OFF')  # tables are rebuilt during migrations
        version = conn.execute('PRAGMA user_version').fetchone()[0]
        for number, migration in enumerate(MIGRATIONS[version:], start=version + 1):
            c = conn.cursor()
            c.execute('BEGIN')
            try:
                migration(c)
                c.execute(f'PRAGMA user_version = {number}')
                c.execute('COMMIT')
            except Exception:
                c.execute('ROLLBACK')
                raise
    finally:
        conn.close()


def schema_version(database_path: str) -> int:
    with _connect(database_path) as conn:
        return conn.execute('PRAGMA user_version').fetchone()[0]


def backup_database(database_path: str, destination_path: str):
    """Write a consistent copy of the database, safe while it is in use."""
    with _connect(database_path) as src:
        dest = sqlite3.connect(destination_path)
        try:
            src.backup(dest)
        finally:
            dest.close()


def restore_database(source_path: str, database_path: str):
    """Replace the database with the one at source_path and migrate it to the latest schema."""
    try:
        with _connect(source_path) as src:
            tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    except sqlite3.DatabaseError as e:
        raise ValueError(f'Not a valid SQLite database: {e}') from e
    if 'transactions' not in tables:
        raise ValueError('The file is not an economics database (no transactions table).')

    create_tables(source_path)
    backup_database(source_path, database_path)


# --------------------------------------------------------------------------------------
# Accounts
# --------------------------------------------------------------------------------------

def _account(row: sqlite3.Row) -> Account:
    return Account(id=row['id'], name=row['name'], derive_allowance=bool(row['derive_allowance']))


def get_accounts(database_path: str) -> list[Account]:
    with _connect(database_path) as conn:
        rows = conn.execute('SELECT * FROM accounts ORDER BY id').fetchall()
        return [_account(r) for r in rows]


def get_account(database_path: str, account_id: int) -> Account | None:
    with _connect(database_path) as conn:
        row = conn.execute('SELECT * FROM accounts WHERE id = ?', (account_id,)).fetchone()
        return _account(row) if row else None


def find_account(database_path: str, name_or_id: str | int | None) -> Account | None:
    """Look up an account by id or (case-insensitive) name. Empty/None gives the first one."""
    accounts = get_accounts(database_path)
    if name_or_id is None or str(name_or_id).strip() == '':
        return accounts[0] if accounts else None
    key = str(name_or_id).strip()
    for account in accounts:
        if str(account.id) == key or account.name.lower() == key.lower():
            return account
    return None


def create_account(database_path: str, name: str, template: str = 'empty',
                   derive_allowance: bool = False) -> int:
    name = name.strip()
    if not name:
        raise ValueError('Account name must not be empty.')
    if template not in TEMPLATES:
        raise ValueError(f'Unknown template: {template}. Choose one of {", ".join(TEMPLATES)}.')
    with _connect(database_path) as conn:
        try:
            c = conn.execute('INSERT INTO accounts (name, derive_allowance) VALUES (?, ?)',
                             (name, int(derive_allowance)))
        except sqlite3.IntegrityError as e:
            raise ValueError(f'An account named {name!r} already exists.') from e
        account_id = c.lastrowid
        _seed_categories(conn.cursor(), account_id, TEMPLATES[template])
        return account_id


def update_account(database_path: str, account_id: int, name: str | None = None,
                   derive_allowance: bool | None = None):
    with _connect(database_path) as conn:
        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError('Account name must not be empty.')
            try:
                conn.execute('UPDATE accounts SET name = ? WHERE id = ?', (name, account_id))
            except sqlite3.IntegrityError as e:
                raise ValueError(f'An account named {name!r} already exists.') from e
        if derive_allowance is not None:
            conn.execute('UPDATE accounts SET derive_allowance = ? WHERE id = ?',
                         (int(derive_allowance), account_id))


def delete_account(database_path: str, account_id: int):
    """Delete an account and its categories, rules and settings. Refuses if it has transactions."""
    with _connect(database_path) as conn:
        count = conn.execute('SELECT COUNT(*) FROM transactions WHERE account_id = ?',
                             (account_id,)).fetchone()[0]
        if count:
            raise ValueError(f'The account has {count} transactions and cannot be deleted.')
        if conn.execute('SELECT COUNT(*) FROM accounts').fetchone()[0] <= 1:
            raise ValueError('The last account cannot be deleted.')
        for table in ('categories', 'issuer_classifications', 'allowances', 'settings'):
            conn.execute(f'DELETE FROM {table} WHERE account_id = ?', (account_id,))
        conn.execute('DELETE FROM accounts WHERE id = ?', (account_id,))


# --------------------------------------------------------------------------------------
# Categories
# --------------------------------------------------------------------------------------

def _category(row: sqlite3.Row) -> Category:
    return Category(id=row['id'], main_category=row['main_category'],
                    sub_category=row['sub_category'], invert_sign=bool(row['invert_sign']),
                    hidden=bool(row['hidden']))


def get_categories(database_path: str, account_id: int) -> list[Category]:
    with _connect(database_path) as conn:
        rows = conn.execute('SELECT * FROM categories WHERE account_id = ? '
                            'ORDER BY position, id', (account_id,)).fetchall()
        return [_category(r) for r in rows]


def get_category(database_path: str, account_id: int, category_id: int) -> Category | None:
    with _connect(database_path) as conn:
        row = conn.execute('SELECT * FROM categories WHERE account_id = ? AND id = ?',
                           (account_id, category_id)).fetchone()
        return _category(row) if row else None


def add_category(database_path: str, account_id: int, main_category: str, sub_category: str,
                 invert_sign: bool = True) -> int:
    main_category = main_category.strip().lower()
    sub_category = sub_category.strip().lower()
    if not main_category or not sub_category:
        raise ValueError('Main and sub category must not be empty.')
    with _connect(database_path) as conn:
        # Keep sub-categories grouped with their main category.
        row = conn.execute('SELECT MAX(position) FROM categories '
                           'WHERE account_id = ? AND main_category = ?',
                           (account_id, main_category)).fetchone()
        if row[0] is None:
            row = conn.execute('SELECT MAX(position) FROM categories WHERE account_id = ?',
                               (account_id,)).fetchone()
        position = (row[0] if row[0] is not None else -1) + 1
        conn.execute('UPDATE categories SET position = position + 1 '
                     'WHERE account_id = ? AND position >= ?', (account_id, position))
        try:
            c = conn.execute('INSERT INTO categories '
                             '(account_id, main_category, sub_category, invert_sign, position) '
                             'VALUES (?, ?, ?, ?, ?)',
                             (account_id, main_category, sub_category, int(invert_sign), position))
        except sqlite3.IntegrityError as e:
            raise ValueError(f'Category {main_category}/{sub_category} already exists.') from e
        return c.lastrowid


def update_category(database_path: str, account_id: int, category_id: int, main_category: str,
                    sub_category: str, invert_sign: bool, hidden: bool | None = None):
    """Rename and/or change a category. Transactions and issuer rules follow a rename."""
    main_category = main_category.strip().lower()
    sub_category = sub_category.strip().lower()
    if not main_category or not sub_category:
        raise ValueError('Main and sub category must not be empty.')
    with _connect(database_path) as conn:
        old = conn.execute('SELECT * FROM categories WHERE account_id = ? AND id = ?',
                           (account_id, category_id)).fetchone()
        if old is None:
            raise ValueError('Category not found.')
        try:
            conn.execute('UPDATE categories SET main_category = ?, sub_category = ?, '
                         'invert_sign = ? WHERE id = ?',
                         (main_category, sub_category, int(invert_sign), category_id))
            if hidden is not None:
                conn.execute('UPDATE categories SET hidden = ? WHERE id = ?',
                             (int(hidden), category_id))
        except sqlite3.IntegrityError as e:
            raise ValueError(f'Category {main_category}/{sub_category} already exists.') from e
        for table in ('transactions', 'issuer_classifications'):
            conn.execute(f'UPDATE {table} SET main_category = ?, sub_category = ? '
                         'WHERE account_id = ? AND py_lower(main_category) = ? '
                         'AND py_lower(sub_category) = ?',
                         (main_category, sub_category, account_id,
                          old['main_category'], old['sub_category']))


def set_category_hidden(database_path: str, account_id: int, hidden: bool,
                        category_id: int | None = None, main_category: str | None = None):
    """Hide or show one category, or every sub-category of a main category."""
    with _connect(database_path) as conn:
        if category_id is not None:
            conn.execute('UPDATE categories SET hidden = ? WHERE account_id = ? AND id = ?',
                         (int(hidden), account_id, category_id))
        elif main_category is not None:
            conn.execute('UPDATE categories SET hidden = ? WHERE account_id = ? '
                         'AND main_category = ?',
                         (int(hidden), account_id, main_category.strip().lower()))


def rename_main_category(database_path: str, account_id: int, old: str, new: str):
    """Rename a main category with all its sub-categories, transactions and issuer rules."""
    old = old.strip().lower()
    new = new.strip().lower()
    if not new:
        raise ValueError('Main category must not be empty.')
    if new == old:
        return
    with _connect(database_path) as conn:
        clash = conn.execute('SELECT a.sub_category FROM categories a JOIN categories b '
                             'ON a.sub_category = b.sub_category AND b.account_id = a.account_id '
                             'WHERE a.account_id = ? AND a.main_category = ? '
                             'AND b.main_category = ?', (account_id, old, new)).fetchone()
        if clash:
            raise ValueError(f'{new}/{clash[0]} already exists.')
        conn.execute('UPDATE categories SET main_category = ? '
                     'WHERE account_id = ? AND main_category = ?', (new, account_id, old))
        for table in ('transactions', 'issuer_classifications'):
            conn.execute(f'UPDATE {table} SET main_category = ? '
                         'WHERE account_id = ? AND py_lower(main_category) = ?',
                         (new, account_id, old))


def category_usage(database_path: str, account_id: int, main_category: str,
                   sub_category: str) -> int:
    with _connect(database_path) as conn:
        return conn.execute('SELECT COUNT(*) FROM transactions WHERE account_id = ? '
                            f'AND {COUNTED} '
                            'AND py_lower(main_category) = ? AND py_lower(sub_category) = ?',
                            (account_id, main_category.lower(),
                             sub_category.lower())).fetchone()[0]


def delete_category(database_path: str, account_id: int, category_id: int):
    """Delete a category. Transactions keep their labels and count as uncategorized."""
    with _connect(database_path) as conn:
        conn.execute('DELETE FROM categories WHERE account_id = ? AND id = ?',
                     (account_id, category_id))


# --------------------------------------------------------------------------------------
# Transactions
# --------------------------------------------------------------------------------------

def _read_transaction(row: sqlite3.Row) -> ReadTransaction:
    return ReadTransaction(
        id=row['id'],
        date=row['date'],
        issuer=row['issuer'],
        amount=row['amount'],
        origin=row['origin'],
        main_category=row['main_category'],
        sub_category=row['sub_category'],
        comment=row['comment'],
        verification_number=row['verification_number'],
        modification_log=row['modification_log'],
        parent_id=row['parent_id'],
        is_split=bool(row['is_split']),
    )


def insert_transaction(database_path: str, account_id: int, transaction: Transaction):
    with _connect(database_path) as conn:
        conn.execute('INSERT INTO transactions (account_id, date, issuer, amount, origin, '
                     'main_category, sub_category, comment, verification_number) '
                     'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                     (account_id,
                      transaction.date,
                      transaction.issuer,
                      transaction.amount,
                      transaction.origin,
                      transaction.main_category,
                      transaction.sub_category,
                      transaction.comment,
                      transaction.verification_number))


def update_transaction(database_path: str, account_id: int, transaction_id: int, main_category: str | None = None, sub_category: str | None = None, date: datetime | None  = None, comment: str | None = None, modification_log: str | None = None):
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

    if modification_log is not None:
        fields.append('modification_log = ?')
        params.append(modification_log)

    if not fields:
        return

    params.extend([account_id, transaction_id])
    with _connect(database_path) as conn:
        conn.execute(f'UPDATE transactions SET {", ".join(fields)} '
                     'WHERE account_id = ? AND id = ?', params)


def get_transactions(database_path: str, account_id: int, start_date: datetime | None = None, end_date: datetime | None = None, main_category: list[str] | None = None, sub_category: list[str] | None = None, origin: str | None = None, search: str | None = None) -> list[ReadTransaction]:
    query = f'SELECT {TRANSACTION_COLUMNS} FROM transactions'
    conditions = ['account_id = ?', COUNTED]
    params: list = [account_id]

    if start_date:
        conditions.append('date >= ?')
        params.append(start_date.strftime('%Y-%m-%d'))

    if end_date:
        conditions.append('date <= ?')
        params.append(end_date.strftime('%Y-%m-%d'))

    if main_category:
        placeholders = ', '.join(['?'] * len(main_category))
        conditions.append(f"py_lower(main_category) IN ({placeholders})")
        params.extend(c.lower() for c in main_category)

    if sub_category:
        placeholders = ', '.join(['?'] * len(sub_category))
        conditions.append(f"py_lower(sub_category) IN ({placeholders})")
        params.extend(c.lower() for c in sub_category)

    if origin:
        conditions.append('origin LIKE ?')
        params.append(f'%{origin}%')

    if search:
        conditions.append('(issuer LIKE ? OR comment LIKE ?)')
        params.extend([f'%{search}%', f'%{search}%'])

    query += ' WHERE ' + ' AND '.join(conditions) + ' ORDER BY date, id'

    with _connect(database_path) as conn:
        return [_read_transaction(r) for r in conn.execute(query, params).fetchall()]


def get_unclassified_transactions(database_path: str, account_id: int) -> list[ReadTransaction]:
    with _connect(database_path) as conn:
        rows = conn.execute(f'SELECT {TRANSACTION_COLUMNS} FROM transactions '
                            f'WHERE account_id = ? AND {COUNTED} '
                            'AND (main_category IS NULL OR sub_category IS NULL) '
                            'ORDER BY date, id', (account_id,)).fetchall()
        return [_read_transaction(r) for r in rows]


def count_transactions(database_path: str, account_id: int) -> int:
    with _connect(database_path) as conn:
        return conn.execute('SELECT COUNT(*) FROM transactions WHERE account_id = ?',
                            (account_id,)).fetchone()[0]


def count_unclassified_transactions(database_path: str, account_id: int) -> int:
    with _connect(database_path) as conn:
        return conn.execute('SELECT COUNT(*) FROM transactions WHERE account_id = ? '
                            f'AND {COUNTED} AND (main_category IS NULL OR sub_category IS NULL)',
                            (account_id,)).fetchone()[0]


def get_transaction(database_path: str, account_id: int, dataid: int) -> ReadTransaction | None:
    with _connect(database_path) as conn:
        row = conn.execute(f'SELECT {TRANSACTION_COLUMNS} FROM transactions '
                           'WHERE account_id = ? AND id = ?', (account_id, dataid)).fetchone()
        return _read_transaction(row) if row else None


def get_split_parts(database_path: str, account_id: int, parent_id: int) -> list[ReadTransaction]:
    with _connect(database_path) as conn:
        rows = conn.execute(f'SELECT {TRANSACTION_COLUMNS} FROM transactions '
                            'WHERE account_id = ? AND parent_id = ? ORDER BY id',
                            (account_id, parent_id)).fetchall()
        return [_read_transaction(r) for r in rows]


def split_transaction(database_path: str, account_id: int, transaction_id: int,
                      parts: list[SplitPart], parent_log: str | None = None) -> list[int]:
    """Replace a transaction by parts that add up to its amount. Splitting an already split
    transaction replaces its parts. Returns the ids of the parts."""
    if len(parts) < 2:
        raise ValueError('A split needs at least two parts.')
    with _connect(database_path) as conn:
        parent = conn.execute(f'SELECT {TRANSACTION_COLUMNS} FROM transactions '
                              'WHERE account_id = ? AND id = ?',
                              (account_id, transaction_id)).fetchone()
        if parent is None:
            raise ValueError(f'No transaction found with id {transaction_id}.')
        if parent['parent_id'] is not None:
            raise ValueError('This is a part of a split transaction; change the split of the '
                             'original instead.')
        if any(round(p.amount * 100) == 0 for p in parts):
            raise ValueError('Every part needs an amount.')
        total = sum(round(p.amount * 100) for p in parts)
        if total != round(parent['amount'] * 100):
            raise ValueError(f'The parts add up to {total / 100:.2f}, '
                             f'not {parent["amount"]:.2f}.')

        conn.execute('DELETE FROM transactions WHERE account_id = ? AND parent_id = ?',
                     (account_id, transaction_id))
        ids = []
        for p in parts:
            c = conn.execute('INSERT INTO transactions (account_id, date, issuer, amount, origin, '
                             'main_category, sub_category, comment, parent_id, modification_log) '
                             'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                             (account_id, parent['date'], parent['issuer'],
                              round(p.amount, 2), parent['origin'], p.main_category,
                              p.sub_category, p.comment, transaction_id,
                              f'Part of transaction #{transaction_id}'))
            ids.append(c.lastrowid)
        conn.execute('UPDATE transactions SET is_split = 1, '
                     'modification_log = COALESCE(?, modification_log) '
                     'WHERE account_id = ? AND id = ?',
                     (parent_log, account_id, transaction_id))
        return ids


def unsplit_transaction(database_path: str, account_id: int, transaction_id: int,
                        parent_log: str | None = None):
    """Remove the parts of a split transaction so the original counts again."""
    with _connect(database_path) as conn:
        conn.execute('DELETE FROM transactions WHERE account_id = ? AND parent_id = ?',
                     (account_id, transaction_id))
        conn.execute('UPDATE transactions SET is_split = 0, '
                     'modification_log = COALESCE(?, modification_log) '
                     'WHERE account_id = ? AND id = ?',
                     (parent_log, account_id, transaction_id))


def latest_transaction_date(database_path: str, account_id: int) -> str | None:
    with _connect(database_path) as conn:
        return conn.execute('SELECT MAX(date) FROM transactions WHERE account_id = ?',
                            (account_id,)).fetchone()[0]


def get_years(database_path: str, account_id: int) -> list[int]:
    """Years that have transactions, newest first."""
    with _connect(database_path) as conn:
        rows = conn.execute('SELECT DISTINCT substr(date, 1, 4) FROM transactions '
                            'WHERE account_id = ? ORDER BY 1 DESC', (account_id,)).fetchall()
        return [int(r[0]) for r in rows if r[0] and r[0].isdigit()]


def get_origins(database_path: str, account_id: int) -> list[str]:
    with _connect(database_path) as conn:
        rows = conn.execute('SELECT DISTINCT origin FROM transactions WHERE account_id = ? '
                            'ORDER BY origin', (account_id,)).fetchall()
        return [r[0] for r in rows]


# --------------------------------------------------------------------------------------
# Issuer classifications
# --------------------------------------------------------------------------------------

def _issuer(row: sqlite3.Row) -> IssuerClassification:
    return IssuerClassification(issuer=row['issuer'], main_category=row['main_category'],
                                sub_category=row['sub_category'])


def classify_issuer(database_path: str, account_id: int, classification: IssuerClassification):
    with _connect(database_path) as conn:
        conn.execute('''INSERT INTO issuer_classifications
                        (account_id, issuer, main_category, sub_category)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(account_id, issuer) DO UPDATE SET
                        main_category = excluded.main_category,
                        sub_category = excluded.sub_category''',
                     (account_id,
                      classification.issuer,
                      classification.main_category,
                      classification.sub_category))


def get_issuer_classification(database_path: str, account_id: int, issuer: str) -> IssuerClassification | None:
    with _connect(database_path) as conn:
        row = conn.execute('SELECT * FROM issuer_classifications '
                           'WHERE account_id = ? AND issuer = ?', (account_id, issuer)).fetchone()
        return _issuer(row) if row else None


def get_issuer_classification_by_id(database_path: str, account_id: int, issuer_id: int) -> IssuerClassification | None:
    with _connect(database_path) as conn:
        row = conn.execute('SELECT * FROM issuer_classifications '
                           'WHERE account_id = ? AND id = ?', (account_id, issuer_id)).fetchone()
        return _issuer(row) if row else None


def get_issuer_classifications(database_path: str, account_id: int) -> List[Tuple[int, IssuerClassification]]:
    with _connect(database_path) as conn:
        rows = conn.execute('SELECT * FROM issuer_classifications WHERE account_id = ? '
                            'ORDER BY issuer', (account_id,)).fetchall()
        return [(r['id'], _issuer(r)) for r in rows]


def remove_issuer_classification(database_path: str, account_id: int, issuer_id: int):
    with _connect(database_path) as conn:
        conn.execute('DELETE FROM issuer_classifications WHERE account_id = ? AND id = ?',
                     (account_id, issuer_id))


def modify_issuer_classification(database_path: str, account_id: int, issuer_id: int, main_category: str, sub_category: str):
    with _connect(database_path) as conn:
        conn.execute('''UPDATE issuer_classifications
                        SET main_category = ?, sub_category = ?
                        WHERE account_id = ? AND id = ?''',
                     (main_category, sub_category, account_id, issuer_id))


# --------------------------------------------------------------------------------------
# Settings and allowances
# --------------------------------------------------------------------------------------

def get_setting(database_path: str, account_id: int, key: str) -> str | None:
    with _connect(database_path) as conn:
        row = conn.execute('SELECT value FROM settings WHERE account_id = ? AND key = ?',
                           (account_id, key)).fetchone()
        return row[0] if row else None


def set_setting(database_path: str, account_id: int, key: str, value: str):
    with _connect(database_path) as conn:
        conn.execute('INSERT INTO settings (account_id, key, value) VALUES (?, ?, ?) '
                     'ON CONFLICT(account_id, key) DO UPDATE SET value = excluded.value',
                     (account_id, key, str(value)))


def get_allowances(database_path: str, account_id: int, year: int, month: int | None = None) -> list[sqlite3.Row]:
    with _connect(database_path) as conn:
        if month is None:
            return conn.execute('SELECT * FROM allowances WHERE account_id = ? AND year = ? '
                                'ORDER BY month', (account_id, year)).fetchall()
        return conn.execute('SELECT * FROM allowances WHERE account_id = ? AND year = ? '
                            'AND month = ?', (account_id, year, month)).fetchall()


def set_allowance(database_path: str, account_id: int, year: int, month: int,
                  rikard: float | None = None, sara: float | None = None,
                  only_if_missing: bool = False):
    """Insert or update the allowance for a month. None leaves that person's value as is."""
    with _connect(database_path) as conn:
        conn.execute('INSERT OR IGNORE INTO allowances (account_id, year, month) VALUES (?, ?, ?)',
                     (account_id, year, month))
        if only_if_missing and conn.total_changes == 0:
            return
        if rikard is not None:
            conn.execute('UPDATE allowances SET rikard_allowance = ? '
                         'WHERE account_id = ? AND year = ? AND month = ?',
                         (rikard, account_id, year, month))
        if sara is not None:
            conn.execute('UPDATE allowances SET sara_allowance = ? '
                         'WHERE account_id = ? AND year = ? AND month = ?',
                         (sara, account_id, year, month))
