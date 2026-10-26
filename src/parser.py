import csv
import hashlib
from app_types import IssuerClassification, Transaction


def _hash_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _disambiguate(verification_numbers: list[str]) -> list[str]:
    """Append _2, _3, ... to repeated ids in file order so identical rows stay distinct."""
    counts: dict[str, int] = {}
    out: list[str] = []
    for vn in verification_numbers:
        n = counts.get(vn, 0) + 1
        counts[vn] = n
        out.append(vn if n == 1 else f"{vn}_{n}")
    return out


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
            date = str(row.get('Valutadatum'))
            verifikationsnummer = str(row.get('Verifikationsnummer'))
            text = str(row.get('Text')).strip()
            belopp = str(row.get('Belopp'))
            amount = float(belopp.replace(',', '.'))
            transactions.append(
                Transaction(
                    date=date,
                    issuer=text,
                    amount=amount,
                    origin="SEB",
                    verification_number=_hash_id("SEB", date, verifikationsnummer, text, belopp)
                )
            )

    vns = _disambiguate([t.verification_number for t in transactions])
    for t, vn in zip(transactions, vns):
        t.verification_number = vn
    return transactions


def parse_remember_transactions(file_path: str) -> list[Transaction]:
    """
    Reads Remember card transactions from an Excel file and returns a list of Transaction objects.

    Args:
        file_path (str): Path to the Remember card transactions Excel file.
    """
    import pandas as pd  # heavy; only loaded when a Remember file is imported

    transactions = []
    df = pd.read_excel(file_path, header=2)
    for _, row in df.iterrows():
        date = str(row.get('Datum'))
        issuer = str(row.get('Detaljer')).strip()
        plats = str(row.get('Plats'))
        transaktionsbelopp = str(row.get('Transaktionsbelopp'))
        amount = float(str(row.get('Fakturabelopp')).replace(',', '.'))
        origin = "Remember card"
        transactions.append(
            Transaction(
                date=date,
                issuer=issuer,
                amount=amount,
                origin=origin,
                verification_number=_hash_id("REM", date, issuer, plats, transaktionsbelopp)
            )
        )

    vns = _disambiguate([t.verification_number for t in transactions])
    for t, vn in zip(transactions, vns):
        t.verification_number = vn
    return transactions


def parse_original_transactions(file_path: str) -> list[Transaction]:
    """
    Reads transactions from a CSV file in the original format and returns a list of Transaction objects.

    Args:
        file_path (str): Path to the transactions CSV file.
    """
    with open(file_path, encoding="utf-8-sig") as f:
        reader = csv.reader(f, delimiter=';')
    
        transactions = []

        for row in reader:
            amount_str = str(row[3]).replace(",", ".").replace(" kr", "").replace(" ", "").strip()
            transactions.append(
                Transaction(
                    date=str(row[0]),
                    issuer=str(row[1]).strip(),
                    origin=str(row[2]),
                    amount=float(amount_str),
                    main_category=str(row[4]),
                    sub_category=str(row[5])   
                )
            )

    return transactions


def parse_original_issuers(file_path: str) -> list[IssuerClassification]:
    """
    Reads issuer classifications from a CSV file in the original format and returns a dictionary mapping issuers to their classifications.

    Args:
        file_path (str): Path to the issuers CSV file.
    """
    with open(file_path, encoding="utf-8-sig") as f:
        reader = csv.reader(f, delimiter=';')
    
        issuer_classifications = []

        for row in reader:
            issuer_classifications.append(
                IssuerClassification(
                    issuer=str(row[0]).strip(),
                    main_category=str(row[1]).strip(),
                    sub_category=str(row[2]).strip()   
                )
            )

    return issuer_classifications