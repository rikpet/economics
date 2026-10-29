from datetime import datetime

import click

import database as db
from app_types import PersonMonth
from cli.context import AppContext, pass_app
from printout import generate_table
from transfers import parse_sum, transfer_year
from utils import month_no_to_name


def _person(app: AppContext, name: str):
    person = next((p for p in db.get_people(app.database_path, app.account_id)
                   if p.name.lower() == name.lower()), None)
    if person is None:
        raise click.ClickException(f"No person called {name} in {app.account.name}. "
                                   f"Add them on the Transfers page.")
    return person


@click.command(name='show')
@click.option('--year', type=int, default=None, help="Year (default: this year).")
@pass_app
def show_transfers(app: AppContext, year: int | None):
    """What each person transfers to the account per month: income − one-off costs − allowance."""
    year = year or datetime.now().year
    people = db.get_people(app.database_path, app.account_id)
    if not people:
        click.echo(f"No people in {app.account.name}. Add them on the Transfers page.")
        return
    months = transfer_year(app.database_path, app.account_id, year)
    rows = []
    for m in range(12):
        values = [months[p.id][m] for p in people]
        if not any(v.has_data for v in values):
            continue
        rows.append([month_no_to_name(m + 1)]
                    + [f"{v.to_account:.0f}" if v.has_data else "" for v in values]
                    + [f"{sum(v.to_account for v in values if v.has_data):.0f}"])
    click.echo(generate_table(header=["Month", *(p.name for p in people), "Together"], rows=rows))


@click.command(name='set')
@click.argument('person')
@click.argument('month', type=int)
@click.option('--year', type=int, default=None, help="Year (default: this year).")
@click.option('--income', default=None, help="Income, e.g. 40000 or 35000+5000.")
@click.option('--costs', default=None, help="One-off costs paid for the account, e.g. 700+500.")
@click.option('--allowance', default=None, help="Allowance from this month on.")
@pass_app
def set_transfer(app: AppContext, person: str, month: int, year: int | None,
                 income: str | None, costs: str | None, allowance: str | None):
    """Enter a person's figures for a month. Options left out keep their value; '' clears."""
    if not 1 <= month <= 12:
        raise click.ClickException("Month must be between 1 and 12.")
    year = year or datetime.now().year
    p = _person(app, person)
    current = next((m for m in db.get_person_months(app.database_path, app.account_id, year)
                    if m.person_id == p.id and m.year == year and m.month == month),
                   PersonMonth(p.id, year, month))
    try:
        if income is not None:
            current.income, current.income_input = parse_sum(income), income or None
        if costs is not None:
            current.costs, current.costs_input = parse_sum(costs), costs or None
        if allowance is not None:
            current.allowance = parse_sum(allowance)
    except ValueError as e:
        raise click.ClickException(str(e))
    db.set_person_month(app.database_path, app.account_id, current)
    t = transfer_year(app.database_path, app.account_id, year)[p.id][month - 1]
    click.echo(f"{p.name}, {month_no_to_name(month)} {year}: {t.income:.0f} − {t.costs:.0f} − "
               f"{t.allowance:.0f} = {t.to_account:.0f} to {app.account.name}")
