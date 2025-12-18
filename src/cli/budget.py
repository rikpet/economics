import calendar
from datetime import datetime
import click
from tabulate import tabulate

from app_types import ReadTransaction
from balance import Balance
from constants import DATABASE_PATH
from database import get_transactions

@click.command()
@click.option('--show-sub-category', is_flag=True, help='Show sub-category breakdown.')
@click.option('--year', type=int, default=datetime.now().year, help="Year for the budget summary.")
def budget(show_sub_category, year):
    """Show budget summary."""

    monthly_balances: dict[int, Balance] = {}
    for month in range(1, 13):
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
        "bokföring",
        "familjeutlägg"
    )
    monthly_balances[1].set_dept(sum(t.amount for t in dept_transactions))
    for month in range(2, 13):
        monthly_balances[month].set_dept(monthly_balances[month - 1].get_sub_category("bokföring", "familjeutlägg"))

    months: list[str] = [str(calendar.month_name[m]) for m in monthly_balances.keys()]

    table_data: list[list[str]] = []
    cat = monthly_balances[1].categories()
    for c in cat:
        table_data.append([c.capitalize()])
        if show_sub_category:
            for sc in monthly_balances[1].sub_categories(c):
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



def get_monthly_budget(transactions: list[ReadTransaction]) -> dict[int, Balance]:
    monthly_balances: dict[int, Balance] = {}

    year = datetime.now().year

    for month in range(1, 13):
        monthly_balances[month] = Balance(year, month)
        monthly_balances[month].add_several([t for t in transactions if datetime.strptime(t.date, '%Y-%m-%d').month == month and datetime.strptime(t.date, '%Y-%m-%d').year == year])

    return monthly_balances