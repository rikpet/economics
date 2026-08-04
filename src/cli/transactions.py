from datetime import datetime, timedelta
import os
import sqlite3
import click
import questionary

from app_types import IssuerClassification
from balance import Balance
from constants import DATABASE_PATH
import calendar

import database as db
from parser import parse_remember_transactions, parse_seb_transactions
from printout import generate_table


def select_file(start_dir="."):
    """Interactively browse the filesystem and pick a file.

    Shows a selectable list of the entries in the current directory. Choosing a
    directory navigates into it, ".." goes up one level, and choosing a file
    returns its path. Returns None if the user cancels.
    """
    current = os.path.abspath(start_dir)
    while True:
        try:
            entries = sorted(os.listdir(current))
        except OSError:
            entries = []

        dirs = [e for e in entries if os.path.isdir(os.path.join(current, e))]
        files = [e for e in entries if os.path.isfile(os.path.join(current, e))]

        choices = [questionary.Choice("..", value=("up", None))]
        choices += [questionary.Choice(f"{d}/", value=("dir", d)) for d in dirs]
        choices += [questionary.Choice(f, value=("file", f)) for f in files]

        selection = questionary.select(
            f"Select a transactions file  [{current}]",
            choices=choices,
        ).ask()

        if selection is None:
            return None

        kind, name = selection
        if kind == "up":
            current = os.path.dirname(current)
        elif kind == "dir":
            current = os.path.join(current, name)
        else:  # file
            return os.path.join(current, name)


@click.command(name='add')
@click.argument('file_path', required=False)
@click.argument('origin', required=False)
def add_transactions(file_path, origin):
    """Adds transactions to database

    Args:
        file_path (str): Path to the transactions file. If omitted, an
            interactive file selector is shown.
        origin (str): Origin of the transactions, e.g., "SEB" or "Remember".
            If omitted, an interactive selector is shown.
    """
    if file_path is None:
        file_path = select_file("originals" if os.path.isdir("originals") else ".")
        if not file_path:
            return

    if origin is None:
        origin = questionary.select(
            "Origin of the transactions:",
            choices=["SEB", "Remember"],
            use_shortcuts=True,
        ).ask()
        if origin is None:
            return

    click.echo(f'Processing file: {file_path}')

    if origin.lower() == "seb":
        transactions = parse_seb_transactions(file_path)
    elif origin.lower() == "remember":
        transactions = parse_remember_transactions(file_path)
    else:
        raise ValueError("Unsupported origin")
    
    added = 0
    skipped_duplicates = 0
    for trans in transactions:
        issuer = db.get_issuer_classification(DATABASE_PATH, trans.issuer)

        trans.main_category = issuer.main_category if issuer is not None else None
        trans.sub_category = issuer.sub_category if issuer is not None else None

        try:
            db.insert_transaction(DATABASE_PATH, trans)
            added += 1
        except sqlite3.IntegrityError:
            skipped_duplicates += 1

    click.echo(f'Added {added} transactions. Skipped {skipped_duplicates} duplicates.')

#TODO: add check on category and sub-category
@click.command(name='list')
@click.option('--start-date', type=click.DateTime(formats=["%Y-%m-%d"]), default=None, help="Start date (YYYY-MM-DD)")
@click.option('--end-date', type=click.DateTime(formats=["%Y-%m-%d"]), default=None, help="End date (YYYY-MM-DD)")
@click.option('--month', type=int, default=None, help="Month (1-12)")
@click.option('--year', type=int, default=None, help="Year (e.g., 2023)")
@click.option('--category', type=str, default=None, multiple=True, help="Filter by main category")
@click.option('--sub-category', type=str, default=None, multiple=True, help="Filter by sub-category")
@click.option('--origin', type=str, default=None, help="Filter by origin (substring match)")
@click.option('--sort-date', type=click.Choice(['asc', 'desc']), default=None, help="Sort transactions by date")
@click.option('--sum', 'show_sum', is_flag=True, help="Show sum of transaction amounts")
@click.option('--count', 'show_count', is_flag=True, help="Show the number of transactions")
@click.option('--verbose', '-v', is_flag=True, help="Show all transaction information")
def list_transactions(start_date, end_date, month, year, category: tuple[str], sub_category: tuple[str], origin: str, sort_date: str, show_sum: bool, show_count: bool, verbose: bool):
    """List all transactions in the database, optionally filtered by date range."""

    year = datetime.now().year if year is None else year
    if month:
        start_date = datetime(year, month, 1)
        days_in_month = calendar.monthrange(year, month)[1]
        end_date = start_date + timedelta(days=days_in_month - 1)

    transactions = db.get_transactions(DATABASE_PATH,start_date=start_date, end_date=end_date, main_category=list(category), sub_category=list(sub_category), origin=origin)

    if len(transactions) == 0:
        click.echo('No transactions found.')
        return

    if sort_date:
        transactions.sort(key=lambda t: t.date, reverse=(sort_date == 'desc'))

    if verbose:
        header = ["ID", "ISSUER", "AMOUNT", "DATE", "ORIGIN", "MAIN CATEGORY", "SUB CATEGORY", "COMMENT", "VERIFICATION NUMBER", "MODIFICATION LOG"]
    else:
        header = ["ID", "ISSUER", "AMOUNT", "DATE", "ORIGIN", "MAIN CATEGORY", "SUB CATEGORY"]

    rows = []
    for trans in transactions:
        if verbose:
            rows.append([
                trans.id,
                trans.issuer,
                trans.amount,
                trans.date,
                trans.origin,
                trans.main_category if trans.main_category is not None else "",
                trans.sub_category if trans.sub_category is not None else "",
                trans.comment if trans.comment is not None else "",
                trans.verification_number if trans.verification_number is not None else "",
                trans.modification_log if trans.modification_log is not None else ""
            ])
        else:
            rows.append([
                trans.id,
                trans.issuer,
                trans.amount,
                trans.date,
                trans.origin,
                trans.main_category if trans.main_category is not None else "",
                trans.sub_category if trans.sub_category is not None else ""
            ])

    click.echo('Listing transactions:\n')
    click.echo(generate_table(
        header=header,
        rows=rows
    ))

    if show_sum:
        total_amount = sum(t.amount for t in transactions)
        click.echo(f'\nTotal amount: {total_amount:.2f}')

    if show_count:
        click.echo(f'\nNumber of transactions: {len(transactions)}')

@click.command(name='modify')
@click.argument('transaction_id', type=int)
@click.option('--category', 'main_category', type=str, default=None, help="New main category")
@click.option('--sub-category', type=str, default=None, help="New sub-category")
@click.option('--date', type=click.DateTime(formats=["%Y-%m-%d"]), default=None, help="New date (YYYY-MM-DD)")
def modify_transaction(transaction_id, main_category, sub_category, date):
    """Modify an existing transaction."""
    if main_category is None and sub_category is None and date is None:
        click.echo('No modifications specified. Use --category, --sub-category, or --date to specify modifications.')
        return

    trans = db.get_transaction(DATABASE_PATH, transaction_id)
    if trans is None:
        click.echo(f'No transaction found with id {transaction_id}.')
        return

    changes = []
    if main_category is not None:
        changes.append(f"main_category: {trans.main_category} -> {main_category}")
    if sub_category is not None:
        changes.append(f"sub_category: {trans.sub_category} -> {sub_category}")
    if date is not None:
        changes.append(f"date: {trans.date} -> {date.strftime('%Y-%m-%d')}")

    log_entry = f"[{datetime.now().strftime('%Y-%m-%d')}] modified {', '.join(changes)}"
    new_log = f"{trans.modification_log}\n{log_entry}" if trans.modification_log else log_entry

    db.update_transaction(DATABASE_PATH, transaction_id, main_category, sub_category, date, modification_log=new_log)


@click.command(name='classify')
def classify_transactions():
    """Classify transactions not yet classified."""
    unclassified_transactions = db.get_unclassified_transactions(DATABASE_PATH)
    for trans in unclassified_transactions:

        mock = Balance(2025, 1)
        
        # Check if the issuer can be classified
        issuer = db.get_issuer_classification(DATABASE_PATH, trans.issuer)
        if issuer is not None:
            db.update_transaction(DATABASE_PATH, trans.id, issuer.main_category, issuer.sub_category)
            continue

        # Prompt user for classification
        click.echo(f'\n\nTransaction: {trans.issuer} | {trans.amount} | {trans.date} | {trans.origin}' )

        main_category=questionary.select(
            "Main category for this transaction",
            choices=["SKIP"] + list(mock.categories()),
            use_shortcuts=True,

        ).ask()

        if main_category is None:
            return
        
        if main_category == "SKIP":
            continue
            
        sub_categories = mock.sub_categories(main_category)
        if len(sub_categories) == 1:
            sub_category = sub_categories[0]
        else:
            sub_category = questionary.select(
                "Sub category for this transaction",
                choices=sub_categories,
                use_shortcuts=True
            ).ask()

            if sub_category is None:
                return

        comment = questionary.text("Comment (optional, leave empty to skip):").ask()
        if comment is None:
            return
        comment = comment.strip() or None

        store_issuer_classification: bool = questionary.confirm(
            "Store this classification for future use?",
            default=False
        ).ask()

        if store_issuer_classification:
            db.classify_issuer(DATABASE_PATH, IssuerClassification(
                issuer=trans.issuer,
                main_category=main_category,
                sub_category=sub_category
            ))

        db.update_transaction(DATABASE_PATH, trans.id, main_category, sub_category, comment=comment)


@click.command(name='unclassified')
def unclassified_transactions():
    """Check for unclassified transactions."""
    unclassified_transactions = db.get_unclassified_transactions(DATABASE_PATH)
    if len(unclassified_transactions) == 0:
        click.echo('No unclassified transactions found.')
        return
    click.echo(f'Found {len(unclassified_transactions)} unclassified transactions.')

