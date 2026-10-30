from datetime import datetime

import pytest
from click.testing import CliRunner

import database as db
from cli.allowance import add_allowance, check_allowance, list_allowance
from cli.context import AppContext


@pytest.fixture
def app(tmp_path):
    path = str(tmp_path / 'test.db')
    db.create_tables(path)
    return AppContext(path, 'Rikard')


def test_add_allowance(app):
    runner = CliRunner()
    result = runner.invoke(add_allowance, ['100', '--month', '5', '--year', '2024'], obj=app)
    assert result.exit_code == 0, result.output
    assert "Processing file" not in result.output  # Ensure it doesn't print the file processing message
    rows = db.get_allowances(app.database_path, app.account_id, 2024, 5)
    assert rows[0]['rikard_allowance'] == 100
    assert rows[0]['sara_allowance'] == 100


def test_add_allowance_for_one_person_keeps_the_other(app):
    runner = CliRunner()
    runner.invoke(add_allowance, ['100', '--month', '5', '--year', '2024'], obj=app)
    result = runner.invoke(add_allowance, ['250', '--month', '5', '--year', '2024', '--sara'], obj=app)
    assert result.exit_code == 0, result.output
    row = db.get_allowances(app.database_path, app.account_id, 2024, 5)[0]
    assert row['rikard_allowance'] == 100
    assert row['sara_allowance'] == 250

    result = runner.invoke(list_allowance, ['--year', '2024'], obj=app)
    assert 'May' in result.output and '250' in result.output


def test_add_allowance_without_month(app):
    runner = CliRunner()
    result = runner.invoke(add_allowance, ['100', '--year', '2024'], obj=app)
    assert result.exit_code != 0
    assert "Month must be specified" in result.output

def test_add_allowance_with_invalid_month(app):
    runner = CliRunner()
    result = runner.invoke(add_allowance, ['100', '--month', '13', '--year', '2024'], obj=app)
    assert result.exit_code != 0
    assert "Month must be between 1 and 12" in result.output

    result = runner.invoke(add_allowance, ['100', '--month', '0', '--year', '2024'], obj=app)
    assert result.exit_code != 0
    assert "Month must be between 1 and 12" in result.output

def test_add_allowance_with_invalid_year(app):
    runner = CliRunner()
    result = runner.invoke(add_allowance, ['100', '--month', '5', '--year', '2019'], obj=app)
    assert result.exit_code != 0
    assert "Year must be between 2020 and this year" in result.output

    future_year = str(datetime.now().year + 1)
    result = runner.invoke(add_allowance, ['100', '--month', '5', '--year', future_year], obj=app)
    assert result.exit_code != 0
    assert "Year must be between 2020 and this year" in result.output


def test_check_allowance_uses_defaults_and_does_not_overwrite(app):
    now = datetime.now()
    check_allowance(app)
    assert db.get_allowances(app.database_path, app.account_id, now.year, now.month) == []

    db.set_setting(app.database_path, app.account_id, 'rikard_allowance', '500')
    check_allowance(app)
    row = db.get_allowances(app.database_path, app.account_id, now.year, now.month)[0]
    assert row['rikard_allowance'] == 500
    assert row['sara_allowance'] == 0

    db.set_allowance(app.database_path, app.account_id, now.year, now.month, rikard=42)
    check_allowance(app)
    row = db.get_allowances(app.database_path, app.account_id, now.year, now.month)[0]
    assert row['rikard_allowance'] == 42
