# Economics

Handling my private and family economy: import bank files from SEB and Remember, classify
the transactions and follow the budget per month and category.

Data is kept in two **accounts**: *Familj* for the family economy and *Rikard* for the private. Each
account has its own transactions, issuer rules and category tree.

There are three ways to run it:

- **Home Assistant add-on**, with a web interface in the HA sidebar and budget sensors.
  See [DOCS.md](DOCS.md).
- **Web interface** on your own computer: `econ web`.
- **Command line**: `econ ...`.

All three work on the same SQLite database format.

## Installation

```sh
pip install -e ".[web]"      # add [dev] for pytest and ruff
```

The database path is taken from `--db`, the `ECONOMICS_DB` environment variable, or
defaults to `transactions.db` (on Windows the OneDrive path used before).
Existing databases are upgraded automatically on first use. Everything already in them is put
in the account **Rikard** (called Privat before 3.0).

## Command line

```sh
econ account list
econ account rename Familj "Familjen"           # accounts can't be added or removed

econ --account Familj trans add originals/seb_jan.csv SEB
econ -a Familj trans classify
econ -a Familj balance --year 2026 --show-sub-category   # --all includes hidden categories
econ -a Familj category list
econ -a Familj category add boende el
econ -a Familj category budget mat 6000           # monthly budget; --clear removes it
econ check list --year 2026                       # categories that should be 0 every month
econ check ack bokföring/utlägg/skuld 2026-03     # acknowledge a warning (undo: econ check undo ...)
econ -a Familj issuer list
econ -a Familj trans split 42 --part 700:mat/butik --part 300:hushåll/övrigt:lampa
econ -a Familj trans unsplit 42

econ web                                         # web interface on http://127.0.0.1:8100
econ transfer show --year 2026                   # the allowance calculation (Familj)
econ transfer set Sara 3 --income 40000 --costs 700+500
econ transfer allowance 10000 --month 3          # --default sets the default (12 000)
econ advanced backup backup.db
```

Without `--account`, the account in `ECONOMICS_ACCOUNT` or else the first account (Rikard) is
used.

### Derived allowance

For accounts with *derive allowance* enabled (Rikard is), `inkomst › månadspeng` is
calculated as `bokföring › inkomst − bokföring › familjekonto − last month's
bokföring › familjeutlägg`, as before.

## Development

```sh
pytest
docker build -t economics-addon .                # the add-on image
docker run --rm -p 8100:8100 economics-addon
```
