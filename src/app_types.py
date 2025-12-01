from dataclasses import dataclass

@dataclass
class Transaction():
    date: str
    issuer: str
    amount: float
    origin: str
    main_category: str | None = None
    sub_category: str | None = None

@dataclass
class ReadTransaction():
    id: int
    date: str
    issuer: str
    amount: float
    origin: str
    main_category: str | None = None
    sub_category: str | None = None

@dataclass
class IssuerClassification:
    issuer: str
    main_category: str
    sub_category: str
