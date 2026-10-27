"""Actions shared by the CLI and the web UI."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime

import database as db
from app_types import IssuerClassification, SplitPart, Transaction
from parser import parse_remember_transactions, parse_seb_transactions

ORIGINS = {
    "seb": parse_seb_transactions,
    "remember": parse_remember_transactions,
}


@dataclass
class ImportResult:
    added: int = 0
    skipped_duplicates: int = 0
    classified: int = 0


def parse_file(file_path: str, origin: str) -> list[Transaction]:
    parser = ORIGINS.get(origin.lower())
    if parser is None:
        raise ValueError(f"Unsupported origin: {origin}. Choose one of {', '.join(ORIGINS)}.")
    return parser(file_path)


def import_transactions(database_path: str, account_id: int,
                        transactions: list[Transaction]) -> ImportResult:
    """Insert transactions, classifying them by the account's issuer rules and skipping
    ones already imported."""
    result = ImportResult()
    for trans in transactions:
        issuer = db.get_issuer_classification(database_path, account_id, trans.issuer)

        trans.main_category = issuer.main_category if issuer is not None else None
        trans.sub_category = issuer.sub_category if issuer is not None else None

        try:
            db.insert_transaction(database_path, account_id, trans)
            result.added += 1
            if issuer is not None:
                result.classified += 1
        except sqlite3.IntegrityError:
            result.skipped_duplicates += 1
    return result


def import_file(database_path: str, account_id: int, file_path: str, origin: str) -> ImportResult:
    return import_transactions(database_path, account_id, parse_file(file_path, origin))


def apply_issuer_rules(database_path: str, account_id: int) -> int:
    """Classify unclassified transactions that have an issuer rule. Returns how many."""
    count = 0
    for trans in db.get_unclassified_transactions(database_path, account_id):
        issuer = db.get_issuer_classification(database_path, account_id, trans.issuer)
        if issuer is not None:
            db.update_transaction(database_path, account_id, trans.id,
                                  issuer.main_category, issuer.sub_category)
            count += 1
    return count


def classify_transaction(database_path: str, account_id: int, transaction_id: int,
                         main_category: str, sub_category: str, comment: str | None = None,
                         remember_issuer: bool = False):
    trans = db.get_transaction(database_path, account_id, transaction_id)
    if trans is None:
        raise ValueError(f"No transaction found with id {transaction_id}.")

    if remember_issuer:
        db.classify_issuer(database_path, account_id, IssuerClassification(
            issuer=trans.issuer,
            main_category=main_category,
            sub_category=sub_category
        ))

    db.update_transaction(database_path, account_id, transaction_id, main_category,
                          sub_category, comment=comment)


def modify_transaction(database_path: str, account_id: int, transaction_id: int,
                       main_category: str | None = None, sub_category: str | None = None,
                       date: datetime | None = None, comment: str | None = None) -> bool:
    """Change a transaction and record the change in its modification log.

    Returns False if nothing changed.
    """
    trans = db.get_transaction(database_path, account_id, transaction_id)
    if trans is None:
        raise ValueError(f"No transaction found with id {transaction_id}.")

    changes = []
    if main_category is not None and main_category != trans.main_category:
        changes.append(f"main_category: {trans.main_category} -> {main_category}")
    if sub_category is not None and sub_category != trans.sub_category:
        changes.append(f"sub_category: {trans.sub_category} -> {sub_category}")
    if date is not None and date.strftime('%Y-%m-%d') != trans.date:
        changes.append(f"date: {trans.date} -> {date.strftime('%Y-%m-%d')}")
    if comment is not None and comment != (trans.comment or ""):
        changes.append(f"comment: {trans.comment or ''} -> {comment}")

    if not changes:
        return False

    log_entry = f"[{datetime.now().strftime('%Y-%m-%d')}] modified {', '.join(changes)}"
    new_log = f"{trans.modification_log}\n{log_entry}" if trans.modification_log else log_entry

    db.update_transaction(database_path, account_id, transaction_id, main_category,
                          sub_category, date, comment=comment, modification_log=new_log)
    return True


def parse_amount(text: str) -> float | None:
    """'1 234,50', '1234.5', '-300' -> float. Empty -> None."""
    text = (text or "").strip().replace(" ", "").replace(" ", "").replace("kr", "")
    text = text.replace("−", "-").replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        raise ValueError(f"Not an amount: {text!r}") from None


def split_transaction(database_path: str, account_id: int, transaction_id: int,
                      parts: list[SplitPart]) -> list[int]:
    """Split a transaction into parts that add up to its amount (or change its split)."""
    trans = db.get_transaction(database_path, account_id, transaction_id)
    if trans is None:
        raise ValueError(f"No transaction found with id {transaction_id}.")
    amounts = ", ".join(f"{p.amount:.2f}" for p in parts)
    log_entry = (f"[{datetime.now().strftime('%Y-%m-%d')}] "
                 f"{'re-split' if trans.is_split else 'split'} into {len(parts)} parts: {amounts}")
    new_log = f"{trans.modification_log}\n{log_entry}" if trans.modification_log else log_entry
    return db.split_transaction(database_path, account_id, transaction_id, parts, new_log)


def unsplit_transaction(database_path: str, account_id: int, transaction_id: int):
    trans = db.get_transaction(database_path, account_id, transaction_id)
    if trans is None or not trans.is_split:
        raise ValueError("The transaction is not split.")
    log_entry = f"[{datetime.now().strftime('%Y-%m-%d')}] split undone"
    new_log = f"{trans.modification_log}\n{log_entry}" if trans.modification_log else log_entry
    db.unsplit_transaction(database_path, account_id, transaction_id, new_log)
