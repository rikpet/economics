from app_types import Transaction
from parser import parse_remember_transactions, parse_seb_transactions

def test_read_seb_transactions():
    file_path = "tests/input_data/seb_transactions.csv"
    transactions = parse_seb_transactions(file_path)
    assert len(transactions) == 8  # Assuming there are 8 valid transactions in the test CSV
    assert transactions[0] == Transaction(
        date='2025-10-27',
        issuer='46701740605',
        amount=200.000,
        origin='SEB'
    )
    assert transactions[1] == Transaction(
        date='2025-10-25',
        issuer='46701740606',
        amount=-195.000,
        origin='SEB'
    )
    assert transactions[2] == Transaction(
        date='2025-09-28',
        issuer='PANT',
        amount=-127.000,
        origin='SEB'
    )
    assert transactions[7] == Transaction(
        date='2025-09-26',
        issuer='PREMIE FÖRS.',
        amount=-1026.000,
        origin='SEB'
    )

def test_read_remember_transactions():
    file_path = "tests/input_data/remember_card_transactions.xls"
    transactions = parse_remember_transactions(file_path)
    assert len(transactions) == 5  # Assuming there are 5 valid transactions in the test CSV
    assert transactions[0] == Transaction(
        date='2025-09-30',
        issuer='INBETALNING BANKGIRO',
        amount=6325.02,
        origin='Remember card'
    )
    assert transactions[3] == Transaction(
        date='2025-09-04',
        issuer='Zettle_*Ton Pai Thai',
        amount=-110.00,
        origin='Remember card'
    )
    assert transactions[4] == Transaction(
        date='2025-09-02',
        issuer='WIENERKONDITORIET',
        amount=-48.6,
        origin='Remember card'
    )