from datetime import datetime
import click

import database as db
from cli.context import AppContext, pass_app
from printout import generate_table
from utils import month_no_to_name

def check_allowance(app: AppContext):
    """Make sure the allowance for the current month exists, using the account's defaults.

    Accounts without default allowances are left alone.
    """
    rikard_default = db.get_setting(app.database_path, app.account_id, 'rikard_allowance')
    sara_default = db.get_setting(app.database_path, app.account_id, 'sara_allowance')
    if rikard_default is None and sara_default is None:
        return

    now = datetime.now()
    db.set_allowance(
        app.database_path, app.account_id, now.year, now.month,
        float(rikard_default or 0), float(sara_default or 0),
        only_if_missing=True
    )


@click.command(name='add')
@click.argument('amount', type=float)
@click.option('--month', type=int, required=True, default=None, help="Month to set the allowance for (default: current month)")
@click.option('--year', type=int, default=None, help="Year to set the allowance for (default: current year)")
@click.option('--rikard', is_flag=True, help="Set the allowance for Rikard")
@click.option('--sara', is_flag=True, help="Set the allowance for Sara")
@pass_app
def add_allowance(app: AppContext, amount: float, month: int, year: int | None, rikard: bool, sara: bool):
    """Set the allowance for a specific month and year."""
    if month is None:
        raise click.ClickException("Month must be specified when adding an allowance.")
    
    if month < 1 or month > 12:
        raise click.ClickException("Month must be between 1 and 12.")

    if year is not None and (year < 2020 or year > datetime.now().year):
        raise click.ClickException("Year must be between 2020 and this year.") 

    year = year if year is not None else datetime.now().year

    if not rikard and not sara:
        rikard = sara = True  # If neither is specified, set both

    db.set_allowance(app.database_path, app.account_id, year, month,
                     amount if rikard else None, amount if sara else None)


@click.command(name='update')
@click.argument('month', type=int)
@click.argument('amount', type=float)
@click.option('--year', type=int, default=None, help="Year for the allowance (default: current year)")
@click.option('--rikard', is_flag=True, help="Set the allowance for Rikard")
@click.option('--sara', is_flag=True, help="Set the allowance for Sara")
@pass_app
def update_allowance(app: AppContext, month: int, amount: float, year: int | None, rikard: bool, sara: bool):
    """Set the allowance for a specific month and year."""
    year = year if year is not None else datetime.now().year

    if not rikard and not sara:
        rikard = sara = True  # If neither is specified, update both

    db.set_allowance(app.database_path, app.account_id, year, month,
                     amount if rikard else None, amount if sara else None)


@click.command(name='list')
@click.option('--month', type=int, default=None, help="Month to list the allowance for (default: current month)")
@click.option('--year', type=int, default=None, help="Year to list the allowance for (default: current year)")
@pass_app
def list_allowance(app: AppContext, month: int | None, year: int | None):
    """List the allowance for the current month and year."""
    year = year if year is not None else datetime.now().year

    rows = db.get_allowances(app.database_path, app.account_id, year, month)

    if not rows:
        click.echo("No allowances found for the specified period.")
        return

    r = []
    for row in rows:
        r.append([
            f"{month_no_to_name(row['month'])}",
            f"{row['year']:d}",
            f"{row['rikard_allowance']:.2f}",
            f"{row['sara_allowance']:.2f}"
        ])

    click.echo(generate_table(
        header=["Month", "Year", "Rikard Allowance", "Sara Allowance"],
        rows=r
    ))


@click.command(name='default')
@click.argument('amount', type=float)
@click.option('--rikard', is_flag=True, help="Set the default allowance for Rikard")
@click.option('--sara', is_flag=True, help="Set the default allowance for Sara")
@pass_app
def set_default_allowance(app: AppContext, amount: float, rikard: bool, sara: bool):
    """Set the default allowance amount."""
    if rikard:
        db.set_setting(app.database_path, app.account_id, 'rikard_allowance', str(amount))
    if sara:
        db.set_setting(app.database_path, app.account_id, 'sara_allowance', str(amount))
