# Economics add-on

Import bank files, classify transactions and follow the budget for the household's two
accounts, *Familj* and *Rikard*, straight from the Home Assistant sidebar.

## Installation

1. In Home Assistant: **Settings → Add-ons → Add-on store → ⋮ → Repositories**
2. Add `https://github.com/rikpet/economics`
3. Install **Economics**, start it and enable **Show in sidebar**

Updates appear when `version` in `config.yaml` is bumped (**⋮ → Check for updates** to look
right away). It can be installed next to other add-ons such as *Todo*; see below.

## Bringing over the existing database

Either:

- open **Accounts** in the add-on and use **Restore** with your current `transactions.db`, or
- copy the file to `/share/economics/transactions.db` and set the option
  `database_path` to that path. The file stays reachable from your PC via Samba, so
  the `econ` command line can keep using it (`ECONOMICS_DB=\\homeassistant\share\economics\transactions.db`).
  Do not write to it from the PC while the add-on is writing.

An older database is upgraded on first use, and all its data is put in the private account
**Rikard**.

## Accounts

There are two accounts: **Familj** for the joint economy and **Rikard** for the private one.
Each has its own transactions, issuer rules and categories, which can be edited under
**Categories**. Switch account with the selector at the top. Accounts can be renamed under
**Accounts**, but not added or removed.

## Working with transactions

1. **Import**: upload a SEB `.csv` or Remember `.xls` export. Rows already imported are
   skipped, so overlapping exports are fine. Afterwards the page shows what happened: the
   file's dates, how many transactions were added, classified by issuer rules, left to
   classify or already imported, and the added transactions themselves.
2. **Classify**: choose categories for as many new transactions as you like and press
   **Save** once. Transactions you leave without a category stay on the page. Tick
   *Remember for this issuer* to classify that issuer automatically from now on.

Card purchases in SEB exports end with the purchase date (`TESTBUTIKEN STO/25-12-30`). The
date is dropped, so the issuer is `TESTBUTIKEN STO` and one issuer rule covers every purchase
there.
3. **Budget**: amounts per month and category. Click an amount to see its transactions.
   The last column is the **average per month** over the months of the year that are over
   (in January, the running month), so a half-finished month doesn't pull it down.
4. **Charts**: income and expenses per month, the spread over categories, and one category
   compared with the year before. Click a category bar to look closer at it. Above the
   charts you can pick months and categories; clicking a category in a chart legend hides
   it from the charts (the budget is not affected).

To divide one purchase over several categories, open the transaction (**Edit**) and choose
**Split…**. Enter the parts' amounts as positive numbers (a minus sign makes a part go the
other way, e.g. a return) and pick a category for each; they must add up to the original
amount. The parts then replace the original everywhere. **Change the split** on any part,
or **Undo split**, brings you back.

The budget ends with **Expenses**, **Expenses excl. fixed costs** and **Balance** (income
minus expenses). With budgets set, these rows get one too — the groups' budgets added up,
and for Balance the income budget minus the expense budgets. What counts is set
per category under **Categories** with *Type*:

- *Expense* and *Fixed expense* count as expenses; fixed ones (from the start Hushåll) are
  left out of "Expenses excl. fixed costs".
- *Transfer / savings* (from the start Sparande and Bokföring › Internöverföring) is shown as
  a cost but not counted as an expense.
- *Income* is income.

*Set for group* gives a whole group the same type. Categories with **0 monthly** ticked
(from the start Bokföring › Utlägg/skuld) are flagged on the budget page for every finished
month where they don't add up to 0. Press **Acknowledge** on a warning you have looked at
and accept; it goes away (also from the sensor) until that month's amount changes. The
acknowledged ones are listed below the warnings, each with **Undo**.

**Budgets** are optional: give a main category a monthly budget under **Categories**
(*Budget/month*). The budget page then shows it in a *Budget* column and colours the
amounts red when an expense group is over budget, or an income group under it in a finished
month. The *Average* column is compared with the budget too. Groups without a budget
stay black.

Under **Categories** you can hide categories you don't want in the budget, such as
Bokföring or internal transfers: a whole group with *Hide from budget*, or a single
sub-category by unticking *Show*. Hidden categories keep their transactions but are left
out of the budget, the charts and the sensors.

## Allowance

**Allowance** works out how much each of you transfers to the joint account (Familj) every
month:

> to Familj = income − shared expenses − allowance

- *Income* is the salary that month.
- *Shared expenses* are what you paid for the household with your own money, so you
  transfer that much less. Several amounts can be added up as in a spreadsheet:
  `=100+250+75`.
- The *allowance* is what each of you keeps on the private account. It is 12 000 kr unless
  a month has its own; the default can be changed under *Settings and people*.
- Pension savings are not part of the calculation.

Pick a month, fill in the figures and press **Save**; the result updates while you type.
A negative result means Familj should pay that person, e.g. during parental leave. The
table below shows every month of the year.

Rikard is linked to the account Rikard: an empty income is that account's
Bokföring › Inkomst for the month, and its debt — Bokföring › Familjeutlägg, what was
paid for the family — is added to the shared expenses the month after. What was actually
transferred (Bokföring › Familjekonto) is shown next to the result.

From the command line: `econ transfer show --year 2026`,
`econ transfer set Sara 3 --income 40000 --costs 700+500` and
`econ transfer allowance 10000 --month 3` (or `--default`).

## Sensors

With `publish_sensors` on, the add-on publishes these sensors for every account (`<account>`
and `<category>` are lower-case, with å/ä/ö written as a/a/o):

| Entity | State | Attributes |
| --- | --- | --- |
| `sensor.economics_<account>_<category>` | This month's amount for the main category (expenses as positive cost). Not published for hidden categories. | `previous_month`, `year_to_date`, `sub_categories`, `month` |
| `sensor.economics_<account>_expenses` | This month's expenses, as the budget's Expenses row | `excl_fixed_costs`, `previous_month`, `previous_month_excl_fixed_costs`, `year_to_date` |
| `sensor.economics_<account>_balance` | This month's income minus expenses | `previous_month`, `year_to_date` |
| `sensor.economics_<account>_debt_check` | Number of finished months this year where a *0 monthly* category is not 0 and not acknowledged | `not_zero` (category, month, amount), `acknowledged` |
| `sensor.economics_<account>_unclassified` | Number of unclassified transactions | |
| `sensor.economics_<account>_latest_transaction` | Date of the latest transaction | |
| `sensor.economics_familj_transfer_<person>` | This month's amount the person transfers (Allowance page); `unknown` before anything is entered | `income`, `shared_expenses`, `allowance`, `previous_month`, `debt_from_previous_month` and `transferred` (Rikard) |

They are refreshed every `sensor_interval` minutes and after each change in the web interface.
Home Assistant does not keep these states over a restart; the add-on publishes them again
within `sensor_interval` minutes.

Example card:

```yaml
type: entities
title: Familj, this month
entities:
  - sensor.economics_familj_mat
  - sensor.economics_familj_boende
  - sensor.economics_familj_unclassified
```

## Running alongside other add-ons (e.g. Todo)

The add-on is independent of other add-ons such as *Todo* (`rikpet/ha-todo`): its own
slug (`economics`), sidebar entry, `/data` and Ingress port (8100). It does not publish any
port on the LAN, so it does not compete with Todo's port 8099. Its cookies are named
`economics_*` and limited to its own Ingress path. Each repository is added separately under
**Repositories**; both can be installed at the same time.

## Options

| Option | Default | |
| --- | --- | --- |
| `database_path` | `/data/economics.db` | SQLite file. `/data` is included in add-on backups. |
| `publish_sensors` | `true` | Publish the sensors above. |
| `sensor_interval` | `15` | Minutes between sensor refreshes. |
| `currency` | `SEK` | Unit of the sensors. |

## Backup

The database in `/data` is part of Home Assistant's backups of the add-on. You can also
download a copy at any time under **Accounts → Download backup**.
