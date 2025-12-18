

from app_types import ReadTransaction
from balance import Balance


def test_placeholder():
    balance = Balance(2025, 2)

    balance.add(ReadTransaction(
        id=1,
        date='2025-02-15',
        issuer='Test Issuer',
        amount=1000,
        origin='Test Origin',
        main_category='inkomst',
        sub_category='övrigt'
    ))
    assert balance.get("inkomst") == 1000