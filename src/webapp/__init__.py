"""Web interface, served stand-alone (`econ web`) or as a Home Assistant add-on via Ingress."""

import os
import secrets
import tempfile
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
from app_types import Account, Category, IssuerClassification
from budget import budget_table, cash_flow, hidden_categories, monthly_balances
from category_templates import TEMPLATES
from utils import month_to_date

ACCOUNT_COOKIE = "economics_account"
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

    def year_arg() -> int:
        return request.args.get("year", type=int) or datetime.now().year

    def here() -> str:
        """The current page as a relative URL that includes the Ingress prefix.

        request.url is absolute and uses the Host the add-on was reached on, which under
        Ingress is the add-on's internal address, not one the browser can reach.
        """
        query = request.query_string.decode()
        return request.script_root + request.path + (f"?{query}" if query else "")

    def local_target(value: str | None, default: str) -> str:
        """Resolve a `next` parameter (an app path like /1/transactions?year=2025)."""
        if value and value.startswith("/") and not value.startswith("//") and "\\" not in value:
            return request.script_root + value
        return default

    def year_options(account_id: int) -> list[int]:
        return sorted(set(db.get_years(dbp(), account_id)) | {datetime.now().year}, reverse=True)

    @app.context_processor
    def inject():
        return {
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

        @after_this_request
        def remember(response):
            response.set_cookie(ACCOUNT_COOKIE, str(account_id), max_age=365 * 24 * 3600,
                                path=cookie_path(), samesite="Lax")
            return response

        return render_template(
            "budget.html", rows=rows, year=year, years=years, show_subs=show_subs,
            hidden_count=len(hidden),
            unclassified=db.count_unclassified_transactions(dbp(), account_id),
        )

    # ---------------------------------------------------------------------------------
    # Charts
    # ---------------------------------------------------------------------------------

    @app.get("/<int:account_id>/charts")
    def charts(account_id: int):
        account = load_account(account_id)
        year = year_arg()
        now = datetime.now()
        # Months that have happened; the rest of the year is not averaged over.
        elapsed = 12 if year < now.year else (now.month if year == now.year else 0)

        categories = db.get_categories(dbp(), account_id)
        hidden = hidden_categories(categories)
        balances = monthly_balances(dbp(), account, year)
        flow = cash_flow(balances, categories)
        rows = budget_table(balances, show_sub_category=True, hidden=hidden)
        previous_rows = budget_table(monthly_balances(dbp(), account, year - 1),
                                     show_sub_category=True, hidden=hidden)

        order = [r.main_category for r in rows if not r.is_sub]
        totals = sorted(((main, sum(values)) for main, values in flow.expenses_by_main.items()),
                        key=lambda item: -item[1])

        # Stacked columns: the largest categories get a color, in category-tree order so a
        # category keeps its color when the ranking shifts; the rest fold into "Other".
        top = sorted((main for main, total in totals[:STACK_SERIES] if total > 0),
                     key=lambda main: order.index(main) if main in order else len(order))
        stack = [{"key": main, "name": main.capitalize(), "values": flow.expenses_by_main[main]}
                 for main in top]
        rest = [main for main, _ in totals
                if main not in top and any(flow.expenses_by_main[main])]
        if rest:
            stack.append({"key": "other", "name": "Other", "other": True,
                          "values": [sum(flow.expenses_by_main[m][i] for m in rest)
                                     for i in range(12)]})

        selected = request.args.get("category") or (totals[0][0] if totals else None)
        if selected not in order:
            selected = order[0] if order else None
        trend = subs = None
        if selected:
            main_row = next(r for r in rows if r.main_category == selected and not r.is_sub)
            previous_row = next((r for r in previous_rows
                                 if r.main_category == selected and not r.is_sub), None)
            trend = {
                "name": main_row.label,
                "current": main_row.values[:elapsed] if elapsed else [],
                # Left out when the previous year has nothing to compare with.
                "previous": previous_row.values if previous_row and any(previous_row.values) else [],
            }
            subs = sorted(({"label": r.label, "key": r.sub_category, "value": r.total} for r in rows
                           if r.is_sub and r.main_category == selected and r.total),
                          key=lambda item: -item["value"])

        income = sum(flow.income[:elapsed or 12])
        expenses = sum(flow.expenses[:elapsed or 12])
        chart_data = {
            "months": MONTHS,
            "year": year,
            "previousYear": year - 1,
            "flow": {"income": flow.income, "expenses": flow.expenses},
            "stack": stack,
            "totals": [{"key": m, "label": m.capitalize(), "value": v} for m, v in totals],
            "selected": selected,
            "trend": trend,
            "subs": subs,
        }
        return render_template(
            "charts.html", year=year, years=year_options(account_id), chart=chart_data,
            selected=selected, mains=[r for r in rows if not r.is_sub],
            income=income, expenses=expenses, elapsed=elapsed,
            average=expenses / elapsed if elapsed else 0, hidden_count=len(hidden),
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
            return redirect(local_target(request.args.get("next"),
                                         url_for("transactions", account_id=account_id)))

        return render_template("transaction_edit.html", t=trans,
                               groups=category_choices(account_id),
                               back=local_target(request.args.get("next"),
                                                 url_for("transactions", account_id=account_id)))

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
        return render_template("categories.html", groups=groups, usage=usage)

    @app.post("/<int:account_id>/categories")
    def add_category(account_id: int):
        load_account(account_id)
        try:
            db.add_category(dbp(), account_id, request.form.get("main", ""),
                            request.form.get("sub", ""),
                            invert_sign=request.form.get("kind", "expense") == "expense")
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
                db.update_category(dbp(), account_id, category_id,
                                   request.form.get("main", ""), request.form.get("sub", ""),
                                   invert_sign=request.form.get("kind", "expense") == "expense",
                                   hidden=not request.form.get("visible"))
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

