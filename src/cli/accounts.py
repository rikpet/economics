import click

import database as db
import operations
from category_templates import TEMPLATES
from cli.context import AppContext, pass_app
from printout import generate_table


@click.command(name='list')
@pass_app
def list_accounts(app: AppContext):
    """List all accounts."""
    rows = [
        (a.id, a.name, 'yes' if a.derive_allowance else 'no',
         db.count_unclassified_transactions(app.database_path, a.id))
        for a in db.get_accounts(app.database_path)
    ]
    click.echo(generate_table(
        header=["ID", "NAME", "DERIVE ALLOWANCE", "UNCLASSIFIED"],
        rows=rows
    ))


@click.command(name='add')
@click.argument('name')
@click.option('--template', type=click.Choice(list(TEMPLATES)), default='empty',
              help="Category tree to start from.")
@click.option('--derive-allowance', is_flag=True,
              help="Calculate inkomst/månadspeng from the bokföring categories.")
@pass_app
def add_account(app: AppContext, name, template, derive_allowance):
    """Create a new account."""
    try:
        account_id = db.create_account(app.database_path, name, template, derive_allowance)
    except ValueError as e:
        raise click.ClickException(str(e))
    click.echo(f'Account {name!r} created with id {account_id}.')


@click.command(name='rename')
@click.argument('account')
@click.argument('new_name')
@pass_app
def rename_account(app: AppContext, account, new_name):
    """Rename ACCOUNT (name or id) to NEW_NAME."""
    found = db.find_account(app.database_path, account)
    if found is None:
        raise click.ClickException(f'Unknown account: {account!r}')
    try:
        db.update_account(app.database_path, found.id, name=new_name)
    except ValueError as e:
        raise click.ClickException(str(e))
    click.echo(f'Account {found.name!r} renamed to {new_name!r}.')


@click.command(name='remove')
@click.argument('account')
@click.confirmation_option(prompt='Delete the account with its categories and issuer rules?')
@pass_app
def remove_account(app: AppContext, account):
    """Delete ACCOUNT (name or id). Only possible when it has no transactions."""
    found = db.find_account(app.database_path, account)
    if found is None:
        raise click.ClickException(f'Unknown account: {account!r}')
    try:
        db.delete_account(app.database_path, found.id)
    except ValueError as e:
        raise click.ClickException(str(e))
    click.echo(f'Account {found.name!r} deleted.')


@click.command(name='list')
@pass_app
def list_categories(app: AppContext):
    """List the categories of the account."""
    budgets = db.get_budgets(app.database_path, app.account_id)
    rows = [
        (c.id, c.main_category, c.sub_category, c.kind,
         int(budgets[c.main_category]) if c.main_category in budgets else '')
        for c in db.get_categories(app.database_path, app.account_id)
    ]
    click.echo(f'Categories for {app.account.name}:\n')
    click.echo(generate_table(header=["ID", "MAIN CATEGORY", "SUB CATEGORY", "TYPE",
                                      "BUDGET/MONTH"], rows=rows))


@click.command(name='budget')
@click.argument('main_category')
@click.argument('amount', required=False)
@click.option('--clear', is_flag=True, help="Remove the budget.")
@pass_app
def set_budget(app: AppContext, main_category, amount, clear):
    """Set the monthly budget for MAIN_CATEGORY, or show it."""
    main_category = main_category.lower()
    if not any(c.main_category == main_category
               for c in db.get_categories(app.database_path, app.account_id)):
        raise click.ClickException(f'Unknown main category: {main_category}')
    if clear:
        db.set_budget(app.database_path, app.account_id, main_category, None)
        click.echo(f'Budget for {main_category} removed.')
        return
    if amount is None:
        current = db.get_budgets(app.database_path, app.account_id).get(main_category)
        click.echo(f'Budget for {main_category}: '
                   + (f'{current:.0f} a month' if current is not None else 'none'))
        return
    try:
        value = operations.parse_amount(amount)
        db.set_budget(app.database_path, app.account_id, main_category, value)
    except ValueError as e:
        raise click.ClickException(str(e))
    click.echo(f'Budget for {main_category} set to {value:.0f} a month.')


@click.command(name='add')
@click.argument('main_category')
@click.argument('sub_category')
@click.option('--income', is_flag=True, help="Positive amounts count as positive (default: expense).")
@pass_app
def add_category(app: AppContext, main_category, sub_category, income):
    """Add a category to the account."""
    try:
        db.add_category(app.database_path, app.account_id, main_category, sub_category,
                        invert_sign=not income)
    except ValueError as e:
        raise click.ClickException(str(e))
    click.echo(f'Category {main_category}/{sub_category} added.')


@click.command(name='remove')
@click.argument('category_id', type=int)
@pass_app
def remove_category(app: AppContext, category_id):
    """Remove a category by id. Its transactions are counted as uncategorized."""
    category = db.get_category(app.database_path, app.account_id, category_id)
    if category is None:
        raise click.ClickException(f'No category with id {category_id}.')
    used = db.category_usage(app.database_path, app.account_id, category.main_category,
                             category.sub_category)
    if used and not click.confirm(f'{used} transactions use this category. Remove anyway?'):
        return
    db.delete_category(app.database_path, app.account_id, category_id)
    click.echo(f'Category {category.main_category}/{category.sub_category} removed.')
