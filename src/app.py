import os
import click
import calendar
from datetime import datetime, timedelta
from tabulate import tabulate

from app_types import IssuerClassification
from budget import get_monthly_budget
from categories import CATEGORIES
from parser import parse_original_transactions, parse_seb_transactions, parse_remember_transactions
from database import *


DATABASE_NAME = 'transactions.db'
DATABASE_PATH = f'./{DATABASE_NAME}'

@click.group()
def cli():
    pass

# -------------------------------------------------------------------
# TRANSACTION COMMAND GROUP
# -------------------------------------------------------------------

@cli.group()
def trans():
    pass


@trans.command(name='add')
@click.argument('file_path')
@click.argument('origin')
def add_transactions(file_path, origin):
    """Adds transactions to database
    
    Args:
        file_path (str): Path to the transactions file.
        origin (str): Origin of the transactions, e.g., "SEB" or "Remember".
    """
    click.echo(f'Processing file: {file_path}')

    if origin.lower() == "seb":
        transactions = parse_seb_transactions(file_path)
    elif origin.lower() == "remember":
        transactions = parse_remember_transactions(file_path)
    else:
        raise ValueError("Unsupported origin")
    
    for trans in transactions:
        trans.main_category, trans.sub_category = get_issuer_classification(DATABASE_PATH, trans.issuer)
        insert_transaction(DATABASE_PATH, trans)


@trans.command(name='list')
@click.option('--start-date', type=click.DateTime(formats=["%Y-%m-%d"]), default=None, help="Start date (YYYY-MM-DD)")
@click.option('--end-date', type=click.DateTime(formats=["%Y-%m-%d"]), default=None, help="End date (YYYY-MM-DD)")
@click.option('--month', type=int, default=None, help="Month (1-12)")
def list_transactions(start_date, end_date, month):
    """List all transactions in the database, optionally filtered by date range."""
        
    if month:
        year = datetime.now().year
        start_date = datetime(year, month, 1)
        end_date = datetime(year, month + 1, 1) - timedelta(days=1)

    transactions = get_transactions(DATABASE_PATH,start_date=start_date, end_date=end_date)

    if len(transactions) == 0:
        click.echo('No transactions found.')
        return
    
    max_issuer_length = max(len(t.issuer) for t in transactions)

    click.echo('Listing transactions:\n')
    click.echo(f'{"ID":<5} | {"ISSUER":<{max_issuer_length + 3}} | {"AMOUNT":<10} | {"DATE":<10} | {"MAIN CATEGORY":<15} | {"SUB CATEGORY":<15}')
    click.echo('-' * (5 + 3 + max_issuer_length + 3 + 10 + 3 + 10 + 3 + 15 + 3 + 15))
    
    for trans in transactions:
        click.echo(f'{trans.id:<5} | {trans.issuer:<{max_issuer_length + 3}} | {trans.amount:>10.2f} | {trans.date:<10} | {trans.main_category:<15} | {trans.sub_category:<15}')



@trans.command(name='classify')
def classify_transactions():
    """Classify transactions not yet classified."""
    unclassified_transactions = get_unclassified_transactions()
    for trans in unclassified_transactions:
        
        # Check if the issuer can be classified
        if get_issuer_classification(DATABASE_PATH, trans.issuer) != (None, None):
            update_transaction(DATABASE_PATH, trans.id, *get_issuer_classification(DATABASE_PATH, trans.issuer))
            continue

        # Prompt user for classification
        click.echo(f'\n\nTransaction: {trans.issuer} | {trans.amount} | {trans.date}' )
        main_category = click.prompt(
            "Main category for this transaction",
            type=click.Choice(CATEGORIES.keys(), case_sensitive=False)
        )
        sub_category = click.prompt(
            "Sub category for this transaction",
            type=click.Choice(CATEGORIES.get(main_category, []), case_sensitive=False)
        )
        store_issuer_classification = click.prompt("Store this classification for future use? (y/n)", default="n")

        if store_issuer_classification.lower() == 'y':
            classify_issuer(DATABASE_PATH, IssuerClassification(
                issuer=trans.issuer,
                main_category=main_category,
                sub_category=sub_category
            ))

        update_transaction(DATABASE_PATH, trans.id, main_category, sub_category)



# -------------------------------------------------------------------
# ISSUER COMMAND GROUP
# -------------------------------------------------------------------

@cli.group()
def issuer():
    pass


@issuer.command(name='list')
def list_issuers():
    """List all issuer classifications."""
    with sqlite3.connect(DATABASE_PATH) as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM issuer_classifications')
        rows = c.fetchall()
        if not rows:
            click.echo('No issuer classifications found.')
            return
        click.echo(f'{"ISSUER":<25} | {"MAIN CATEGORY":<15} | {"SUB CATEGORY":<15}')
        click.echo('-' * 60)
        for row in rows:
            click.echo(f'{row[0]:<25} | {row[1]:<15} | {row[2]:<15}')


@issuer.command()
def add():
    """Add a new issuer classification."""
    issuer = click.prompt("Issuer name")
    main_category = click.prompt(
        "Main category",
        type=click.Choice(CATEGORIES.keys(), case_sensitive=False)
    )
    sub_category = click.prompt(
        "Sub category",
        type=click.Choice(CATEGORIES.get(main_category, []), case_sensitive=False)
    )
    classify_issuer(DATABASE_PATH, IssuerClassification(
        issuer=issuer,
        main_category=main_category,
        sub_category=sub_category
    ))
    click.echo(f'Issuer classification for {issuer} added.')




@cli.command()
def unclassified_transactions():
    """Check for unclassified transactions."""
    unclassified_transactions = get_unclassified_transactions()
    if len(unclassified_transactions) == 0:
        click.echo('No unclassified transactions found.')
        return
    click.echo(f'Found {len(unclassified_transactions)} unclassified transactions.')


@cli.command()
def budget():
    """Show budget summary."""
    show_sub_category = False

    transactions = get_transactions(DATABASE_PATH, datetime.strptime('2025-01-01', '%Y-%m-%d'), datetime.strptime('2025-12-31', '%Y-%m-%d'))

    summary = get_monthly_budget(transactions)

    months: list[str] = [str(calendar.month_name[m]) for m in summary.keys()]

    table_data = [[c.capitalize()] for c in next(iter(summary.values())).keys()]
    for _, monthly_data in summary.items():
        for main_cat, main_cat_data in monthly_data.items():
            for i in table_data:
                if i[0].lower() == main_cat:
                    i.append(main_cat_data['total'])
                    break

    click.echo('Budget summary')
    click.echo(tabulate(table_data, headers=['Category'] + months, floatfmt=".2f"))


@cli.command()
@click.argument('file_path')
def add_originals(file_path):
    """Adds original transactions to database
    
    Args:
        file_path (str): Path to the original transactions file.
    """
    click.echo(f'Processing file: {file_path}')
    transactions = parse_original_transactions(file_path)
    
    for trans in transactions:
        insert_transaction(DATABASE_PATH, trans)


def main():
    if not os.path.exists(DATABASE_PATH):
        create_tables()
    cli()

if __name__ == '__main__':
    budget()