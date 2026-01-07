from datetime import datetime, timedelta
import calendar

def month_to_date(month: int = datetime.now().month, year: int = datetime.now().year) -> (tuple[datetime, datetime]):
    """Get start and end date for a given month and year."""

    start_date = datetime.strptime(f'{year}-{month:02d}-01', '%Y-%m-%d')
    if month == 12:
        end_date = datetime.strptime(f'{year + 1}-01-01', '%Y-%m-%d') - timedelta(days=1)
    else:
        end_date = datetime.strptime(f'{year}-{month + 1:02d}-01', '%Y-%m-%d') - timedelta(days=1)
    return start_date, end_date


def month_no_to_name(month_no: int) -> str:
    """Convert month number to month name."""
    if 1 <= month_no <= 12:
        return calendar.month_name[month_no]
    else:
        raise ValueError("Month number must be between 1 and 12.")