"""Web interface, served stand-alone (`econ web`) or as a Home Assistant add-on via Ingress."""

import os
import secrets
import tempfile
from urllib.parse import parse_qsl, quote, unquote
from datetime import datetime
from typing import Callable

from flask import (
    Flask,
    has_request_context,
    abort,
    after_this_request,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask.sessions import SecureCookieSessionInterface

import database as db
import operations
from version import __version__
from app_types import Account, Category, IssuerClassification, SplitPart
from budget import (
    budget_checks,
    budget_table,
    cash_flow,
    completed_months,
    hidden_categories,
    monthly_balances,
    split_acknowledged,
    summary_checks,
    summary_rows,
    zero_check_flags,
)
from category_templates import KINDS, TEMPLATES
from utils import month_to_date

ACCOUNT_COOKIE = "economics_account"
CHARTS_COOKIE = "economics_charts"  # categories left out of the charts, per account
TRANSACTION_FILTERS = ("year", "month", "category", "sub", "origin", "q", "sort")
KIND_LABELS = {"income": "Income", "expense": "Expense", "fixed": "Fixed expense",
               "transfer": "Transfer / savings"}
STACK_SERIES = 7  # colored categories in the stacked chart; the rest are "Other"

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


class IngressMiddleware:
    """Mount the app under the path Home Assistant's Ingress proxy serves it from.

    Ingress strips its prefix before forwarding and passes it in X-Ingress-Path. Setting it
    as SCRIPT_NAME makes url_for() generate links that work through the proxy.
    """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        prefix = environ.get("HTTP_X_INGRESS_PATH", "").rstrip("/")
        if prefix:
            environ["SCRIPT_NAME"] = prefix
        return self.app(environ, start_response)


def cookie_path() -> str:
    """Scope cookies to the app's own path. Under Ingress every add-on shares Home Assistant's
    origin, so cookies on "/" would be visible to (and could collide with) other add-ons."""
    return (request.script_root or "") + "/" if has_request_context() else "/"


class ScopedSessionInterface(SecureCookieSessionInterface):
    def get_cookie_path(self, app):
        return cookie_path()


def period_label(months: list[int]) -> str:
    """Selected months as text, with runs collapsed: [1, 2, 3, 7] -> 'Jan–Mar, Jul'."""
    runs: list[list[int]] = []
    for m in months:
        if runs and m == runs[-1][-1] + 1:
            runs[-1].append(m)
        else:
            runs.append([m])
    return ", ".join(MONTHS[r[0] - 1] if len(r) == 1 else f"{MONTHS[r[0] - 1]}\u2013{MONTHS[r[-1] - 1]}"
                     for r in runs)


def format_amount(value: float) -> str:
    """An amount for an input field: 1234.5 -> '1234,50', 300.0 -> '300'."""
    if round(value, 2) == round(value):
        return str(int(round(value)))
    return f"{value:.2f}".replace(".", ",")


def format_exact(value: float) -> str:
    """Kronor with öre when there are any: -808.26 -> '−808,26', 300 -> '300'."""
    text = f"{abs(value):,.2f}".replace(",", "\u00a0").replace(".", ",").removesuffix(",00")
    return ("\u2212" if value < 0 else "") + text


def format_money(value: float | None) -> str:
    if value is None:
        return ""
    text = f"{round(value):,}".replace(",", " ")
    return text.replace("-", "−")


def create_app(database_path: str, on_change: Callable[[], None] | None = None,
               secret_key: str | None = None) -> Flask:
    """Create the web app.

    Args:
        database_path: SQLite database to use. It is created/migrated on startup.
        on_change: Called after every successful change, e.g. to refresh HA sensors.
    """
    app = Flask(__name__)
    app.secret_key = secret_key or secrets.token_hex(32)
    app.config["SESSION_COOKIE_NAME"] = "economics_session"
    app.session_interface = ScopedSessionInterface()
    app.config["DATABASE"] = database_path
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024
    app.wsgi_app = IngressMiddleware(app.wsgi_app)
    app.jinja_env.filters["money"] = format_money
    app.jinja_env.filters["exact"] = format_exact

    db.create_tables(database_path)

    def dbp() -> str:
        return app.config["DATABASE"]

    def load_account(account_id: int) -> Account:
        account = db.get_account(dbp(), account_id)
        if account is None:
            abort(404)
        g.account = account
        return account

    def category_choices(account_id: int) -> list[tuple[str, list[Category]]]:
        groups: dict[str, list[Category]] = {}
        for c in db.get_categories(dbp(), account_id):
            groups.setdefault(c.main_category, []).append(c)
        return list(groups.items())

    def category_by_id(account_id: int, value: str | None) -> Category | None:
        if not value or not value.isdigit():
            return None
        return db.get_category(dbp(), account_id, int(value))

    def kind_arg() -> tuple[bool, str]:
        """The Type chosen on the Categories page as (invert_sign, expense_role)."""
        kind = request.form.get("kind", "expense")
        if kind not in KINDS:
            raise ValueError(f"Unknown type: {kind}")
        return KINDS[kind]

    def year_arg() -> int:
        return request.args.get("year", type=int) or datetime.now().year

    def here() -> str:
        """The current page as a relative URL that includes the Ingress prefix.

        request.url is absolute and uses the Host the add-on was reached on, which under
        Ingress is the add-on's internal address, not one the browser can reach.
        """
        query = request.query_string.decode()
        return request.script_root + request.path + (f"?{query}" if query else "")

    def transactions_url(account_id: int, filters: str | None) -> str:
        """The transaction list with the filters it was left with.

        Links carry only the list's query string (year=2025&month=3), never a path:
        Home Assistant's security filter answers 400 to query strings like next=/1/...
        """
        args = {k: v for k, v in parse_qsl(filters or "") if k in TRANSACTION_FILTERS}
        return url_for("transactions", account_id=account_id, **args)

    def year_options(account_id: int) -> list[int]:
        return sorted(set(db.get_years(dbp(), account_id)) | {datetime.now().year}, reverse=True)

    @app.context_processor
    def inject():
        return {
            "kind_labels": KIND_LABELS,
            "accounts": db.get_accounts(dbp()),
            "account": g.get("account"),
            "months": MONTHS,
            "app_version": __version__,
        }

    @app.after_request
    def notify_change(response):
        if on_change and request.method == "POST" and response.status_code < 400:
            on_change()
        return response

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "schema": db.schema_version(dbp())}

    @app.get("/")
    def index():
        account = db.find_account(dbp(), request.cookies.get(ACCOUNT_COOKIE))
        if account is None:
            return redirect(url_for("accounts"))
        return redirect(url_for("budget", account_id=account.id))

    # ---------------------------------------------------------------------------------
    # Budget
    # ---------------------------------------------------------------------------------

    @app.get("/<int:account_id>/")
    def budget(account_id: int):
        account = load_account(account_id)
        year = year_arg()
        show_subs = request.args.get("subs", "0") == "1"
        categories = db.get_categories(dbp(), account_id)
        hidden = hidden_categories(categories)
        balances = monthly_balances(dbp(), account, year)
        rows = budget_table(balances, show_sub_category=show_subs, hidden=hidden)
        years = year_options(account_id)
        flags, acknowledged = split_acknowledged(
            zero_check_flags(balances, categories, completed_months(year)),
            db.get_zero_check_acks(dbp(), account_id, year))
        budgets = db.get_budgets(dbp(), account_id)
        # The month a phone shows first: the chosen one, else this month, or for another
        # year the last month with transactions.
        now = datetime.now()
        month_shown = request.args.get("m", type=int)
        if not month_shown or not 1 <= month_shown <= 12:
            used = [m for m in range(1, 13) if any(r.values[m - 1] for r in rows)]
            month_shown = now.month if year == now.year else (used[-1] if used else 1)
        # Phones show this month and the one before it; January pairs with February.
        month_shown = max(month_shown, 2)
        checks = budget_checks(rows, budgets, categories, year, list(balances))
        summary = summary_rows(balances, categories, budgets)
        totals_checks = summary_checks(summary, year, list(balances))

        @after_this_request
        def remember(response):
            response.set_cookie(ACCOUNT_COOKIE, str(account_id), max_age=365 * 24 * 3600,
                                path=cookie_path(), samesite="Lax")
            return response

        return render_template(
            "budget.html", rows=rows, year=year, years=years, show_subs=show_subs,
            hidden_count=len(hidden), summary=summary, summary_checks=totals_checks, flags=flags,
            budgets=budgets, checks=checks, month_shown=month_shown, acknowledged=acknowledged,
            flagged={(f.main_category, f.sub_category, f.month) for f in flags},
            flagged_main={(f.main_category, f.month) for f in flags},
            unclassified=db.count_unclassified_transactions(dbp(), account_id),
        )

    @app.post("/<int:account_id>/checks")
    def zero_check(account_id: int):
        """Acknowledge a debt-check warning (or undo that), then go back to the budget."""
        load_account(account_id)
        form = request.form
        year, month = form.get("year", type=int), form.get("month", type=int)
        main, sub = form.get("main", ""), form.get("sub", "")
        if not (year and month and main and sub):
            abort(400)
        if form.get("action") == "undo":
            db.unacknowledge_zero_check(dbp(), account_id, main, sub, year, month)
            flash(f"{main.capitalize()} › {sub.capitalize()} in {MONTHS[month - 1]} is a "
                  "warning again.", "ok")
        else:
            amount = operations.parse_amount(form.get("amount", "")) or 0
            db.acknowledge_zero_check(dbp(), account_id, main, sub, year, month, amount)
            flash(f"Acknowledged: {main.capitalize()} › {sub.capitalize()} is "
                  f"{format_money(amount)} kr in {MONTHS[month - 1]}. If the amount changes, "
                  "the warning comes back.", "ok")
        return redirect(url_for("budget", account_id=account_id, year=year,
                                subs=form.get("subs", "0"), m=form.get("m", "")))

    # ---------------------------------------------------------------------------------
    # Charts
    # ---------------------------------------------------------------------------------

    @app.get("/<int:account_id>/charts")
    def charts(account_id: int):
        account = load_account(account_id)
        year = year_arg()
        now = datetime.now()
        # Months that have happened; later months are not averaged over.
        elapsed = 12 if year < now.year else (now.month if year == now.year else 0)

        categories = db.get_categories(dbp(), account_id)
        hidden = hidden_categories(categories)
        balances = monthly_balances(dbp(), account, year)
        rows = budget_table(balances, show_sub_category=True, hidden=hidden)
        all_mains = [r for r in rows if not r.is_sub]

        # Filters. `f` marks a submitted filter form; without it the defaults apply: every
        # month, and the categories this account last chose to show in the charts.
        submitted = request.args.get("f") == "1"
        months = sorted({m for m in request.args.getlist("m", type=int) if 1 <= m <= 12})
        months = months or list(range(1, 13))
        cookie = f"{CHARTS_COOKIE}_{account_id}"
        excluded = {unquote(c) for c in request.cookies.get(cookie, "").split(",") if c}
        if submitted:
            # Only the chips the form offered can change; a category that wasn't on the
            # page (e.g. another year's) keeps its previous state.
            offered = set(request.args.getlist("offered"))
            excluded = (excluded - offered) | (offered - set(request.args.getlist("c")))
        idx = [m - 1 for m in months]

        def pick(values: list[float]) -> list[float]:
            return [values[i] for i in idx]

        flow = cash_flow(balances, categories, exclude=excluded)
        rows = [r for r in rows if r.main_category not in excluded]
        previous_rows = budget_table(monthly_balances(dbp(), account, year - 1),
                                     show_sub_category=True, hidden=hidden)

        order = [r.main_category for r in rows if not r.is_sub]
        totals = sorted(((main, total) for main, values in flow.expenses_by_main.items()
                         if (total := sum(pick(values)))),
                        key=lambda item: -item[1])

        # Stacked columns: the largest categories get a color, in category-tree order so a
        # category keeps its color when the ranking shifts; the rest fold into "Other".
        top = sorted((main for main, total in totals[:STACK_SERIES] if total > 0),
                     key=lambda main: order.index(main) if main in order else len(order))
        stack = [{"key": main, "name": main.capitalize(),
                  "values": pick(flow.expenses_by_main[main])} for main in top]
        rest = [main for main, _ in totals
                if main not in top and any(pick(flow.expenses_by_main[main]))]
        if rest:
            stack.append({"key": "other", "name": "Other", "other": True,
                          "values": [sum(flow.expenses_by_main[m][i] for m in rest) for i in idx]})

        # Look closer at the chosen category, else the largest expense.
        largest = next((main for main, _ in totals if main in order), None)
        selected = request.args.get("category")
        if selected not in order:
            selected = largest or (order[0] if order else None)
        past = [i for i in idx if i < elapsed]
        trend = subs = None
        if selected:
            main_row = next(r for r in rows if r.main_category == selected and not r.is_sub)
            previous_row = next((r for r in previous_rows
                                 if r.main_category == selected and not r.is_sub), None)
            previous = pick(previous_row.values) if previous_row else []
            trend = {
                "name": main_row.label,
                "current": [main_row.values[i] for i in past],
                # Left out when the previous year has nothing to compare with.
                "previous": previous if any(previous) else [],
            }
            subs = sorted(({"label": r.label, "key": r.sub_category, "value": sum(pick(r.values))}
                           for r in rows if r.is_sub and r.main_category == selected),
                          key=lambda item: -item["value"])
            subs = [item for item in subs if item["value"]]

        income = sum(flow.income[i] for i in past)
        expenses = sum(flow.expenses[i] for i in past)
        chart_data = {
            "months": [MONTHS[i] for i in idx],
            "year": year,
            "previousYear": year - 1,
            "flow": {"income": pick(flow.income), "expenses": pick(flow.expenses)},
            "stack": stack,
            "totals": [{"key": m, "label": m.capitalize(), "value": v} for m, v in totals],
            "selected": selected,
            "trend": trend,
            "subs": subs,
        }

        @after_this_request
        def remember(response):
            if submitted:
                response.set_cookie(cookie, ",".join(quote(c) for c in sorted(excluded)),
                                    max_age=365 * 24 * 3600,
                                    path=cookie_path(), samesite="Lax")
            return response

        return render_template(
            "charts.html", year=year, years=year_options(account_id), chart=chart_data,
            selected=selected, mains=[r for r in rows if not r.is_sub], all_mains=all_mains,
            excluded=excluded, months_selected=months, all_months=len(months) == 12,
            period=period_label(months),
            income=income, expenses=expenses, past_count=len(past),
            average=expenses / len(past) if past else 0, hidden_count=len(hidden),
        )

    # ---------------------------------------------------------------------------------
    # Transactions
    # ---------------------------------------------------------------------------------

    @app.get("/<int:account_id>/transactions")
    def transactions(account_id: int):
        load_account(account_id)
        year = year_arg()
        month = request.args.get("month", type=int)
        main = request.args.get("category") or None
        sub = request.args.get("sub") or None
        origin = request.args.get("origin") or None
        search = request.args.get("q") or None

        if month:
            start, end = month_to_date(month, year)
        else:
            start, end = datetime(year, 1, 1), datetime(year, 12, 31)

        uncategorized = main == "uncategorized"
        rows = db.get_transactions(
            dbp(), account_id, start, end,
            [main] if main and not uncategorized else None,
            [sub] if sub and not uncategorized else None,
            origin, search,
        )
        if uncategorized:
            known = {(c.main_category, c.sub_category) for c in db.get_categories(dbp(), account_id)}
            rows = [t for t in rows
                    if ((t.main_category or "").lower(), (t.sub_category or "").lower()) not in known]

        if request.args.get("sort", "desc") == "desc":
            rows.reverse()

        years = year_options(account_id)
        return render_template(
            "transactions.html", rows=rows, year=year, years=years, month=month,
            main=main, sub=sub, origin=origin, q=search, sort=request.args.get("sort", "desc"),
            origins=db.get_origins(dbp(), account_id), groups=category_choices(account_id),
            total=sum(t.amount for t in rows),
        )

    @app.route("/<int:account_id>/transactions/<int:transaction_id>", methods=["GET", "POST"])
    def edit_transaction(account_id: int, transaction_id: int):
        load_account(account_id)
        trans = db.get_transaction(dbp(), account_id, transaction_id)
        if trans is None:
            abort(404)
        if trans.is_split:  # the original of a split is edited through its parts
            return redirect(url_for("split_transaction", account_id=account_id,
                                    transaction_id=transaction_id,
                                    back=request.args.get("back", "")))

        if request.method == "POST":
            category = category_by_id(account_id, request.form.get("category"))
            date = None
            if request.form.get("date"):
                try:
                    date = datetime.strptime(request.form["date"], "%Y-%m-%d")
                except ValueError:
                    flash("Invalid date.", "error")
                    return redirect(here())
            changed = operations.modify_transaction(
                dbp(), account_id, transaction_id,
                category.main_category if category else None,
                category.sub_category if category else None,
                date,
                request.form.get("comment", "").strip(),
            )
            if category and request.form.get("remember"):
                operations.classify_transaction(
                    dbp(), account_id, transaction_id, category.main_category,
                    category.sub_category, remember_issuer=True)
            flash("Transaction saved." if changed else "Nothing changed.", "ok")
            return redirect(transactions_url(account_id, request.args.get("back")))

        parent = (db.get_transaction(dbp(), account_id, trans.parent_id)
                  if trans.parent_id else None)
        return render_template("transaction_edit.html", t=trans, parent=parent,
                               groups=category_choices(account_id),
                               back_filters=request.args.get("back", ""),
                               back=transactions_url(account_id, request.args.get("back")))

    @app.route("/<int:account_id>/transactions/<int:transaction_id>/split",
               methods=["GET", "POST"])
    def split_transaction(account_id: int, transaction_id: int):
        """Split a transaction into parts, each with its own amount and category.

        Amounts are entered in the original's direction (an expense of -1 000 kr is split as
        700 and 300); a minus sign turns a part the other way, e.g. a return in the same
        purchase.
        """
        load_account(account_id)
        trans = db.get_transaction(dbp(), account_id, transaction_id)
        if trans is None:
            abort(404)
        back_filters = request.args.get("back", "")
        if trans.parent_id:
            return redirect(url_for("split_transaction", account_id=account_id,
                                    transaction_id=trans.parent_id, back=back_filters))
        sign = -1 if trans.amount < 0 else 1
        error = None

        if request.method == "POST":
            rows = list(zip(request.form.getlist("amount"), request.form.getlist("category"),
                            request.form.getlist("comment")))
            try:
                parts = []
                for amount_text, category_id, comment in rows:
                    value = operations.parse_amount(amount_text)
                    if value is None:
                        continue
                    category = category_by_id(account_id, category_id)
                    parts.append(SplitPart(
                        amount=value * sign,
                        main_category=category.main_category if category else None,
                        sub_category=category.sub_category if category else None,
                        comment=comment.strip() or None,
                    ))
                operations.split_transaction(dbp(), account_id, transaction_id, parts)
            except ValueError as e:
                error = str(e)
            else:
                flash(f"Split into {len(parts)} transactions.", "ok")
                return redirect(transactions_url(account_id, back_filters))
            entered = [{"amount": a, "category": int(c) if c.isdigit() else None, "comment": m}
                       for a, c, m in rows]
        else:
            existing = db.get_split_parts(dbp(), account_id, transaction_id)
            categories = {(c.main_category, c.sub_category): c.id
                          for c in db.get_categories(dbp(), account_id)}

            def row(amount: float | None, main: str | None, sub: str | None, comment: str | None):
                key = ((main or "").lower(), (sub or "").lower())
                return {"amount": format_amount(amount * sign) if amount is not None else "",
                        "category": categories.get(key), "comment": comment or ""}

            if existing:
                entered = [row(p.amount, p.main_category, p.sub_category, p.comment)
                           for p in existing]
            else:
                entered = [row(trans.amount, trans.main_category, trans.sub_category,
                               trans.comment), row(None, None, None, None)]

        groups = category_choices(account_id)
        return render_template("split.html", t=trans, rows=entered, error=error, sign=sign,
                               groups=groups, back_filters=back_filters,
                               categories_by_id={c.id: c for _, cats in groups for c in cats},
                               back=transactions_url(account_id, back_filters))

    @app.post("/<int:account_id>/transactions/<int:transaction_id>/unsplit")
    def unsplit_transaction(account_id: int, transaction_id: int):
        load_account(account_id)
        try:
            operations.unsplit_transaction(dbp(), account_id, transaction_id)
            flash("The split is undone; the original transaction counts again.", "ok")
        except ValueError as e:
            flash(str(e), "error")
        return redirect(transactions_url(account_id, request.args.get("back")))

    # ---------------------------------------------------------------------------------
    # Import
    # ---------------------------------------------------------------------------------

    @app.route("/<int:account_id>/import", methods=["GET", "POST"])
    def import_file(account_id: int):
        load_account(account_id)
        if request.method == "POST":
            upload = request.files.get("file")
            if upload is None or not upload.filename:
                flash("Choose a file to import.", "error")
                return redirect(here())

            origin = request.form.get("origin", "auto")
            suffix = os.path.splitext(upload.filename)[1].lower()
            if origin == "auto":
                origin = "remember" if suffix in (".xls", ".xlsx") else "seb"

            fd, path = tempfile.mkstemp(suffix=suffix)
            os.close(fd)
            try:
                upload.save(path)
                result = operations.import_file(dbp(), account_id, path, origin)
            except Exception as e:  # parsing errors come in many shapes from csv/pandas
                flash(f"Could not import {upload.filename} as {origin}: {e}", "error")
                return redirect(here())
            finally:
                os.remove(path)

            flash(f"{upload.filename}: added {result.added} transactions "
                  f"({result.classified} classified by issuer rules), "
                  f"skipped {result.skipped_duplicates} duplicates.", "ok")
            if result.added > result.classified:
                return redirect(url_for("classify", account_id=account_id))
            return redirect(here())

        return render_template("import.html", origins=list(operations.ORIGINS))

    # ---------------------------------------------------------------------------------
    # Classify
    # ---------------------------------------------------------------------------------

    @app.get("/<int:account_id>/classify")
    def classify(account_id: int):
        load_account(account_id)
        return render_template(
            "classify.html", rows=db.get_unclassified_transactions(dbp(), account_id),
            groups=category_choices(account_id),
        )

    @app.post("/<int:account_id>/classify/<int:transaction_id>")
    def classify_one(account_id: int, transaction_id: int):
        load_account(account_id)
        category = category_by_id(account_id, request.form.get("category"))
        if category is None:
            flash("Choose a category.", "error")
            return redirect(url_for("classify", account_id=account_id))
        remember = bool(request.form.get("remember"))
        try:
            operations.classify_transaction(
                dbp(), account_id, transaction_id, category.main_category, category.sub_category,
                request.form.get("comment", "").strip() or None, remember_issuer=remember)
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("classify", account_id=account_id))
        if remember:
            others = operations.apply_issuer_rules(dbp(), account_id)
            if others:
                flash(f"The rule also classified {others} other transactions.", "ok")
        anchor = request.form.get("next", "")
        return redirect(url_for("classify", account_id=account_id)
                        + (f"#t-{anchor}" if anchor.isdigit() else ""))

    @app.post("/<int:account_id>/classify/apply-rules")
    def apply_rules(account_id: int):
        load_account(account_id)
        count = operations.apply_issuer_rules(dbp(), account_id)
        flash(f"Classified {count} transactions by issuer rules.", "ok")
        return redirect(url_for("classify", account_id=account_id))

    # ---------------------------------------------------------------------------------
    # Issuer rules
    # ---------------------------------------------------------------------------------

    @app.get("/<int:account_id>/issuers")
    def issuers(account_id: int):
        load_account(account_id)
        q = (request.args.get("q") or "").strip().lower()
        rows = db.get_issuer_classifications(dbp(), account_id)
        if q:
            rows = [r for r in rows if q in r[1].issuer.lower()]
        return render_template("issuers.html", rows=rows, q=q,
                               groups=category_choices(account_id))

    @app.post("/<int:account_id>/issuers")
    def add_issuer(account_id: int):
        load_account(account_id)
        name = request.form.get("issuer", "").strip()
        category = category_by_id(account_id, request.form.get("category"))
        if not name or category is None:
            flash("Enter an issuer and choose a category.", "error")
        else:
            db.classify_issuer(dbp(), account_id, IssuerClassification(
                name, category.main_category, category.sub_category))
            flash(f"Rule for {name} saved.", "ok")
        return redirect(url_for("issuers", account_id=account_id))

    @app.post("/<int:account_id>/issuers/<int:issuer_id>")
    def update_issuer(account_id: int, issuer_id: int):
        load_account(account_id)
        if request.form.get("action") == "delete":
            db.remove_issuer_classification(dbp(), account_id, issuer_id)
            flash("Rule removed.", "ok")
        else:
            category = category_by_id(account_id, request.form.get("category"))
            if category is not None:
                db.modify_issuer_classification(dbp(), account_id, issuer_id,
                                                category.main_category, category.sub_category)
                flash("Rule updated.", "ok")
        return redirect(url_for("issuers", account_id=account_id, q=request.args.get("q", "")))

    # ---------------------------------------------------------------------------------
    # Categories
    # ---------------------------------------------------------------------------------

    @app.get("/<int:account_id>/categories")
    def categories(account_id: int):
        load_account(account_id)
        groups = category_choices(account_id)
        usage = {c.id: db.category_usage(dbp(), account_id, c.main_category, c.sub_category)
                 for _, cats in groups for c in cats}
        return render_template("categories.html", groups=groups, usage=usage,
                               budgets=db.get_budgets(dbp(), account_id))

    @app.post("/<int:account_id>/categories")
    def add_category(account_id: int):
        load_account(account_id)
        try:
            invert, role = kind_arg()
            db.add_category(dbp(), account_id, request.form.get("main", ""),
                            request.form.get("sub", ""), invert_sign=invert,
                            # Leave the default from the name (e.g. sparande -> transfer)
                            # unless something other than a plain expense was chosen.
                            expense_role=None if request.form.get("kind") == "expense" else role)
            flash("Category added.", "ok")
        except ValueError as e:
            flash(str(e), "error")
        return redirect(url_for("categories", account_id=account_id))

    @app.post("/<int:account_id>/categories/<int:category_id>")
    def update_category(account_id: int, category_id: int):
        load_account(account_id)
        try:
            if request.form.get("action") == "delete":
                db.delete_category(dbp(), account_id, category_id)
                flash("Category removed.", "ok")
            else:
                invert, role = kind_arg()
                db.update_category(dbp(), account_id, category_id,
                                   request.form.get("main", ""), request.form.get("sub", ""),
                                   invert_sign=invert, expense_role=role,
                                   hidden=not request.form.get("visible"),
                                   zero_check=bool(request.form.get("zero_check")))
                flash("Category saved.", "ok")
        except ValueError as e:
            flash(str(e), "error")
        return redirect(url_for("categories", account_id=account_id))

    @app.post("/<int:account_id>/categories/group")
    def update_category_group(account_id: int):
        load_account(account_id)
        main = request.form.get("main", "")
        action = request.form.get("action")
        try:
            if action in ("hide", "show"):
                db.set_category_hidden(dbp(), account_id, action == "hide", main_category=main)
                flash(f"{main.capitalize()} is {'hidden from' if action == 'hide' else 'shown in'} "
                      "the budget.", "ok")
            elif action == "budget":
                amount = operations.parse_amount(request.form.get("budget", ""))
                db.set_budget(dbp(), account_id, main, amount)
                flash(f"Budget for {main.capitalize()} "
                      + (f"set to {format_money(amount)} kr a month." if amount is not None
                         else "removed."), "ok")
            elif action == "kind":
                invert, role = kind_arg()
                db.set_group_kind(dbp(), account_id, main, invert, role)
                flash(f"All of {main.capitalize()} is now "
                      f"{KIND_LABELS[request.form.get('kind', 'expense')].lower()}.", "ok")
            else:
                db.rename_main_category(dbp(), account_id, main, request.form.get("name", ""))
                flash("Category renamed.", "ok")
        except ValueError as e:
            flash(str(e), "error")
        return redirect(url_for("categories", account_id=account_id))

    # ---------------------------------------------------------------------------------
    # Accounts, backup and restore
    # ---------------------------------------------------------------------------------

    @app.get("/accounts")
    def accounts():
        counts = {a.id: db.count_transactions(dbp(), a.id) for a in db.get_accounts(dbp())}
        return render_template("accounts.html", counts=counts, templates=list(TEMPLATES),
                               db_path=dbp(), schema=db.schema_version(dbp()))

    @app.post("/accounts")
    def create_account():
        try:
            account_id = db.create_account(dbp(), request.form.get("name", ""),
                                           request.form.get("template", "empty"),
                                           bool(request.form.get("derive_allowance")))
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("accounts"))
        flash("Account created.", "ok")
        return redirect(url_for("budget", account_id=account_id))

    @app.post("/accounts/<int:account_id>")
    def update_account(account_id: int):
        load_account(account_id)
        try:
            if request.form.get("action") == "delete":
                db.delete_account(dbp(), account_id)
                flash("Account deleted.", "ok")
            else:
                db.update_account(dbp(), account_id, name=request.form.get("name"),
                                  derive_allowance=bool(request.form.get("derive_allowance")))
                flash("Account saved.", "ok")
        except ValueError as e:
            flash(str(e), "error")
        return redirect(url_for("accounts"))

    @app.get("/backup")
    def backup():
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db.backup_database(dbp(), path)

        @after_this_request
        def cleanup(response):
            response.call_on_close(lambda: os.remove(path))
            return response

        name = f"economics-{datetime.now().strftime('%Y%m%d-%H%M')}.db"
        return send_file(path, as_attachment=True, download_name=name)

    @app.post("/restore")
    def restore():
        upload = request.files.get("file")
        if upload is None or not upload.filename:
            flash("Choose a database file.", "error")
            return redirect(url_for("accounts"))
        if not request.form.get("confirm"):
            flash("Tick the box to confirm that the current data will be replaced.", "error")
            return redirect(url_for("accounts"))

        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            upload.save(path)
            db.restore_database(path, dbp())
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("accounts"))
        finally:
            os.remove(path)
        flash(f"Database restored from {upload.filename}.", "ok")
        return redirect(url_for("index"))

    return app

