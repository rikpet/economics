import csv
from app_types import Transaction
import pandas as pd


def parse_seb_transactions(file_path: str) -> list[Transaction]:
    """
    Reads SEB bank transactions from a CSV file and returns a list of Transaction objects.

    Args:
        file_path (str): Path to the SEB transactions CSV file.
    """
    with open(file_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=';')
    
        transactions = []

        for row in reader:
            transactions.append(
                Transaction(
                    date=str(row.get('Valutadatum')),
                    issuer=str(row.get('Text')).strip(),
                    amount=float(row.get('Belopp').replace(',', '.')),  # type: ignore
                    origin="SEB"
                )
            )

    return transactions


def parse_remember_transactions(file_path: str) -> list[Transaction]:
    """
    Reads Remember card transactions from an Excel file and returns a list of Transaction objects.

    Args:
        file_path (str): Path to the Remember card transactions Excel file.
    """
    with open(file_path, encoding="utf-8") as f:
        transactions = []
        df = pd.read_excel(file_path, header=2)
        for _, row in df.iterrows():
            date = str(row.get('Datum'))
            issuer = str(row.get('Detaljer')).strip()
            amount = float(str(row.get('Fakturabelopp')).replace(',', '.'))
            origin = "Remember card"
            transactions.append(
                Transaction(
                    date=date,
                    issuer=issuer,
                    amount=amount,
                    origin=origin
                )
            )

    return transactions
