import os
import shutil
import sqlite3
import subprocess
import sys

import database
from app_types import Transaction
from parser import parse_remember_transactions, parse_seb_transactions

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOCK_DB_PATH = 'mock_backfill.db'
SCRIPT = os.path.join(REPO_ROOT, 'scripts', 'backfill_verification_numbers.py')


def setup_function(_):
    if os.path.exists(MOCK_DB_PATH):
        os.remove(MOCK_DB_PATH)
    database.create_tables(MOCK_DB_PATH)


def teardown_function(_):
    if os.path.exists(MOCK_DB_PATH):
        try:
            os.remove(MOCK_DB_PATH)
        except PermissionError:
            pass


def _seed_with_null_vns(originals_dir: str):
    """Insert all source rows from the fixtures dir with verification_number=None."""
    for name in sorted(os.listdir(originals_dir)):
        path = os.path.join(originals_dir, name)
        lower = name.lower()
        if lower.startswith('seb_') and lower.endswith('.csv'):
            txs = parse_seb_transactions(path)
        elif lower.startswith('remember_') and lower.endswith('.xls'):
            txs = parse_remember_transactions(path)
        else:
            continue
        for t in txs:
            t.verification_number = None
            database.insert_transaction(MOCK_DB_PATH, t)


def _run_backfill(originals_dir: str, apply: bool):
    cmd = [sys.executable, SCRIPT, '--db', MOCK_DB_PATH, '--originals', originals_dir]
    if apply:
        cmd.append('--apply')
    return subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)


def test_backfill_fills_all_rows(tmp_path):
    fixtures = tmp_path / 'originals'
    fixtures.mkdir()
    shutil.copy(os.path.join(REPO_ROOT, 'tests', 'input_data', 'seb_transactions.csv'),
                fixtures / 'seb_test.csv')
    shutil.copy(os.path.join(REPO_ROOT, 'tests', 'input_data', 'remember_card_transactions.xls'),
                fixtures / 'remember_test.xls')

    _seed_with_null_vns(str(fixtures))

    with sqlite3.connect(MOCK_DB_PATH) as conn:
        nulls_before = conn.execute(
            'SELECT COUNT(*) FROM transactions WHERE verification_number IS NULL'
        ).fetchone()[0]
    assert nulls_before == 8 + 5

    result = _run_backfill(str(fixtures), apply=True)
    assert result.returncode == 0, result.stderr

    with sqlite3.connect(MOCK_DB_PATH) as conn:
        nulls_after = conn.execute(
            'SELECT COUNT(*) FROM transactions WHERE verification_number IS NULL'
        ).fetchone()[0]
        rows = conn.execute(
            'SELECT verification_number FROM transactions'
        ).fetchall()
    assert nulls_after == 0
    vns = [r[0] for r in rows]
    assert len(set(vns)) == len(vns)
    assert all(v.startswith('SEB_') or v.startswith('REM_') for v in vns)

    # Idempotent: re-running finds zero null rows.
    result2 = _run_backfill(str(fixtures), apply=True)
    assert result2.returncode == 0
    assert 'Matched updates:        0' in result2.stdout
