import calendar
from datetime import datetime
import click
from tabulate import tabulate
from dataclasses import dataclass, make_dataclass

from app_types import ReadTransaction
from categories import CATEGORIES
from constants import DATABASE_PATH
from database import get_transactions

@click.command()
@click.option('--show-sub-category', is_flag=True, help='Show sub-category breakdown.')
@click.option('--year', type=int, default=datetime.now().year, help="Year for the budget summary.")
def budget(show_sub_category, year):
    """Show budget summary."""
    show_sub_category = False

    transactions = get_transactions(DATABASE_PATH, datetime.strptime(f'{year}-01-01', '%Y-%m-%d'), datetime.strptime(f'{year}-12-31', '%Y-%m-%d'))

    summary = get_monthly_budget(transactions)

    months: list[str] = [str(calendar.month_name[m]) for m in summary.keys()]

    table_data = [[c.capitalize()] for c in next(iter(summary.values())).keys()]
    for _, monthly_data in summary.items():
        for main_cat, main_cat_data in monthly_data.items():
            for i in table_data:
                if i[0].lower() == main_cat:
                    i.append(main_cat_data['total'])
                    break

    click.echo('BUDGET SUMMARY:\n')
    click.echo(tabulate(table_data, headers=['Category'] + months, floatfmt=".2f"))



def get_monthly_budget(transactions: list[ReadTransaction]):
    monthly_budget = {}

    year = datetime.now().year

    for month in range(1, 13):   
        month_transactions = [t for t in transactions if datetime.strptime(t.date, '%Y-%m-%d').month == month and datetime.strptime(t.date, '%Y-%m-%d').year == year]
       
        if len(month_transactions) == 0:
            continue

        monthly_budget[month] = calculate_budget(month_transactions)

    # Calculating special categories
    for month, budget in monthly_budget.items():
        income = budget['bokföring']['sub_categories']['inkomst']['total']
        transferred = budget['bokföring']['sub_categories']['familjekonto']['total']

        if month == 1:
            trans = get_transactions(DATABASE_PATH, datetime(year -1, 12, 1), datetime(year -1, 12, 31), 'bokföring', 'familjeutlägg')
            dept = sum(t.amount for t in trans)
        else:
            dept = monthly_budget[month -1]['bokföring']['sub_categories']['familjeutlägg']['total']

        budget['inkomst']['sub_categories']['månadspeng']['total'] = income - abs(transferred) - abs(dept)
        budget['inkomst']['total'] = budget['inkomst']['sub_categories']['månadspeng']['total'] + budget['inkomst']['sub_categories']['ränta']['total'] + budget['inkomst']['sub_categories']['övrigt']['total']


    return monthly_budget


def calculate_budget(transactions: list[ReadTransaction]):    
    summary = create_budget_template()
    for trans in transactions:
        main_cat = trans.main_category.lower() if trans.main_category else 'uncategorized'
        sub_cat = trans.sub_category.lower() if trans.sub_category else 'uncategorized'

        summary[main_cat]['total'] += trans.amount
        summary[main_cat]['sub_categories'][sub_cat]['total'] += trans.amount

    return summary


def create_budget_template():

    template = {}
    for main_cat in CATEGORIES.keys():
        template[main_cat] = {
            'total': 0,
            'sub_categories': {sub_cat: {'total': 0} for sub_cat in CATEGORIES[main_cat]}
        }

    return template


@dataclass
class MainCategories:
    bokgöring: dict
    inkomst: dict
    övrigt: dict