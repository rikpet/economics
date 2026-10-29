from datetime import datetime, timedelta
import os
import click
import questionary

import calendar

import database as db
import operations
from app_types import SplitPart
from cli.context import AppContext, category_tree, pass_app
from printout import generate_table


def select_file(start_dir="."):
    """Interactively browse the filesystem and pick a file.

    Shows a selectable list of the entries in the current directory. Choosing a
    directory navigates into it, ".." goes up one level, and choosing a file
    returns its path. Returns None if the user cancels.
    """
    current = os.path.abspath(start_dir)
    while True:
        try:
            entries = sorted(os.listdir(current))
        except OSError:
            entries = []

        dirs = [e for e in entries if os.path.isdir(os.path.join(current, e))]
        files = [e for e in entries if os.path.isfile(os.path.join(current, e))]

        choices = [questionary.Choice("..", value=("up", None))]
        choices += [questionary.Choice(f"{d}/", value=("dir", d)) for d in dirs]
        choices += [questionary.Choice(f, value=("file", f)) for f in files]

        selection = questionary.select(
            f"Select a transactions file  [{current}]",
            choices=choices,
        ).ask()

        if selection is None:
            return None

        kind, name = selection
        if kind == "up":
            current = os.path.dirname(current)
        elif kind == "dir":
            current = os.path.join(current, name)
        else:  # file
            return os.path.join(current, name)


@click.command(name='add')
@click.argument('file_path', required=False)
@click.argument('origin', required=False)
@pass_app
def add_transactions(app: AppContext, file_path, origin):
    """Adds transactions to database

    Args:
        file_path (str): Path to the transactions file. If omitted, an
            interactive file selector is shown.
        origin (str): Origin of the transactions, e.g., "SEB" or "Remember".
            If omitted, an interactive selector is shown.
    """
    if file_path is None:
        file_path = select_file("originals" if os.path.isdir("originals") else ".")
        if not file_path:
            return

    if origin is None:
        origin = questionary.select(
            "Origin of the transactions:",
            choices=["SEB", "Remember"],
            use_shortcuts=True,
        ).ask()
        if origin is None:
            return

    click.echo(f'Processing file: {file_path} (account: {app.account.name})')

    try:
        result = operations.import_file(app.database_path, app.account_id, file_path, origin)
    except ValueError as e:
        raise click.ClickException(str(e))

    click.echo(result.summary())
    if result.unclassified:
        click.echo("Classify the rest with: econ trans classify")

#TODO: add check on category and sub-category
@click.command(name='list')
@click.option('--start-date', type=click.DateTime(formats=["%Y-%m-%d"]), default=None, help="Start date (YYYY-MM-DD)")
@click.option('--end-date', type=click.DateTime(formats=["%Y-%m-%d"]), default=None, help="End date (YYYY-MM-DD)")
@click.option('--month', type=int, default=None, help="Month (1-12)")
@click.option('--year', type=int, default=None, help="Year (e.g., 2023)")
@click.option('--category', type=str, default=None, multiple=True, help="Filter by main category")
@click.option('--sub-category', type=str, default=None, multiple=True, help="Filter by sub-category")
@click.option('--origin', type=str, default=None, help="Filter by origin (substring match)")
@click.option('--sort-date', type=click.Choice(['asc', 'desc']), default=None, help="Sort transactions by date")
@click.option('--sum', 'show_sum', is_flag=True, help="Show sum of transaction amounts")
@click.option('--count', 'show_count', is_flag=True, help="Show the number of transactions")
@click.option('--verbose', '-v', is_flag=True, help="Show all transaction information")
@pass_app
def list_transactions(app: AppContext, start_date, end_date, month, year, category: tuple[str], sub_category: tuple[str], origin: str, sort_date: str, show_sum: bool, show_count: bool, verbose: bool):
    """List all transactions in the database, optionally filtered by date range."""

    year = datetime.now().year if year is None else year
    if month:
        start_date = datetime(year, month, 1)
        days_in_month = calendar.monthrange(year, month)[1]
        end_date = start_date + timedelta(days=days_in_month - 1)

    transactions = db.get_transactions(app.database_path, app.account_id, start_date=start_date, end_date=end_date, main_category=list(category), sub_category=list(sub_category), origin=origin)

    if len(transactions) == 0:
        click.echo('No transactions found.')
        return

    if sort_date:
        transactions.sort(key=lambda t: t.date, reverse=(sort_date == 'desc'))

    if verbose:
        header = ["ID", "ISSUER", "AMOUNT", "DATE", "ORIGIN", "MAIN CATEGORY", "SUB CATEGORY", "COMMENT", "VERIFICATION NUMBER", "MODIFICATION LOG"]
    else:
        header = ["ID", "ISSUER", "AMOUNT", "DATE", "ORIGIN", "MAIN CATEGORY", "SUB CATEGORY"]

    rows = []
    for trans in transactions:
        if verbose:
            rows.append([
                trans.id,
                trans.issuer,
                trans.amount,
                trans.date,
                trans.origin,
                trans.main_category if trans.main_category is not None else "",
                trans.sub_category if trans.sub_category is not None else "",
                trans.comment if trans.comment is not None else "",
                trans.verification_number if trans.verification_number is not None else "",
                trans.modification_log if trans.modification_log is not None else ""
            ])
        else:
            rows.append([
                trans.id,
                trans.issuer,
                trans.amount,
                trans.date,
                trans.origin,
                trans.main_category if trans.main_category is not None else "",
                trans.sub_category if trans.sub_category is not None else ""
            ])

    click.echo('Listing transactions:\n')
    click.echo(generate_table(
        header=header,
        rows=rows
    ))

    if show_sum:
        total_amount = sum(t.amount for t in transactions)
        click.echo(f'\nTotal amount: {total_amount:.2f}')

    if show_count:
        click.echo(f'\nNumber of transactions: {len(transactions)}')

@click.command(name='modify')
@click.argument('transaction_id', type=int)
@click.option('--category', 'main_category', type=str, default=None, help="New main category")
@click.option('--sub-category', type=str, default=None, help="New sub-category")
@click.option('--date', type=click.DateTime(formats=["%Y-%m-%d"]), default=None, help="New date (YYYY-MM-DD)")
@click.option('--comment', type=str, default=None, help="New comment")
@pass_app
def modify_transaction(app: AppContext, transaction_id, main_category, sub_category, date, comment):
    """Modify an existing transaction."""
    if main_category is None and sub_category is None and date is None and comment is None:
        click.echo('No modifications specified. Use --category, --sub-category, --date or --comment to specify modifications.')
        return

    try:
        operations.modify_transaction(app.database_path, app.account_id, transaction_id,
                                      main_category, sub_category, date, comment)
    except ValueError as e:
        click.echo(str(e))


@click.command(name='classify')
@pass_app
def classify_transactions(app: AppContext):
    """Classify transactions not yet classified."""
    # Transactions whose issuer has a rule are classified without asking.
    operations.apply_issuer_rules(app.database_path, app.account_id)

    tree = category_tree(app)
    for trans in db.get_unclassified_transactions(app.database_path, app.account_id):

        # Prompt user for classification
        click.echo(f'\n\nTransaction: {trans.issuer} | {trans.amount} | {trans.date} | {trans.origin}' )

        main_category=questionary.select(
            "Main category for this transaction",
            choices=["SKIP"] + list(tree),
            use_shortcuts=True,

        ).ask()

        if main_category is None:
            return
        
        if main_category == "SKIP":
            continue
            
        sub_categories = tree[main_category]
        if len(sub_categories) == 1:
            sub_category = sub_categories[0]
        else:
            sub_category = questionary.select(
                "Sub category for this transaction",
                choices=sub_categories,
                use_shortcuts=True
            ).ask()

            if sub_category is None:
                return

        comment = questionary.text("Comment (optional, leave empty to skip):").ask()
        if comment is None:
            return
        comment = comment.strip() or None

        store_issuer_classification: bool = questionary.confirm(
            "Store this classification for future use?",
            default=False
        ).ask()

        operations.classify_transaction(app.database_path, app.account_id, trans.id,
                                        main_category, sub_category, comment,
                                        remember_issuer=bool(store_issuer_classification))


@click.command(name='split')
@click.argument('transaction_id', type=int)
@click.option('--part', 'parts', multiple=True, required=True,
              help="AMOUNT[:MAIN/SUB[:COMMENT]], in the original's direction, e.g. 700:mat/butik. "
                   "Repeat for every part; they must add up to the transaction's amount.")
@pass_app
def split_transaction(app: AppContext, transaction_id, parts):
    """Split a transaction into parts with their own category."""
    trans = db.get_transaction(app.database_path, app.account_id, transaction_id)
    if trans is None:
        raise click.ClickException(f'No transaction found with id {transaction_id}.')
    sign = -1 if trans.amount < 0 else 1
    tree = category_tree(app)
    split_parts = []
    for text in parts:
        amount_text, _, rest = text.partition(':')
        category, _, comment = rest.partition(':')
        main, _, sub = category.partition('/')
        main, sub = main.strip().lower() or None, sub.strip().lower() or None
        if main and sub not in tree.get(main, []):
            raise click.ClickException(f'Unknown category: {category}')
        try:
            amount = operations.parse_amount(amount_text)
        except ValueError as e:
            raise click.ClickException(str(e))
        if amount is None:
            raise click.ClickException(f'Missing amount in {text!r}')
        split_parts.append(SplitPart(amount * sign, main, sub, comment.strip() or None))
    try:
        ids = operations.split_transaction(app.database_path, app.account_id, transaction_id,
                                           split_parts)
    except ValueError as e:
        raise click.ClickException(str(e))
    click.echo(f'Transaction {transaction_id} split into {len(ids)} parts: '
               f'{", ".join(map(str, ids))}.')


@click.command(name='unsplit')
@click.argument('transaction_id', type=int)
@pass_app
def unsplit_transaction(app: AppContext, transaction_id):
    """Undo a split, so the original transaction counts again."""
    try:
        operations.unsplit_transaction(app.database_path, app.account_id, transaction_id)
    except ValueError as e:
        raise click.ClickException(str(e))
    click.echo(f'Split of transaction {transaction_id} undone.')


@click.command(name='unclassified')
@pass_app
def unclassified_transactions(app: AppContext):
    """Check for unclassified transactions."""
    unclassified_transactions = db.get_unclassified_transactions(app.database_path, app.account_id)
    if len(unclassified_transactions) == 0:
        click.echo('No unclassified transactions found.')
        return
    click.echo(f'Found {len(unclassified_transactions)} unclassified transactions.')

