from datetime import datetime

import click

import database as db
from app_types import Account, PersonMonth
from cli.context import AppContext, pass_app
from printout import generate_table
from transfers import ALLOWANCE_SETTING, parse_sum, transfer_year
from utils import month_no_to_name


def _joint(app: AppContext) -> Account:
    """The account with the allowance calculation (Familj), whichever account is selected."""
    accounts = db.get_accounts(app.database_path)
    joint = (next((a for a in accounts if db.get_people(app.database_path, a.id)), None)
             or next((a for a in accounts if not a.derive_allowance), None))
    if joint is None:
        raise click.ClickException("There is no joint account.")
    return joint


def _person(app: AppContext, account: Account, name: str):
    person = next((p for p in db.get_people(app.database_path, account.id)
                   if p.name.lower() == name.lower()), None)
    if person is None:
        raise click.ClickException(f"No person called {name} in {account.name}. "
                                   f"Add them on the Allowance page.")
    return person


def _amount(text: str | None) -> float | None:
    try:
        return parse_sum(text)
    except ValueError as e:
        raise click.ClickException(str(e))


@click.command(name='show')
@click.option('--year', type=int, default=None, help="Year (default: this year).")
@pass_app
def show_transfers(app: AppContext, year: int | None):
    """What each person transfers to the joint account per month:
    income − shared expenses − allowance."""
    year = year or datetime.now().year
    joint = _joint(app)
    people = db.get_people(app.database_path, joint.id)
    if not people:
        click.echo(f"No people in {joint.name}. Add them on the Allowance page.")
        return
    months = transfer_year(app.database_path, joint.id, year)
    rows = []
    for m in range(12):
        values = [months[p.id][m] for p in people]
        if not any(v.has_data for v in values):
            continue
        rows.append([month_no_to_name(m + 1), f"{values[0].allowance:.0f}"]
                    + [f"{v.to_account:.0f}" if v.has_data else "" for v in values]
                    + [f"{sum(v.to_account for v in values if v.has_data):.0f}"])
    click.echo(generate_table(header=["Month", "Allowance", *(p.name for p in people), "Together"],
                              rows=rows))


@click.command(name='set')
@click.argument('person')
@click.argument('month', type=int)
@click.option('--year', type=int, default=None, help="Year (default: this year).")
@click.option('--income', default=None, help="Income, e.g. 40000 or 35000+5000.")
@click.option('--costs', default=None, help="Shared expenses paid privately, e.g. 700+500.")
@pass_app
def set_transfer(app: AppContext, person: str, month: int, year: int | None,
                 income: str | None, costs: str | None):
    """Enter a person's income and shared expenses for a month. Options left out keep their
    value; '' clears."""
    if not 1 <= month <= 12:
        raise click.ClickException("Month must be between 1 and 12.")
    year = year or datetime.now().year
    joint = _joint(app)
    p = _person(app, joint, person)
    current = next((m for m in db.get_person_months(app.database_path, joint.id, year)
                    if m.person_id == p.id and m.month == month),
                   PersonMonth(p.id, year, month))
    if income is not None:
        current.income, current.income_input = _amount(income), income or None
    if costs is not None:
        current.costs, current.costs_input = _amount(costs), costs or None
    db.set_person_month(app.database_path, joint.id, current)
    t = transfer_year(app.database_path, joint.id, year)[p.id][month - 1]
    click.echo(f"{p.name}, {month_no_to_name(month)} {year}: {t.income:.0f} − {t.costs:.0f} − "
               f"{t.allowance:.0f} = {t.to_account:.0f} to {joint.name}")


@click.command(name='allowance')
@click.argument('amount')
@click.option('--month', type=int, default=None, help="Month to set it for.")
@click.option('--year', type=int, default=None, help="Year (default: this year).")
@click.option('--default', 'is_default', is_flag=True,
              help="Set the default for months without their own allowance.")
@pass_app
def set_allowance(app: AppContext, amount: str, month: int | None, year: int | None,
                  is_default: bool):
    """Set the allowance each person keeps: for one month (--month, '' for the default) or
    the default (--default)."""
    joint = _joint(app)
    if is_default == (month is not None):
        raise click.ClickException("Give either --month or --default.")
    value = _amount(amount)
    if is_default:
        if value is None:
            raise click.ClickException("Give an amount for the default.")
        db.set_setting(app.database_path, joint.id, ALLOWANCE_SETTING, str(value))
        click.echo(f"Default allowance: {value:.0f}")
        return
    if not 1 <= month <= 12:
        raise click.ClickException("Month must be between 1 and 12.")
    year = year or datetime.now().year
    db.set_allowance_month(app.database_path, joint.id, year, month, value)
    click.echo(f"Allowance for {month_no_to_name(month)} {year}: "
               + (f"{value:.0f}" if value is not None else "the default"))
