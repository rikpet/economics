import click
from datetime import datetime, timedelta

from app_types import IssuerClassification
from categories import MAIN_CATEGORY, SUB_CATEGORY
from parser import parse_seb_transactions, parse_remember_transactions
from database import *

@click.group()
def cli():
    pass


@cli.command()
@click.argument('file_path')
@click.argument('origin')
def add(file_path, origin):
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
        trans.main_category, trans.sub_category = get_issuer_classification(trans.issuer)
        insert_transaction(trans)


@cli.command()
@click.option('--start-date', type=click.DateTime(formats=["%Y-%m-%d"]), default=None, help="Start date (YYYY-MM-DD)")
@click.option('--end-date', type=click.DateTime(formats=["%Y-%m-%d"]), default=None, help="End date (YYYY-MM-DD)")
@click.option('--month', type=int, default=None, help="Month (1-12)")
def list(start_date, end_date, month):
    """List all transactions in the database, optionally filtered by date range."""
        
    if month:
        year = datetime.now().year
        start_date = datetime(year, month, 1)
        end_date = datetime(year, month + 1, 1) - timedelta(days=1)

    transactions = get_transactions(start_date=start_date, end_date=end_date)

    if len(transactions) == 0:
        click.echo('No transactions found.')
        return
    
    click.echo('Listing transactions:\n')
    for trans in transactions:
        click.echo(f'{trans.issuer:<25} | {trans.amount:>10.2f} | {trans.date}')


@cli.command()
def classify():
    """Classify transactions not yet classified."""
    unclassified_transactions = get_unclassified_transactions()
    for trans in unclassified_transactions:
        
        # Check if the issuer can be classified
        if get_issuer_classification(trans.issuer) != (None, None):
            update_transaction(trans.id, *get_issuer_classification(trans.issuer))
            continue

        # Prompt user for classification
        click.echo(f'\n\nTransaction: {trans.issuer} | {trans.amount} | {trans.date}' )
        main_category = click.prompt(
            "Main category for this transaction",
            type=click.Choice(MAIN_CATEGORY, case_sensitive=False)
        )
        sub_category = click.prompt(
            "Sub category for this transaction",
            type=click.Choice(SUB_CATEGORY.get(main_category, []), case_sensitive=False)
        )
        store_issuer_classification = click.prompt("Store this classification for future use? (y/n)", default="n")

        if store_issuer_classification.lower() == 'y':
            classify_issuer(IssuerClassification(
                issuer=trans.issuer,
                main_category=main_category,
                sub_category=sub_category
            ))

        update_transaction(trans.id, main_category, sub_category)


@cli.command()
def unclassified_transactions():
    """Check for unclassified transactions."""
    unclassified_transactions = get_unclassified_transactions()
    if len(unclassified_transactions) == 0:
        click.echo('No unclassified transactions found.')
        return
    click.echo(f'Found {len(unclassified_transactions)} unclassified transactions.')


if __name__ == '__main__':
    create_tables()
    cli()