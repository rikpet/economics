# Changelog

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
