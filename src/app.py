import os
import click


from constants import DATABASE_PATH


from cli.transactions import (
    add_transactions,
    list_transactions,
    modify_transaction,
    classify_transactions,
    unclassified_transactions
)

from cli.issuer import (
    list_issuers,
    add_issuer,
    remove_issuer,
    modify_issuer
)

from cli.balance import balance, dept

from cli.advanced import (
    add_original_issuers,
    add_original_transactions,
    query_db
)
from database import create_tables

@click.group()
def cli():
    pass

cli.add_command(balance)
cli.add_command(dept)


@cli.group()
def trans():
    """Transaction related commands."""
    pass

trans.add_command(add_transactions)
trans.add_command(list_transactions)
trans.add_command(modify_transaction)
trans.add_command(classify_transactions)
trans.add_command(unclassified_transactions)


@cli.group()
def issuer():
    """Issuer classification related commands."""
    pass

issuer.add_command(list_issuers)
issuer.add_command(add_issuer)
issuer.add_command(modify_issuer)
issuer.add_command(remove_issuer)

@cli.group()
def advanced():
    """Advanced database commands."""
    pass

advanced.add_command(query_db)
advanced.add_command(add_original_transactions)
advanced.add_command(add_original_issuers)


def main():
    if not os.path.exists(DATABASE_PATH):
        create_tables(DATABASE_PATH)
    cli()