import os
import click

from constants import DATABASE_PATH

from parser import parse_original_issuers, parse_original_transactions
from database import *

from cli.transactions import add_transactions, list_transactions, classify_transactions
from cli.issuer import list_issuers, add_issuer
from cli.budget import budget

@click.group()
def cli():
    pass

cli.add_command(budget)


@cli.group()
def trans():
    """Transaction related commands."""
    pass

trans.add_command(add_transactions)
trans.add_command(list_transactions)
trans.add_command(classify_transactions)


@cli.group()
def issuer():
    """Issuer classification related commands."""
    pass

issuer.add_command(list_issuers)
issuer.add_command(add_issuer)


@cli.command()
def unclassified_transactions():
    """Check for unclassified transactions."""
    unclassified_transactions = get_unclassified_transactions()
    if len(unclassified_transactions) == 0:
        click.echo('No unclassified transactions found.')
        return
    click.echo(f'Found {len(unclassified_transactions)} unclassified transactions.')


# -------------------------------------------------------------------
# Advanced COMMAND GROUP
# -------------------------------------------------------------------

@cli.group()
def advanced():
    """Advanced database commands."""
    pass

@advanced.command(name='query')
@click.argument('query_string')
def query_db(query_string):
    results = query(DATABASE_PATH, query_string)
    for row in results:
        click.echo(row)

@cli.command()
@click.argument('file_path')
def add_original_transactions(file_path):
    """Adds original transactions to database
    
    Args:
        file_path (str): Path to the original transactions file.
    """
    click.echo(f'Processing file: {file_path}')
    transactions = parse_original_transactions(file_path)
    
    for trans in transactions:
        insert_transaction(DATABASE_PATH, trans)

@advanced.command()
@click.argument('file_path')
def add_original_issuers(file_path):
    """Adds original issuer classifications to database
    
    Args:
        file_path (str): Path to the original issuers file.
    """
    click.echo(f'Processing issuers file: {file_path}')
    issuers = parse_original_issuers(file_path)
    
    for issuer in issuers:
        classify_issuer(DATABASE_PATH, issuer)


def main():
    if not os.path.exists(DATABASE_PATH):
        create_tables(DATABASE_PATH)
    cli()

if __name__ == '__main__':
    budget()