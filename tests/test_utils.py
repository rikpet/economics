import pytest
from datetime import datetime, timedelta
from src.utils import month_to_date, month_no_to_name

@pytest.mark.parametrize(
    "month, year, expected",
    [
        (1, 2023, (datetime(2023, 1, 1), datetime(2023, 1, 31))),
        (2, 2024, (datetime(2024, 2, 1), datetime(2024, 2, 29))),  # Leap year
        (3, 2023, (datetime(2023, 3, 1), datetime(2023, 3, 31))),
        (12, 2025, (datetime(2025, 12, 1), datetime(2025, 12, 31))),
        (1, 2025, (datetime(2025, 1, 1), datetime(2025, 1, 31))),
        (None, 202)
    ]
)
def test_month_to_date_default(month, year, expected):
    # Should return previous month of current year
    now = datetime.now()
    prev_month = now.month - 1 if now.month > 1 else 12
    prev_year = now.year if now.month > 1 else now.year - 1
    start, end = month_to_date()
    assert start.month == prev_month
    assert start.year == prev_year
    assert start.day == 1
    assert end.month == prev_month
    assert end.year == prev_year
    # End day should be last day of the month
    if prev_month == 12:
        assert end.day == 31
    else:
        # For non-December, check last day
        next_month_start = datetime(prev_year, prev_month % 12 + 1, 1)
        assert (end + timedelta(days=1)).date() == next_month_start.date()

def test_month_to_date_only_year():
    now = datetime.now()
    prev_month = now.month - 1 if now.month > 1 else 12
    prev_year = 2020 if now.month > 1 else 2019
    start, end = month_to_date(year=2020)
    assert start.month == prev_month
    assert start.year == prev_year
    assert start.day == 1
    assert end.month == prev_month
    assert end.year == prev_year

def test_month_to_date_only_month():
    now = datetime.now()
    # If month > now.month, should use previous year
    start, end = month_to_date(month=12)
    if 12 > now.month:
        assert start.year == now.year - 1
    else:
        assert start.year == now.year
    assert start.month == 12
    assert start.day == 1
    assert end.month == 12
    # December always ends on 31st
    assert end.day == 31

def test_month_to_date_both_provided():
    start, end = month_to_date(month=2, year=2024)
    assert start == datetime(2024, 2, 1)
    assert end == datetime(2024, 2, 29)  # Leap year
    start, end = month_to_date(month=4, year=2023)
    assert start == datetime(2023, 4, 1)
    assert end == datetime(2023, 4, 30)

def test_month_to_date_invalid():
    with pytest.raises(ValueError):
        month_to_date(month=None, year=None)

    # Should not raise, but test for coverage
    month_to_date(month=1, year=2022)

def test_month_no_to_name_valid():
    assert month_no_to_name(1) == "January"
    assert month_no_to_name(12) == "December"
    assert month_no_to_name(6) == "June"

def test_month_no_to_name_invalid():
    with pytest.raises(ValueError):
        month_no_to_name(0)
    with pytest.raises(ValueError):
        month_no_to_name(13)
