# Changelog

## 2.11.0

- New **Transfers** page: how much each person should transfer to the joint account in a
  month, as income − one-off costs − allowance (pension is not included). Add the people at
  the bottom of the page, pick a month and fill in their figures. Fields take sums such as
  `=700+500`, the result updates as you type, and the allowance carries over to the
  following months until you change it. A year table shows every month per person and
  together.
- A person can be linked to their own account (e.g. Privat). Empty fields then use its
  Bokföring › Inkomst and the previous month's Bokföring › Familjeutlägg, and the page shows
  what was actually transferred according to Bokföring › Familjekonto.
- Home Assistant: a `transfer_<person>` sensor per person with this month's amount.
- Command line: `econ transfer show` and `econ transfer set`.

## 2.10.0

- Issuer rules now work for card purchases from SEB. Their text ends with the purchase
  date (`TESTBUTIKEN STO/25-12-30`), which made every purchase a new issuer. The date is now
  dropped, so the issuer is `TESTBUTIKEN STO` and one rule covers every purchase in that
  shop. Transactions and rules already in the database are updated the same way when the
  add-on starts. If you had several rules for one shop with different dates, the newest is
  kept, and a rule without a date always wins.
- After an import you see what happened instead of a one-line message: the file's dates,
  how many transactions were added, classified by issuer rules, left to classify and
  already imported, plus a list of the added transactions. There are buttons to classify
  the rest, see the transactions or go to the budget, and the form to import the next
  file. Importing the same file again says clearly that nothing was new.
- A file that isn't the export it was read as (e.g. a csv from another bank) now gets an
  error that says which columns are missing.
- Classify several transactions at once: choose categories for as many as you like and
  press **Save** once. The Save button shows how many will be saved, and the page warns
  you before you leave it with unsaved choices.

## 2.9.0

- New **Balance** row under the budget: income minus expenses for each month and the year.
  Negative when more went out than came in.
- The total rows now have budgets too: Expenses shows the expense groups' budgets added up,
  Expenses excl. fixed costs the same without the fixed groups, and Balance the income
  budget minus the expense budgets (when an income group has a budget). They turn red like
  the groups: Expenses when over, Balance when under in a finished month.
- In the private account the calculated Inkomst › Månadspeng is no longer counted as income
  on top of Bokföring › Inkomst it comes from, so the income in the charts is no longer
  counted twice.
- Home Assistant: a new `balance` sensor per account (this month, previous month, year to
  date).

## 2.8.1

- On a phone the budget shows two months side by side (the chosen month and the one
  before it) next to the year's total, so you can compare with last month. ‹ › move one
  month at a time.

## 2.8.0

- Debt-check warnings (e.g. Utlägg/skuld not 0 in a month) can be acknowledged with
  **Acknowledge** on the budget page. An acknowledged warning disappears, also from the
  Home Assistant sensor, and is listed under "acknowledged warnings" with an **Undo**.
- The acknowledgement is for the amount at that time: if the month's amount changes later,
  the warning comes back.

## 2.7.0

Works much better on a phone (for example in the Home Assistant app):

- A compact header: pick the account at the top and swipe the menu sideways. It no longer
  stays on top of the page while you scroll.
- The budget shows one month at a time next to the year's total; step with ‹ › or pick a
  month. On a tablet the category names stay in view while the months scroll.
- Transactions and issuer rules are shown as cards; tap a transaction to edit it. The
  filters fold away until you need them.
- Categories are folded into one card per group with a short summary; tap to open.
- Bigger buttons, fields and check boxes, and nothing is wider than the screen.

## 2.6.0

- Optional monthly budgets per main category. Set one under **Categories** (*Budget/month*
  in the group's header); leave it empty for no budget.
- The budget page shows the budget next to each group, and the amounts turn red when an
  expense group goes over it (an income group: when it stays under it in a finished month).
  The total turns red when the year so far is over budget. Without budgets everything stays
  black, as before.
- Home Assistant: category sensors with a budget get `budget`, `budget_left` and, for
  expenses, `over_budget` attributes.

## 2.5.0

- The budget ends with two totals: **Expenses** (every expense, but not income or savings)
  and **Expenses excl. fixed costs** (the same without fixed monthly costs, from the start
  Hushåll). Unclassified transactions count as expenses.
- Each category now has a type under **Categories**: Income, Expense, Fixed expense or
  Transfer / savings. Savings and internal transfers start as Transfer / savings and are not
  counted as expenses; Hushåll starts as Fixed expense. Set a whole group at once with
  *Set for group*, e.g. Boende in the family account.
- Debt check: categories marked *0 monthly* (from the start Bokföring › Utlägg/skuld) are
  flagged on the budget page for every finished month where they don't add up to 0, with a
  link to that month's transactions.
- New Home Assistant sensors per account: expenses this month (with the total excluding
  fixed costs as an attribute) and the number of months this year where debt is not 0.
- The charts count expenses the same way, so savings no longer show up as expenses there.

## 2.4.0

- Split a transaction into several smaller ones, each with its own category and comment —
  for example a supermarket receipt that is partly groceries and partly household things.
  Open the transaction, choose **Split…**, and divide the amount; the page shows how much
  is left to divide. The parts replace the original in the budget, the charts and the lists.
- A split can be changed or undone later, from the original or from any of its parts.
  Importing the same bank file again does not bring the original back.

## 2.3.1

- The charts use the latest version of Plotly (4.1). They look and work as before.

## 2.3.0

- The charts are now drawn with Plotly: smoother hover with one tooltip per month listing
  every category and the total, and legends that wrap neatly on a phone. Clicking a
  category in a legend still hides it from the charts, and clicking a bar still opens that
  category or its transactions.

## 2.2.0

- Editing a transaction works again in Home Assistant. Home Assistant's own security check
  rejected the edit link and answered "400: Bad Request" before it reached the add-on.
- Charts: hide categories straight from the chart. Click a category in the legend, or use
  the category buttons above the charts. This only changes the charts (the budget is left
  as it is) and is remembered for each account.
- Charts: pick which months to look at, for example only January to March, or the whole
  year without July. The key figures and every chart follow the selection.

## 2.1.0

- New **Charts** page: income and expenses per month, expenses per month by category,
  expenses per category for the year, and a closer look at one category compared with the
  year before. Hover or tap a chart to see the amounts.
- Categories can be hidden from the budget, e.g. Bokföring or internal transfers. Hide a whole
  group or single sub-categories under **Categories**. Hidden categories are also left out
  of the charts and the Home Assistant sensors.
- The Categories page is easier to read: columns line up, a group can be renamed in one go,
  and a sub-category is moved to another group with a drop-down.
- The budget shows main categories only by default. Use *Show sub-categories* for the details.
- Saving an edited transaction no longer ends in "400: Bad Request".

## 2.0.0

- Runs as a Home Assistant add-on with a web interface (Ingress) and budget sensors.
- Accounts: separate transactions, issuer rules and categories, e.g. for the family and
  private economy. Existing data moves to the account *Privat*.
- Categories are stored per account and can be edited; new accounts start from a template.
- `econ --account/-a`, `econ --db`, `econ account ...`, `econ category ...`, `econ web` and
  `econ advanced backup`.
- Runs side by side with other add-ons such as Todo: no LAN port, Ingress port 8100 and
  cookies limited to the add-on.
- The database path comes from `ECONOMICS_DB` instead of a hard-coded path.
