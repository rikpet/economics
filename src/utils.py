from datetime import datetime, timedelta
import calendar

def month_to_date(month: int | None = None, year: int | None = None) -> (tuple[datetime, datetime]):
    """Get start and end date for a given month and year."""

    if year is None and month is None:  # Both year and month are None, use previous month of current year
        year = datetime.now().year
        month = datetime.now().month - 1
        if month == 0:
            month = 12
            year -= 1

    elif month is None and year is not None:  # Only month is None, use previous month of given year
        raise ValueError("Month must be provided if year is provided.")

    elif month is not None and year is None:  # Only year is None, use current year
        if month > datetime.now().month:
            year = datetime.now().year - 1
        else:
            year = datetime.now().year

    else:  # Both month and year are provided
        pass

    if year is None or month is None:
        # This is more for type checking purposes; the above logic should ensure both are set
        raise ValueError("Year and month must be determined.")

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