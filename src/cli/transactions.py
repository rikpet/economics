from datetime import datetime, timedelta
import click
import questionary

from app_types import IssuerClassification
from constants import DATABASE_PATH

from categories import CATEGORIES

from database import classify_issuer, get_issuer_classification, get_transactions, get_transactions, get_unclassified_transactions, insert_transaction, update_transaction
from parser import parse_remember_transactions, parse_seb_transactions


@click.command(name='add')
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


@click.command(name='list')
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
    click.echo('-' * (5 + 3 + max_issuer_length + 3 + 10 + 3 + 3 + 10 + 3 + 15 + 3 + 15))
    
    for trans in transactions:
        click.echo(f'{trans.id:<5} | {trans.issuer:<{max_issuer_length + 3}} | {trans.amount:>10.2f} | {trans.date:<10} | {trans.main_category:<15} | {trans.sub_category:<15}')



@click.command(name='classify')
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

        main_category=questionary.select(
            "Main category for this transaction",
            choices=list(CATEGORIES.keys())
        ).ask()

        sub_categories = CATEGORIES.get(main_category, [])
        if len(sub_categories) == 1:
            sub_category = sub_categories[0]
        else:
            sub_category = questionary.select(
                "Sub category for this transaction",
                choices=sub_categories
            ).ask()
        
        store_issuer_classification = questionary.confirm(
            "Store this classification for future use?",
            default=False
        ).ask()

        if store_issuer_classification.lower() == 'y':
            classify_issuer(DATABASE_PATH, IssuerClassification(
                issuer=trans.issuer,
                main_category=main_category,
                sub_category=sub_category
            ))

        update_transaction(DATABASE_PATH, trans.id, main_category, sub_category)

