import calendar
from datetime import datetime
import click
from tabulate import tabulate

from balance import Balance
from constants import DATABASE_PATH
from database import get_transactions
from utils import month_no_to_name, month_to_date

@click.command()
@click.option('--show-sub-category', is_flag=True, help='Show sub-category breakdown.')
@click.option('--year', type=int, default=datetime.now().year, help="Year for the budget summary.")
@click.option('--month', type=int, default=None, help="Month for the budget summary.")
@click.option('--category', default=None, multiple=True, help="Category for the budget summary.")
def balance(show_sub_category, year, month, category: tuple[str]):
    """Show budget summary."""

    monthly_balances: dict[int, Balance] = {}
    if month is None:
        months_range = range(1, 13)
    else:
        months_range = [month]

    for month in months_range:
        monthly_balances[month] = Balance(year, month)
        monthly_balances[month].add_several(
            get_transactions(
                DATABASE_PATH,
                datetime.strptime(f'{year}-{month:02d}-01', '%Y-%m-%d'),
                datetime.strptime(f'{year}-{month:02d}-{calendar.monthrange(year, month)[1]}', '%Y-%m-%d')
            )
        )

    dept_transactions = get_transactions(
        DATABASE_PATH,
        datetime.strptime(f'{year - 1}-12-01', '%Y-%m-%d'),
        datetime.strptime(f'{year - 1}-12-31', '%Y-%m-%d'),
        ["bokföring"],
        ["familjeutlägg"]
    )
    monthly_balances[months_range[0]].set_dept(sum(t.amount for t in dept_transactions))
    for month in months_range[1:]:
        monthly_balances[month].set_dept(monthly_balances[month - 1].get_sub_category("bokföring", "familjeutlägg"))

    months: list[str] = [month_no_to_name(m) for m in monthly_balances.keys()]
    
    table_data: list[list[str]] = []

    if category:
          cat = list(category)
    else:
          cat = monthly_balances[months_range[0]].categories()

    for c in cat:
        table_data.append([c.capitalize()])
        if show_sub_category:
            for sc in monthly_balances[months_range[0]].sub_categories(c):
                table_data.append([f'  - {sc.capitalize()}'])

    current_cat = ''
    for c in table_data:
        category_name = c[0]
        if not category_name.startswith('  - '):
            current_cat = category_name

        for b in monthly_balances.values():
            if category_name.startswith('  - '):
                c.append(str(int(b.get_sub_category(current_cat, category_name.strip("  - ")))))
            else:
                c.append(str(int(b.get(category_name))))

    click.echo('BUDGET SUMMARY:\n')
    click.echo(tabulate(table_data, headers=['Category'] + months))


@click.command()
@click.option('--month', type=int, default=datetime.now().month - 1, help="Month for when to accumulated dept.")
def dept(month):
    """Show accumulated dept up to a specific month."""

    start_date, end_date = month_to_date(month)

    trans = get_transactions(DATABASE_PATH, start_date, end_date, ["bokföring"], ["familjeutlägg"])

    total_dept = sum(t.amount for t in trans)
    click.echo(f'Accumulated dept for {month_no_to_name(month)}: {total_dept}')