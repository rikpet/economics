from datetime import datetime
import click

from dataclasses import replace

from budget import (
    budget_checks,
    budget_table,
    completed_months,
    hidden_categories,
    monthly_balances,
    split_acknowledged,
    summary_rows,
    zero_check_flags,
)
from cli.context import AppContext, pass_app
from database import get_budgets, get_categories, get_transactions, get_zero_check_acks
from printout import generate_table
from utils import month_no_to_name, month_to_date

@click.command()
@click.option('--show-sub-category', is_flag=True, help='Show sub-category breakdown.')
@click.option('--year', type=int, default=datetime.now().year, help="Year for the budget summary.")
@click.option('--month', type=int, default=None, help="Month for the budget summary.")
@click.option('--category', default=None, multiple=True, help="Category for the budget summary.")
@click.option('--all', 'show_all', is_flag=True, help="Include categories hidden from the budget.")
@pass_app
def balance(app: AppContext, show_sub_category, year, month, category: tuple[str], show_all: bool):
    """Show budget summary."""

    balances = monthly_balances(app.database_path, app.account, year,
                                [month] if month is not None else None)

    categories = get_categories(app.database_path, app.account_id)
    if show_all:
        categories = [replace(c, hidden=False) for c in categories]
    try:
        rows = budget_table(balances, show_sub_category, list(category) or None,
                            hidden_categories(categories))
    except ValueError as e:
        raise click.ClickException(str(e))

    budgets = get_budgets(app.database_path, app.account_id)
    checks = budget_checks(rows, budgets, categories, year, list(balances))

    def cell(value: float, red: bool) -> str:
        # Red when over budget; click drops the color when the output isn't a terminal.
        return click.style(str(int(value)), fg='red', bold=True) if red else str(int(value))

    table_data = []
    for r in rows:
        check = None if r.is_sub else checks.get(r.main_category)
        line = [f'  - {r.label}' if r.is_sub else r.label]
        if budgets:
            line.append(str(int(check.budget)) if check else '')
        line += [cell(v, bool(check) and m in check.red_months)
                 for m, v in zip(balances, r.values)]
        table_data.append(line)
    if not category:
        blank = [''] if budgets else []
        table_data.append([''] * (len(balances) + 1 + len(blank)))
        table_data += [[s.label] + blank + [str(int(v)) for v in s.values]
                       for s in summary_rows(balances, categories)]

    click.echo(f'BUDGET SUMMARY ({app.account.name}):\n')
    click.echo(generate_table(
        header=['Category'] + (['Budget'] if budgets else []) + [month_no_to_name(m) for m in balances],
        rows=table_data
    ))

    flags, acknowledged = split_acknowledged(
        zero_check_flags(balances, categories, completed_months(year)),
        get_zero_check_acks(app.database_path, app.account_id, year))
    for flag in flags:
        click.echo(f'WARNING: {flag.main_category}/{flag.sub_category} is {int(flag.value)}, '
                   f'not 0, in {month_no_to_name(flag.month)}')
    if acknowledged:
        click.echo(f'({len(acknowledged)} acknowledged; see econ check list)')


@click.command()
@click.option('--month', type=int, default=None, help="Month for when to accumulated dept (default: previous month).")
@pass_app
def dept(app: AppContext, month):
    """Show accumulated dept up to a specific month."""

    start_date, end_date = month_to_date(month)
    month = start_date.month

    trans = get_transactions(app.database_path, app.account_id, start_date, end_date, ["bokföring"], ["familjeutlägg"])

    total_dept = sum(t.amount for t in trans)
    click.echo(f'Accumulated dept for {month_no_to_name(month)}: {total_dept}')
