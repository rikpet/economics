# Changelog

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
