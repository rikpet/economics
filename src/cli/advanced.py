import click
from cli.context import AppContext, pass_app
import database as db
from parser import parse_original_issuers, parse_original_transactions


@click.command(name='query')
@click.argument('query_string')
@pass_app
def query_db(app: AppContext, query_string):
    results = db.query(app.database_path, query_string)
    for row in results:
        click.echo(row)


@click.command()
@click.argument('file_path')
@pass_app
def add_original_transactions(app: AppContext, file_path):
    """Adds original transactions to database
    
    Args:
        file_path (str): Path to the original transactions file.
    """
    click.echo(f'Processing file: {file_path}')
    transactions = parse_original_transactions(file_path)
    
    for trans in transactions:
        db.insert_transaction(app.database_path, app.account_id, trans)


@click.command()
@click.argument('file_path')
@pass_app
def add_original_issuers(app: AppContext, file_path):
    """Adds original issuer classifications to database
    
    Args:
        file_path (str): Path to the original issuers file.
    """
    click.echo(f'Processing issuers file: {file_path}')
    issuers = parse_original_issuers(file_path)
    
    for issuer in issuers:
        db.classify_issuer(app.database_path, app.account_id, issuer)

@click.command()
@pass_app
def run_db_schema(app: AppContext):
    """Create the database tables and apply schema migrations."""
    db.create_tables(app.database_path)


@click.command(name='backup')
@click.argument('destination')
@pass_app
def backup_db(app: AppContext, destination):
    """Write a copy of the database to DESTINATION."""
    db.backup_database(app.database_path, destination)
    click.echo(f'Database copied to {destination}')
