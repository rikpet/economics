# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

Personal economy app for Rikard Pettersson: import bank exports (SEB csv, Remember card
xls), classify the transactions and follow a budget per month and category. Data is split
into two fixed **accounts**, *Familj* (joint) and *Rikard* (private, called *Privat* before
migration 10), each with its own transactions, issuer rules and category tree. Accounts
can be renamed but not added or removed in the UI or CLI (the user's choice: one
household); `db.create_account()` remains for tests. Storage is SQLite. It runs three ways on the same database:

- **Home Assistant add-on** on a Raspberry Pi 5 (aarch64): Flask web UI via Ingress, plus
  budget sensors pushed to HA. Runs next to the user's other add-on, `rikpet/ha-todo`.
- **Web UI** locally: `econ web` (port 8100).
- **CLI**: `econ ...` (click), used on the user's Windows laptop.

GitHub: `rikpet/economics` (public).

## Layout

```
config.yaml, Dockerfile,     the HA add-on, at the repo root (Supervisor finds any
.dockerignore, translations/ config.* in the repo, so no subfolder is needed)
repository.yaml              HA add-on repository manifest
DOCS.md, CHANGELOG.md        shown to the user in HA (docs tab, update dialog)
src/                         flat modules, imported as top-level names (`import database`)
  database.py                SQLite layer: migrations, accounts, categories, transactions
                             (incl. splits), issuer rules
  balance.py                 Balance: one month's totals per (main, sub) category
  budget.py                  monthly_balances(), budget_table(), cash_flow(), hidden-category helpers
  transfers.py               the Allowance page: transfer_year(), month_allowances(), parse_sum()
  operations.py              import/classify/modify actions shared by CLI and web
  parser.py                  SEB / Remember / legacy csv parsers
  category_templates.py      category trees for new accounts (private, family, empty)
  ha_sensors.py              publishes sensors via the Supervisor API
  addon.py                   add-on entry point (reads /data/options.json, serves on 8100)
  version.py                 __version__
  cli/                       click commands; cli/context.py holds AppContext (db path + account)
  webapp/                    Flask app factory, Jinja templates, static (style.css, charts.js,
                             vendor/plotly-basic.min.js)
tests/                       pytest; tests/input_data holds SYNTHETIC fixtures only
scripts/                     one-off maintenance scripts
```

## Development

```bash
python -m venv .venv && . .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest                                           # pythonpath is set in pyproject.toml
econ --db scratch.db web                         # http://127.0.0.1:8100
```

Set `ECONOMICS_DB` (or pass `--db`) to a scratch file. Without it the CLI uses the user's
real database on Windows (OneDrive path in `constants.py`).

Prefer driving the real UI in a browser (Playwright) over trusting tests alone, and test
through an Ingress-like proxy that strips a prefix, sets `X-Ingress-Path` and applies HA's
security filter — the Ingress bugs so far were invisible without one. The most faithful
proxy copies the two aiohttp hops from HA Core `hassio/ingress.py` and Supervisor
`api/ingress.py`. Check both light and dark mode, and a
390px-wide viewport.

## Conventions

**Never commit personal data.** The repo is public and its history was rewritten once to
remove bank exports. `originals/` and `*.xls` are git-ignored; test fixtures must be made
up (Swedish fiction phone numbers 070-1740605..699, "TEST TESTSSON"). Don't put real
issuers, amounts, balances or IPs in tests, docs or commit messages.

**Versioning.** The version lives in three files that must agree: `config.yaml`,
`pyproject.toml`, `src/version.py`. Bump all three and add a `CHANGELOG.md` entry for any
change that should reach the add-on. HA only offers an update when `config.yaml`'s version
changes on `main`; git tags are not used.

**Changelog voice.** Written for the user: what changed and what it means for them.
Implementation detail belongs in the commit message.

**Migrations are append-only.** `database.MIGRATIONS` is a list and `PRAGMA user_version`
is the number applied. Never edit an existing entry — live databases exist at every version.
SQLite can't alter constraints, so those changes rebuild the table (migration 2 is the
worked example). Legacy (pre-account) databases have `user_version` 0 and go through the
whole list; all their data ends up in account 1 (*Privat*, renamed *Rikard* by migration 10).

**Everything is account-scoped.** Database functions take `(database_path, account_id, ...)`
and every query filters on `account_id` — including lookups by id, so one account can never
read or modify another's rows. Web routes call `load_account()` and resolve category ids
with `category_by_id()`, which also checks the account.

**Commits** use the GitHub noreply address
(`66693061+rikpet@users.noreply.github.com`), not a work email. **Pushing directly to
`main` is the preferred way to deliver code in this repo** — no feature branch or PR
needed. Run `pytest` before pushing; CI (`.github/workflows/python-package.yml`) also runs
on every push to `main`, so check that run afterwards.

## Design decisions worth knowing

**Category names are stored lower-case** and shown with `.capitalize()`. Comparisons go
through Python's `lower()` (`py_lower()` is registered on every connection) because
SQLite's `NOCASE` only folds ASCII, so `'Övrigt' != 'övrigt'` there.

**Expense vs income is `invert_sign`.** Expense categories flip the sign so costs show as
positive numbers. Unknown or deleted categories count as *Uncategorized* instead of
raising, so the budget never breaks when categories are edited.

**Derived allowance.** For accounts with `derive_allowance` (Rikard), `inkomst/månadspeng` is
calculated, not imported: `bokföring/inkomst − bokföring/familjekonto − previous month's
bokföring/familjeutlägg`. `monthly_balances()` wires up the previous month (December of the
year before for January).

**Split transactions** (migration 4): the original row stays with `is_split = 1` so a
re-import still finds its verification number, and its parts are new rows with
`parent_id` pointing at it, the same date/issuer/origin and no verification number. Every
read that sums or lists transactions excludes the originals via `database.COUNTED`
(`is_split = 0`) — use it in any new query. Parts must add up to the original to the öre and
can't be split themselves; re-splitting replaces the parts, unsplitting deletes them. In the
UI amounts are entered in the original's direction (positive numbers for an expense).

**Expense roles and the debt check** (migration 5): `categories.expense_role` is
`variable`, `fixed` or `transfer`, meaningful for expense categories (`invert_sign`); the UI
shows it with `invert_sign` as one *Type* (`Category.kind`, `category_templates.KINDS`).
`budget.summary_rows()` builds the "Expenses" / "Expenses excl. fixed costs" / "Balance"
rows (expenses: not hidden, `counts_as_expense`, plus unclassified; income:
`counts_as_income()`: the derived `inkomst/månadspeng` counts only when
`bokföring/inkomst` doesn't (`salary_is_counted()` — usually Bokföring is hidden), so the
salary is never counted twice and never left out), and `cash_flow()` for the charts uses the same rules. With the budgets
passed in, the rows carry summed budgets (Balance only when an income group has one) and
`summary_checks()` colours them like `budget_checks()`; both share `_compare()`. `categories.zero_check` marks categories that must add up to 0 each month;
`zero_check_flags()` checks only finished months (`completed_months()`), hidden ones
included. Warnings can be acknowledged (migration 7, table `zero_check_acks`, keyed by
account/main/sub/year/month with the amount at the time); `split_acknowledged()` treats an
acknowledgement as valid only while the amount is unchanged, and renames carry the rows
along (`UPDATE OR REPLACE`). Defaults for new categories come from names in `category_templates`
(`TRANSFER_MAINS`, `TRANSFER_SUBS`, `FIXED_MAINS`, `ZERO_CHECK_SUB_PART`) via
`_apply_category_defaults()`; migration 5 has its own frozen copy of those rules.

**Budgets** (migration 6, table `budgets`): an optional monthly amount per main category
and account; `rename_main_category()` moves it along. `budget.budget_checks()` decides what
is red: expense groups over budget in any month up to now, income groups (every sub of type
Income) under budget in finished months only. The last column is the average per month
over `average_months()` (the finished months; the running month in January), coloured by
comparing it with the monthly budget (`BudgetCheck.average_red`).
Without a budget nothing is coloured — amounts stay in the normal text colour.

**Allowance calculation** (the *Allowance* page, routes `/<id>/transfers`; migrations 9
and 10, tables `people`, `person_months`, `allowance_months`): what Rikard and Sara each
transfer to the joint account, `income − shared expenses − allowance`, pension deliberately
left out. People belong to the joint account (migration 10 seeds Rikard, linked to the
private account, and Sara); the nav's Allowance link and the `econ transfer` commands find
that account themselves (the one with people, else the first without `derive_allowance`).
`person_months` holds income and shared expenses with the text as typed
(`income_input`/`costs_input`, since `parse_sum()` accepts `=100+250`); its `allowance`
column is unused since migration 10. The allowance is one amount per month for the
household: `allowance_months`, else the setting `default_allowance`, else
`DEFAULT_ALLOWANCE` (12 000) — no carry-over. A person with `linked_account_id` uses that
account's Bokföring › Inkomst when no income is entered, and its Bokföring › Familjeutlägg
of the previous month (the debt) is **added** to their shared expenses; Bokföring ›
Familjekonto shows what was transferred. That link is the one place an account reads
another account's data on purpose; people and their months are still account-scoped.

**Hidden categories** (`categories.hidden`) are left out of the budget table, the charts and
the sensors, including their share of the main category's total. They still exist for
classification. `econ balance --all` shows them.

**Charts** use **Plotly** (`plotly.js-basic-dist-min` 4.1.2, vendored as
`webapp/static/vendor/plotly-basic.min.js` with its MIT license — no CDN, since the page is
served through Ingress). `webapp/static/charts.js` wraps it in `columns()`, `hbars()` and
`lines()`, fed by JSON the `charts` route embeds. The basic bundle has bar, scatter and pie
only; switching to the full bundle costs ~3 MB more. To upgrade, download the tarball from
npm, check its `dist.integrity`, read the CHANGELOG's breaking changes (v4 only accepts
valid CSS colors — ours are hex from the CSS variables), and replace the file (asset URLs
carry `?v=`).
The filter form (`f=1`, months `m`, shown categories `c`, `offered`) only affects the
charts; the categories left out are remembered per account in the `economics_charts_<id>`
cookie, months are not. A legend click on a category hides it via that form
(`plotly_legendclick` returns false); other series toggle in place. Colors are read from the
CSS variables (`--series-1..8`, `--viz-other`, `--viz-context`) at render time and the
charts are redrawn when the color scheme changes. The categorical palette order is validated
for colour-blind safety — don't reorder or invent colors; fold extra series into "Other".

**The add-on image** is built by the Supervisor on the Pi from `Dockerfile`
(`python:3.13-slim`, glibc, so pandas/numpy install as wheels — don't switch to the Alpine
HA base images). `.dockerignore` is a whitelist. pandas is imported lazily in `parser.py`
to keep idle memory low.

## Gotchas (each one cost a real bug)

- **HA's security filter rejects URLs before they reach the add-on.** Home Assistant Core
  (`homeassistant/components/http/security_filter.py`) answers "400: Bad Request" when the
  unquoted path+query matches patterns like `[a-zA-Z0-9_]=/([a-z0-9_.]//?)+` — so a query
  parameter whose value starts with a path (`?next=/1/transactions`) can never be used.
  Pass filters, not paths (see `transactions_url()` and the `back` parameter).
  `test_no_url_is_blocked_by_home_assistant` runs the same regex over every rendered link;
  keep it passing when adding links. "400: Bad Request" in that exact form is aiohttp's,
  i.e. HA's, not Flask's.
- **Ingress redirects.** Never redirect to `request.url` (absolute, with the add-on's
  internal host) or to a bare app path. Use `url_for()`, `here()` or `transactions_url()`
  in `webapp/__init__.py`; `IngressMiddleware` sets `SCRIPT_NAME` from `X-Ingress-Path` so
  generated URLs carry the prefix.
- **Cookies under Ingress** share Home Assistant's origin with every other add-on. Ours
  are named `economics_*` and scoped to the Ingress path (`cookie_path()`).
- **Static caching.** Asset links carry `?v={{ app_version }}`; without it browsers keep the
  old CSS/JS after an add-on update.
- **iOS auto-zoom** on focused fields under 16px: inputs are forced to 16px on small screens.
- **Inline `confirm()` in templates**: use `onclick='return confirm({{ msg|tojson }})'`
  (single-quoted attribute). `|e` inside a double-quoted attribute breaks on apostrophes.
- **Flash messages contain category names**, so a test asserting a name is *absent* from a
  page must look at the table markup (`<th scope="row">…`), not the whole body.
- **Phones (≤ 640px)** get their own layout from CSS media queries at the end of
  `style.css`: the header stops being sticky and the nav scrolls sideways; tables become
  cards (`table.tx`, `table.rules`, cell classes `c-*` / `r-*`); the budget table hides all
  month columns but two (`.m .mN` cells; `data-month` = the later month 2..12 and
  `data-month2` = the one before on the table; `?m=` in the URL; ‹ › step one month). Sections marked `details[data-mobile-closed]` are folded on phones by the
  script in `base.html`. Check new pages at 360 and 390px: no element wider than the
  screen, tap targets about 40px.
- **Issuers are cleaned before they are stored or looked up.** SEB card purchases end with
  the purchase date (`TESTBUTIKEN STO/25-12-30`); `parser.clean_issuer()` drops it, and
  `classify_issuer()` / `get_issuer_classification()` apply it too, so a rule typed with a
  date still matches. Migration 8 cleaned existing rows with its own frozen copy of the
  regex. The verification-number hash still uses the raw text, so re-imports dedupe.
- **The legacy `C:\Users\...` default path** becomes a literal file name in the working
  directory if old code runs on Linux; it's git-ignored (`*.db`) but delete it if it appears.

## Deployment

Push to `main` with the version bumped. In HA: Add-on store → ⋮ → Check for updates, then
update *Economics*; the Pi builds the image (a few minutes). The database lives in the
add-on's `/data/economics.db` (or the `database_path` option) and is migrated on start.
