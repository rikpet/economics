from datetime import datetime
import sqlite3
import click

from constants import DATABASE_PATH
from printout import generate_table
from utils import month_no_to_name

def check_allowance():
    """Check if the allowance for the current month has been set."""
    current_month = datetime.now().month
    current_year = datetime.now().year

    with sqlite3.connect(DATABASE_PATH) as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM allowances WHERE month = ? AND year = ?', (current_month, current_year))
        row = c.fetchone()
        if not row:
            c.execute('SELECT * FROM settings WHERE key = ?', ('rikard_allowance',))
            rikard_default = c.fetchone()
            c.execute('SELECT * FROM settings WHERE key = ?', ('sara_allowance',))
            sara_default = c.fetchone()
            c.execute(
                'INSERT INTO allowances (year, month, rikard_allowance, sara_allowance) VALUES (?, ?, ?, ?)', 
                (current_year, current_month, rikard_default[1] if rikard_default else 0, sara_default[1] if sara_default else 0)
            )


@click.command(name='add')
@click.argument('amount', type=float)
@click.option('--month', type=int, required=True, default=None, help="Month to set the allowance for (default: current month)")
@click.option('--year', type=int, default=None, help="Year to set the allowance for (default: current year)")
@click.option('--rikard', is_flag=True, help="Set the allowance for Rikard")
@click.option('--sara', is_flag=True, help="Set the allowance for Sara")
def add_allowance(amount: float, month: int, year: int | None, rikard: bool, sara: bool):
    """Set the allowance for a specific month and year."""
    if month is None:
        raise click.ClickException("Month must be specified when adding an allowance.")
    
    if month < 1 or month > 12:
        raise click.ClickException("Month must be between 1 and 12.")

    if year is not None and (year < 2020 or year > datetime.now().year):
        raise click.ClickException("Year must be between 2020 and this year.") 

    year = year if year is not None else datetime.now().year

    if not rikard and not sara:
        rikard = sara = True  # If neither is specified, set both

    with sqlite3.connect(DATABASE_PATH) as conn:
        c = conn.cursor()
        if rikard:
            c.execute('INSERT INTO allowances (year, month, rikard_allowance) VALUES (?, ?, ?)', (year, month, amount))
        if sara:
            c.execute('INSERT INTO allowances (year, month, sara_allowance) VALUES (?, ?, ?)', (year, month, amount))
        conn.commit()


@click.command(name='update')
@click.argument('month', type=int)
@click.argument('amount', type=float)
@click.option('--year', type=int, default=None, help="Year for the allowance (default: current year)")
@click.option('--rikard', is_flag=True, help="Set the allowance for Rikard")
@click.option('--sara', is_flag=True, help="Set the allowance for Sara")
def update_allowance(month: int, amount: float, year: int | None, rikard: bool, sara: bool):
    """Set the allowance for a specific month and year."""
    year = year if year is not None else datetime.now().year

    if not rikard and not sara:
        rikard = sara = True  # If neither is specified, update both

    with sqlite3.connect(DATABASE_PATH) as conn:
        c = conn.cursor()
        if rikard:
            c.execute('UPDATE allowances SET rikard_allowance = ? WHERE month = ? AND year = ?', (amount, month, year))
        if sara:
            c.execute('UPDATE allowances SET sara_allowance = ? WHERE month = ? AND year = ?', (amount, month, year))
        conn.commit()


@click.command(name='list')
@click.option('--month', type=int, default=None, help="Month to list the allowance for (default: current month)")
@click.option('--year', type=int, default=None, help="Year to list the allowance for (default: current year)")
def list_allowance(month: int | None, year: int | None):
    """List the allowance for the current month and year."""
    year = year if year is not None else datetime.now().year

    with sqlite3.connect(DATABASE_PATH) as conn:
        c = conn.cursor()
        if month is None:
            c.execute('SELECT * FROM allowances WHERE year = ?', (year,))
        else:
            c.execute('SELECT * FROM allowances WHERE month = ? AND year = ?', (month, year))
        
        rows = c.fetchall()

        if not rows:
            click.echo("No allowances found for the specified period.")
            return
        
        r = []
        for row in rows:
            r.append([
                f"{month_no_to_name(row[2])}",  # Month
                f"{row[1]:d}",  # Year
                f"{row[3]:.2f}",  # Rikard Allowance
                f"{row[4]:.2f}"   # Sara Allowance
            ])

        click.echo(generate_table(
            header=["Month", "Year", "Rikard Allowance", "Sara Allowance"],
            rows=r
        ))


@click.command(name='default')
@click.argument('amount', type=float)
@click.option('--rikard', is_flag=True, help="Set the default allowance for Rikard")
@click.option('--sara', is_flag=True, help="Set the default allowance for Sara")
def set_default_allowance(amount: float, rikard: bool, sara: bool):
    """Set the default allowance amount."""
    if rikard:
        with sqlite3.connect(DATABASE_PATH) as conn:
            c = conn.cursor()
            c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('rikard_allowance', amount))
            conn.commit()
    if sara:
        with sqlite3.connect(DATABASE_PATH) as conn:
            c = conn.cursor()
            c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('sara_allowance', amount))
            conn.commit()