import click

from cli.accounts import (
    add_account,
    add_category,
    list_accounts,
    set_budget,
    list_categories,
    remove_account,
    remove_category,
    rename_account
)
from cli.allowance import add_allowance, check_allowance, list_allowance, set_default_allowance, update_allowance
from cli.context import AppContext
from constants import DATABASE_PATH, DEFAULT_ACCOUNT


from cli.transactions import (
    add_transactions,
    list_transactions,
    modify_transaction,
    classify_transactions,
    split_transaction,
    unclassified_transactions,
    unsplit_transaction
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
    backup_db,
    query_db,
    run_db_schema
)
from cli.checks import acknowledge, list_checks, unacknowledge
from cli.web import web
from database import create_tables

@click.group()
@click.option('--account', '-a', default=DEFAULT_ACCOUNT,
              help="Account name or id to work on (default: $ECONOMICS_ACCOUNT or the first account).")
@click.option('--db', 'database_path', default=DATABASE_PATH, show_default=True,
              help="Path to the database (default: $ECONOMICS_DB).")
@click.pass_context
def cli(ctx: click.Context, account: str, database_path: str):
    # create_tables is idempotent and applies schema migrations to existing databases,
    # so run it on every startup.
    create_tables(database_path)
    ctx.obj = AppContext(database_path, account)

    if ctx.invoked_subcommand not in ('account', 'web'):
        check_allowance(ctx.obj)

cli.add_command(balance)
cli.add_command(dept)
cli.add_command(web)


@cli.group()
def account():
    """Account related commands."""
    pass

account.add_command(list_accounts)
account.add_command(add_account)
account.add_command(rename_account)
account.add_command(remove_account)


@cli.group()
def category():
    """Category related commands for the selected account."""
    pass

category.add_command(list_categories)
category.add_command(add_category)
category.add_command(remove_category)
category.add_command(set_budget)


@cli.group()
def check():
    """Debt-check warnings: categories that should be 0 every month."""
    pass

check.add_command(list_checks)
check.add_command(acknowledge)
check.add_command(unacknowledge)


@cli.group()
def trans():
    """Transaction related commands."""
    pass

trans.add_command(add_transactions)
trans.add_command(list_transactions)
trans.add_command(modify_transaction)
trans.add_command(classify_transactions)
trans.add_command(unclassified_transactions)
trans.add_command(split_transaction)
trans.add_command(unsplit_transaction)


@cli.group()
def issuer():
    """Issuer classification related commands."""
    pass

issuer.add_command(list_issuers)
issuer.add_command(add_issuer)
issuer.add_command(modify_issuer)
issuer.add_command(remove_issuer)

@cli.group()
def allowance():
    """Allowance related commands."""
    pass

allowance.add_command(add_allowance)
allowance.add_command(list_allowance)
allowance.add_command(update_allowance)
allowance.add_command(set_default_allowance)


@cli.group()
def advanced():
    """Advanced database commands."""
    pass

advanced.add_command(query_db)
advanced.add_command(add_original_transactions)
advanced.add_command(add_original_issuers)
advanced.add_command(run_db_schema)
advanced.add_command(backup_db)


def main():
    cli()
