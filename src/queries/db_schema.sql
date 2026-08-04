-- SQL schema for economics database
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    issuer TEXT NOT NULL,
    amount REAL NOT NULL,
    origin TEXT NOT NULL,
    main_category TEXT COLLATE NOCASE,
    sub_category TEXT COLLATE NOCASE,
    comment TEXT,
    verification_number TEXT,
    modification_log TEXT
);

CREATE TABLE IF NOT EXISTS issuer_classifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    issuer TEXT UNIQUE NOT NULL,
    main_category TEXT NOT NULL COLLATE NOCASE,
    sub_category TEXT NOT NULL COLLATE NOCASE
);

CREATE TABLE IF NOT EXISTS allowances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    rikard_allowance REAL NOT NULL,
    sara_allowance REAL NOT NULL,
    UNIQUE(year, month)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);