from click.testing import CliRunner

import database as db
from app import cli


def test_accounts_from_the_command_line(tmp_path):
    path = str(tmp_path / 'cli.db')
    runner = CliRunner()

    result = runner.invoke(cli, ['--db', path, 'account', 'add', 'Familj', '--template', 'family'])
    assert result.exit_code == 0, result.output

    result = runner.invoke(cli, ['--db', path, 'account', 'list'])
    assert 'Privat' in result.output and 'Familj' in result.output

    result = runner.invoke(cli, ['--db', path, '--account', 'Familj', 'trans', 'add',
                                 'tests/input_data/seb_transactions.csv', 'SEB'])
    assert result.exit_code == 0, result.output
    assert 'Added 8 transactions' in result.output

    family = db.find_account(path, 'Familj')
    assert len(db.get_transactions(path, family.id)) == 8
    assert db.get_transactions(path, 1) == []

    result = runner.invoke(cli, ['--db', path, '-a', 'Familj', 'category', 'list'])
    assert 'barnbidrag' in result.output

    result = runner.invoke(cli, ['--db', path, '-a', 'Familj', 'balance', '--year', '2025'])
    assert result.exit_code == 0, result.output
    assert 'BUDGET SUMMARY (Familj)' in result.output and 'Boende' in result.output

    result = runner.invoke(cli, ['--db', path, '-a', 'Nope', 'trans', 'list'])
    assert result.exit_code != 0
    assert 'Unknown account' in result.output
