from parser import parse_remember_transactions, parse_seb_transactions

def test_read_seb_transactions():
    file_path = "tests/input_data/seb_transactions.csv"
    transactions = parse_seb_transactions(file_path)
    assert len(transactions) == 8  # Assuming there are 8 valid transactions in the test CSV
    assert transactions[0].date == '2025-10-27'
    assert transactions[0].issuer == '46701740605'
    assert transactions[0].amount == 200.000
    assert transactions[0].origin == 'SEB'
    assert transactions[0].verification_number is not None
    assert transactions[0].verification_number.startswith('SEB_')

    assert transactions[1].issuer == '46701740606'
    assert transactions[2].issuer == 'PANT'
    assert transactions[7].issuer == 'PREMIE FÖRS.'

    # Rows that share Verifikationsnummer must still get distinct ids.
    vns = [t.verification_number for t in transactions]
    assert len(set(vns)) == len(vns)


def test_read_remember_transactions():
    file_path = "tests/input_data/remember_card_transactions.xls"
    transactions = parse_remember_transactions(file_path)
    assert len(transactions) == 5
    assert transactions[0].date == '2025-09-30'
    assert transactions[0].issuer == 'INBETALNING BANKGIRO'
    assert transactions[0].amount == 6325.02
    assert transactions[0].origin == 'Remember card'
    assert transactions[0].verification_number is not None
    assert transactions[0].verification_number.startswith('REM_')

    vns = [t.verification_number for t in transactions]
    assert len(set(vns)) == len(vns)


def test_seb_verification_number_is_deterministic():
    a = parse_seb_transactions("tests/input_data/seb_transactions.csv")
    b = parse_seb_transactions("tests/input_data/seb_transactions.csv")
    assert [t.verification_number for t in a] == [t.verification_number for t in b]