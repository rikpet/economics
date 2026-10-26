import os

# Path to the SQLite database. Override with the ECONOMICS_DB environment variable.
_LEGACY_WINDOWS_PATH = 'C:\\Users\\RikardPettersson\\OneDrive\\Ekonomi\\transactions.db'

DATABASE_PATH = os.environ.get(
    'ECONOMICS_DB',
    _LEGACY_WINDOWS_PATH if os.name == 'nt' else 'transactions.db'
)

# Account used when none is given. Name or id; empty means the first account.
DEFAULT_ACCOUNT = os.environ.get('ECONOMICS_ACCOUNT', '')
