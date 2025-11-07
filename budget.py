from datetime import datetime, timedelta
from database import get_transactions


def get_monthly_budget(year):
    monthly_budget = {}



    for month in range(1, 12):
        start_date = f'{year}-{month:02d}-01'
        end_date = datetime.strftime(datetime(year, month + 1, 1) - timedelta(days=1), '%Y-%m-%d')
       
        summary = budget_summary(start_date, end_date)
        monthly_budget[month] = summary
    return monthly_budget

def budget_summary(start_date, end_date):
    transactions = get_transactions(start_date=start_date, end_date=end_date)
    if not transactions:
        return
    
    summary = {}
    for trans in transactions:
        main_cat = trans.main_category or 'Uncategorized'
        sub_cat = trans.sub_category or 'Uncategorized'

        if main_cat not in summary:
            summary[main_cat] = {'total': 0, 'sub_categories': {}}
        summary[main_cat]['total'] += trans.amount
        
        if sub_cat not in summary[main_cat]['sub_categories']:
            summary[main_cat]['sub_categories'][sub_cat] = 0
        summary[main_cat]['sub_categories'][sub_cat] += trans.amount

    return summary