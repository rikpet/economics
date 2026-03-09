from datetime import datetime

from click.testing import CliRunner
from cli.allowance import add_allowance

def test_add_allowance():
    runner = CliRunner()
    result = runner.invoke(add_allowance, ['100', '--month', '5', '--year', '2024'])
    assert result.exit_code == 0
    assert "Processing file" not in result.output  # Ensure it doesn't print the file processing message

def test_add_allowance_without_month():
    runner = CliRunner()
    result = runner.invoke(add_allowance, ['100', '--year', '2024'])
    assert result.exit_code != 0
    assert "Month must be specified" in result.output

def test_add_allowance_with_invalid_month():
    runner = CliRunner()
    result = runner.invoke(add_allowance, ['100', '--month', '13', '--year', '2024'])
    assert result.exit_code != 0
    assert "Month must be between 1 and 12" in result.output

    result = runner.invoke(add_allowance, ['100', '--month', '0', '--year', '2024'])
    assert result.exit_code != 0
    assert "Month must be between 1 and 12" in result.output

def test_add_allowance_with_invalid_year():
    runner = CliRunner()
    result = runner.invoke(add_allowance, ['100', '--month', '5', '--year', '2019'])
    assert result.exit_code != 0
    assert "Year must be between 2020 and this year" in result.output

    future_year = str(datetime.now().year + 1)
    result = runner.invoke(add_allowance, ['100', '--month', '5', '--year', future_year])
    assert result.exit_code != 0
    assert "Year must be between 2020 and this year" in result.output