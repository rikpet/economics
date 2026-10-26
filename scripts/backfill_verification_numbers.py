"""Backfill verification_number for transactions already in the database.

Re-parses every CSV/XLS file in originals/ and matches each parsed source row
against DB rows that have verification_number IS NULL by (date, amount, origin,
issuer). When N source rows share a key with N DB rows, they are paired in id
order so duplicate-purchase rows all get filled deterministically.

Usage:
    python scripts/backfill_verification_numbers.py [--apply] [--originals DIR] [--db PATH]
        [--account ID]
"""

import argparse
import os
import sqlite3
import sys
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, 'src'))

from parser import parse_seb_transactions, parse_remember_transactions  # noqa: E402
from constants import DATABASE_PATH  # noqa: E402
from database import create_tables  # noqa: E402


def parse_originals(originals_dir: str):
    parsed = []
    for name in sorted(os.listdir(originals_dir)):
        path = os.path.join(originals_dir, name)
        lower = name.lower()
        if lower.startswith('seb_') and lower.endswith('.csv'):
            parsed.extend(parse_seb_transactions(path))
        elif lower.startswith('remember_') and lower.endswith('.xls'):
            parsed.extend(parse_remember_transactions(path))
    return parsed


def load_null_rows(db_path: str, account_id: int):
    with sqlite3.connect(db_path) as conn:
        c = conn.cursor()
        c.execute(
            'SELECT id, date, issuer, amount, origin FROM transactions '
            'WHERE verification_number IS NULL AND account_id = ? ORDER BY id',
            (account_id,)
        )
        return c.fetchall()


def key(date: str, amount: float, origin: str, issuer: str):
    return (date, round(float(amount), 2), origin, issuer.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='Write updates (default: dry-run)')
    ap.add_argument('--originals', default=os.path.join(REPO_ROOT, 'originals'))
    ap.add_argument('--db', default=DATABASE_PATH)
    ap.add_argument('--account', type=int, default=1, help='Account id (default: 1)')
    args = ap.parse_args()

    create_tables(args.db)

    print(f'DB: {args.db}')
    print(f'Originals: {args.originals}')
    print(f'Mode: {"APPLY" if args.apply else "DRY-RUN"}\n')

    sources = parse_originals(args.originals)
    print(f'Parsed {len(sources)} source transactions from originals/')

    db_rows = load_null_rows(args.db, args.account)
    print(f'Found {len(db_rows)} DB rows with verification_number IS NULL')

    db_by_key = defaultdict(list)
    for row_id, date, issuer, amount, origin in db_rows:
        db_by_key[key(date, amount, origin, issuer)].append(row_id)

    src_by_key = defaultdict(list)
    for t in sources:
        src_by_key[key(t.date, t.amount, t.origin, t.issuer)].append(t)

    updates = []
    src_unmatched = 0
    for k, src_list in src_by_key.items():
        db_ids = db_by_key.get(k, [])
        n = min(len(src_list), len(db_ids))
        for i in range(n):
            updates.append((db_ids[i], src_list[i].verification_number))
        src_unmatched += max(0, len(src_list) - len(db_ids))
        db_by_key[k] = db_ids[n:]

    db_unmatched = sum(len(v) for v in db_by_key.values())

    seen = {}
    collisions = 0
    for row_id, vn in updates:
        if vn in seen:
            collisions += 1
        seen[vn] = row_id

    print(f'\nMatched updates:        {len(updates)}')
    print(f'Source rows w/o DB row: {src_unmatched}')
    print(f'DB rows w/o source:     {db_unmatched}')
    print(f'Verification # collisions in update set: {collisions}')

    if not args.apply:
        print('\nDry-run; no changes made. Re-run with --apply to write.')
        return

    if collisions:
        print('\nAborting: would-be updates contain duplicate verification numbers.')
        sys.exit(1)

    with sqlite3.connect(args.db) as conn:
        c = conn.cursor()
        try:
            c.executemany(
                'UPDATE transactions SET verification_number = ? WHERE id = ?',
                [(vn, rid) for rid, vn in updates],
            )
            conn.commit()
        except sqlite3.IntegrityError as e:
            conn.rollback()
            print(f'\nIntegrity error, rolled back: {e}')
            sys.exit(1)

    print(f'\nApplied {len(updates)} updates.')


if __name__ == '__main__':
    main()
