import click
from constants import DATABASE_PATH
import database as db
from parser import parse_original_issuers, parse_original_transactions


@click.command(name='query')
@click.argument('query_string')
def query_db(query_string):
    results = db.query(DATABASE_PATH, query_string)
    for row in results:
        click.echo(row)


@click.command()
@click.argument('file_path')
def add_original_transactions(file_path):
    """Adds original transactions to database
    
    Args:
        file_path (str): Path to the original transactions file.
    """
    click.echo(f'Processing file: {file_path}')
    transactions = parse_original_transactions(file_path)
    
    for trans in transactions:
        db.insert_transaction(DATABASE_PATH, trans)


@click.command()
@click.argument('file_path')
def add_original_issuers(file_path):
    """Adds original issuer classifications to database
    
    Args:
        file_path (str): Path to the original issuers file.
    """
    click.echo(f'Processing issuers file: {file_path}')
    issuers = parse_original_issuers(file_path)
    
    for issuer in issuers:
        db.classify_issuer(DATABASE_PATH, issuer)

@click.command()
def run_db_schema():
    """Run the database schema SQL script to create tables."""
    db.create_tables(DATABASE_PATH)
