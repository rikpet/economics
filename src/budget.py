from datetime import datetime, timedelta
from database import get_transactions
from categories import CATEGORIES


def get_monthly_budget(transactions):
    monthly_budget = {}

    year = datetime.now().year

    for month in range(1, 13):   
        month_transactions = [t for t in transactions if datetime.strptime(t.date, '%Y-%m-%d').month == month and datetime.strptime(t.date, '%Y-%m-%d').year == year]
       
        if len(month_transactions) == 0:
            continue

        monthly_budget[month] = budget_summary(month_transactions)
    return monthly_budget

def budget_summary(transactions):    
    summary = create_budget_template()
    for trans in transactions:
        main_cat = trans.main_category.lower() or 'uncategorized'
        sub_cat = trans.sub_category.lower() or 'uncategorized'

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