from datetime import datetime

import click

import database as db
from budget import completed_months, monthly_balances, split_acknowledged, zero_check_flags
from cli.context import AppContext, pass_app
from printout import generate_table
from utils import month_no_to_name


def _flags(app: AppContext, year: int):
    balances = monthly_balances(app.database_path, app.account, year)
    categories = db.get_categories(app.database_path, app.account_id)
    return split_acknowledged(zero_check_flags(balances, categories, completed_months(year)),
                              db.get_zero_check_acks(app.database_path, app.account_id, year))


def _parse(category: str, month: str) -> tuple[str, str, int, int]:
    main, _, sub = category.lower().partition('/')
    try:
        when = datetime.strptime(month, '%Y-%m')
    except ValueError:
        raise click.ClickException(f'Month must look like 2025-03, not {month!r}')
    if not sub:
        raise click.ClickException(f'Category must look like main/sub, not {category!r}')
    return main, sub, when.year, when.month


@click.command(name='list')
@click.option('--year', type=int, default=datetime.now().year, help="Year to check.")
@pass_app
def list_checks(app: AppContext, year):
    """List debt-check warnings (categories that should be 0 every month) and acknowledgements."""
    flags, acknowledged = _flags(app, year)
    rows = [(f'{f.main_category}/{f.sub_category}', f'{year}-{f.month:02d}', int(f.value),
             f'acknowledged {f.acknowledged_at}' if f.acknowledged_at else 'WARNING')
            for f in sorted(flags + acknowledged, key=lambda f: (f.month, f.label))]
    if not rows:
        click.echo(f'Everything that should be 0 is 0 in {year}.')
        return
    click.echo(generate_table(header=['CATEGORY', 'MONTH', 'AMOUNT', 'STATUS'], rows=rows))


@click.command(name='ack')
@click.argument('category')
@click.argument('month')
@pass_app
def acknowledge(app: AppContext, category, month):
    """Acknowledge that CATEGORY (main/sub) is not 0 in MONTH (YYYY-MM).

    The acknowledgement holds for the current amount; if it changes, the warning is back.
    """
    main, sub, year, month_no = _parse(category, month)
    flags, _ = _flags(app, year)
    flag = next((f for f in flags if (f.main_category, f.sub_category, f.month) ==
                 (main, sub, month_no)), None)
    if flag is None:
        raise click.ClickException(f'No open warning for {main}/{sub} in {month}.')
    db.acknowledge_zero_check(app.database_path, app.account_id, main, sub, year, month_no,
                              flag.value)
    click.echo(f'Acknowledged: {main}/{sub} is {int(flag.value)} in '
               f'{month_no_to_name(month_no)} {year}.')


@click.command(name='undo')
@click.argument('category')
@click.argument('month')
@pass_app
def unacknowledge(app: AppContext, category, month):
    """Make an acknowledged warning a warning again."""
    main, sub, year, month_no = _parse(category, month)
    db.unacknowledge_zero_check(app.database_path, app.account_id, main, sub, year, month_no)
    click.echo(f'{main}/{sub} in {month_no_to_name(month_no)} {year} is a warning again.')
