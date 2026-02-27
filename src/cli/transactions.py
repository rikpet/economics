from datetime import datetime, timedelta
import click
import questionary

from app_types import IssuerClassification
from balance import Balance
from constants import DATABASE_PATH
import calendar

import database as db
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
        issuer = db.get_issuer_classification(DATABASE_PATH, trans.issuer)
        
        trans.main_category = issuer.main_category if issuer is not None else None
        trans.sub_category = issuer.sub_category if issuer is not None else None

        db.insert_transaction(DATABASE_PATH, trans)

#TODO: add check on category and sub-category
@click.command(name='list')
@click.option('--start-date', type=click.DateTime(formats=["%Y-%m-%d"]), default=None, help="Start date (YYYY-MM-DD)")
@click.option('--end-date', type=click.DateTime(formats=["%Y-%m-%d"]), default=None, help="End date (YYYY-MM-DD)")
@click.option('--month', type=int, default=None, help="Month (1-12)")
@click.option('--year', type=int, default=None, help="Year (e.g., 2023)")
@click.option('--category', type=str, default=None, multiple=True, help="Filter by main category")
@click.option('--sub-category', type=str, default=None, multiple=True, help="Filter by sub-category")
@click.option('--sum', 'show_sum', is_flag=True, help="Show sum of transaction amounts")
def list_transactions(start_date, end_date, month, year, category: tuple[str], sub_category: tuple[str], show_sum: bool):
    """List all transactions in the database, optionally filtered by date range."""
        
    year = datetime.now().year if year is None else year
    if month:
        start_date = datetime(year, month, 1)
        days_in_month = calendar.monthrange(year, month)[1]
        end_date = start_date + timedelta(days=days_in_month - 1)

    transactions = db.get_transactions(DATABASE_PATH,start_date=start_date, end_date=end_date, main_category=list(category), sub_category=list(sub_category))

    if len(transactions) == 0:
        click.echo('No transactions found.')
        return
    
    max_issuer_length = max(len(t.issuer) for t in transactions)

    click.echo('Listing transactions:\n')
    click.echo(f'{"ID":<5} | {"ISSUER":<{max_issuer_length + 3}} | {"AMOUNT":<10} | {"DATE":<10} | {"MAIN CATEGORY":<15} | {"SUB CATEGORY":<15}')
    click.echo('-' * (5 + 3 + max_issuer_length + 3 + 10 + 3 + 3 + 10 + 3 + 15 + 3 + 15))
    
    for trans in transactions:
        click.echo(f'{trans.id:<5} | {trans.issuer:<{max_issuer_length + 3}} | {trans.amount:>10.2f} | {trans.date:<10} | {trans.main_category if trans.main_category is not None else "":<15} | {trans.sub_category if trans.sub_category is not None else "":<15}')

    if show_sum:
        total_amount = sum(t.amount for t in transactions)
        click.echo(f'\nTotal amount: {total_amount:.2f}')

@click.command(name='modify')
@click.argument('transaction_id', type=int)
@click.option('--main-category', type=str, default=None, help="New main category")
@click.option('--sub-category', type=str, default=None, help="New sub-category")
@click.option('--date', type=click.DateTime(formats=["%Y-%m-%d"]), default=None, help="New date (YYYY-MM-DD)")
def modify_transaction(transaction_id, main_category, sub_category, date):
    """Modify an existing transaction."""
    if main_category is None and sub_category is None and date is None:
        click.echo('No modifications specified. Use --main-category, --sub-category, or --date to specify modifications.')
        return
    db.update_transaction(DATABASE_PATH, transaction_id, main_category, sub_category, date)


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
        click.echo(f'\n\nTransaction: {trans.issuer} | {trans.amount} | {trans.date}' )

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

        db.update_transaction(DATABASE_PATH, trans.id, main_category, sub_category)


@click.command(name='unclassified')
def unclassified_transactions():
    """Check for unclassified transactions."""
    unclassified_transactions = db.get_unclassified_transactions(DATABASE_PATH)
    if len(unclassified_transactions) == 0:
        click.echo('No unclassified transactions found.')
        return
    click.echo(f'Found {len(unclassified_transactions)} unclassified transactions.')

