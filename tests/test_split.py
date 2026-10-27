import io
import re

import pytest
from click.testing import CliRunner

import database as db
import operations
from app import cli
from app_types import SplitPart, Transaction
from budget import budget_table, monthly_balances
from webapp import create_app

SEB_FILE = 'tests/input_data/seb_transactions.csv'


@pytest.fixture
def path(tmp_path):
    p = str(tmp_path / 'split.db')
    db.create_tables(p)
    return p


def receipt(path, account_id=1, amount=-1000.0, vn='SEB_receipt'):
    db.insert_transaction(path, account_id, Transaction('2025-03-10', 'ICA MAXI', amount, 'SEB',
                                                        'mat', 'butik', verification_number=vn))
    return db.get_transactions(path, account_id)[-1].id


def test_split_replaces_the_original(path):
    tid = receipt(path)
    ids = operations.split_transaction(path, 1, tid, [
        SplitPart(-700, 'mat', 'butik'), SplitPart(-300, 'hushåll', 'övrigt', 'lampa')])

    listed = db.get_transactions(path, 1)
    assert sorted(t.id for t in listed) == sorted(ids)
    assert sum(t.amount for t in listed) == -1000
    assert all(t.parent_id == tid and t.issuer == 'ICA MAXI' and t.date == '2025-03-10' for t in listed)
    assert next(t for t in listed if t.amount == -300).comment == 'lampa'

    original = db.get_transaction(path, 1, tid)
    assert original.is_split and 'split into 2 parts' in original.modification_log
    assert db.category_usage(path, 1, 'mat', 'butik') == 1


def test_budget_follows_the_parts(path):
    tid = receipt(path)
    account = db.get_account(path, 1)
    mat = lambda: next(r for r in budget_table(monthly_balances(path, account, 2025))
                       if r.main_category == 'mat').values[2]
    assert mat() == 1000
    operations.split_transaction(path, 1, tid, [SplitPart(-700, 'mat', 'butik'),
                                                SplitPart(-300, 'hushåll', 'övrigt')])
    assert mat() == 700
    operations.unsplit_transaction(path, 1, tid)
    assert mat() == 1000
    assert [t.id for t in db.get_transactions(path, 1)] == [tid]
    assert not db.get_transaction(path, 1, tid).is_split


def test_split_rules(path):
    tid = receipt(path)
    with pytest.raises(ValueError, match='add up to -900.00, not -1000.00'):
        operations.split_transaction(path, 1, tid, [SplitPart(-600), SplitPart(-300)])
    with pytest.raises(ValueError, match='at least two'):
        operations.split_transaction(path, 1, tid, [SplitPart(-1000)])
    with pytest.raises(ValueError, match='needs an amount'):
        operations.split_transaction(path, 1, tid, [SplitPart(-1000), SplitPart(0)])

    # Rounding to öre: 333.33 + 333.33 + 333.34.
    ids = operations.split_transaction(path, 1, tid, [SplitPart(-333.33), SplitPart(-333.33),
                                                      SplitPart(-333.34)])
    # A part cannot itself be split; re-splitting the original replaces the parts.
    with pytest.raises(ValueError, match='change the split of the original'):
        operations.split_transaction(path, 1, ids[0], [SplitPart(-200), SplitPart(-133.33)])
    operations.split_transaction(path, 1, tid, [SplitPart(-500), SplitPart(-500)])
    assert sorted(t.amount for t in db.get_transactions(path, 1)) == [-500, -500]
    assert 're-split' in db.get_transaction(path, 1, tid).modification_log

    # A return inside the purchase goes the other way.
    operations.split_transaction(path, 1, tid, [SplitPart(-1100), SplitPart(100)])

    # Another account can't touch it.
    family = db.create_account(path, 'Familj', 'family')
    with pytest.raises(ValueError, match='No transaction'):
        operations.split_transaction(path, family, tid, [SplitPart(-500), SplitPart(-500)])


def test_unclassified_parts_and_reimport(path):
    first = operations.import_file(path, 1, SEB_FILE, 'seb')
    assert first.added == 8
    original = next(t for t in db.get_transactions(path, 1) if t.amount == -1026)
    operations.split_transaction(path, 1, original.id, [SplitPart(-1000), SplitPart(-26)])

    # The original no longer counts as unclassified; its two parts do.
    assert db.count_unclassified_transactions(path, 1) == 8 - 1 + 2
    # Importing the same file again adds nothing, the split original keeps its number.
    again = operations.import_file(path, 1, SEB_FILE, 'seb')
    assert (again.added, again.skipped_duplicates) == (0, 8)


def test_parse_amount():
    assert operations.parse_amount('1 234,50') == 1234.5
    assert operations.parse_amount('−300 kr') == -300
    assert operations.parse_amount('  ') is None
    with pytest.raises(ValueError):
        operations.parse_amount('tre')


@pytest.fixture
def client(path):
    app = create_app(path)
    app.testing = True
    return app.test_client()


def category_id(path, main, sub):
    return next(c.id for c in db.get_categories(path, 1)
                if c.main_category == main and c.sub_category == sub)


def test_split_in_the_web_ui(client, path):
    tid = receipt(path)
    prefix = '/api/hassio_ingress/abc'
    headers = {'X-Ingress-Path': prefix}

    edit = client.get(f'/1/transactions/{tid}?back=year%3D2025', headers=headers).get_data(as_text=True)
    split_url = re.search(r'href="([^"]*/split[^"]*)"', edit).group(1).replace('&amp;', '&')
    assert split_url == f'{prefix}/1/transactions/{tid}/split?back=year%3D2025'
    split_url = split_url[len(prefix):]

    page = client.get(split_url, headers=headers).get_data(as_text=True)
    assert 'value="1000"' in page  # prefilled with the whole amount, as a positive number

    butik, ovrigt = category_id(path, 'mat', 'butik'), category_id(path, 'hushåll', 'övrigt')
    form = {'amount': ['650,50', '300', ''], 'category': [str(butik), str(ovrigt), ''],
            'comment': ['', 'glödlampor', '']}

    # Not adding up: the form comes back with what was entered.
    bad = dict(form, amount=['650,50', '200', ''])
    response = client.post(split_url, headers=headers, data=bad)
    html = response.get_data(as_text=True)
    assert response.status_code == 200 and 'add up to -850.50' in html and 'value="650,50"' in html
    assert not db.get_transaction(path, 1, tid).is_split

    form['amount'] = ['650,50', '349,50', '']
    response = client.post(split_url, headers=headers, data=form)
    assert response.headers['Location'] == f'{prefix}/1/transactions?year=2025'
    parts = db.get_split_parts(path, 1, tid)
    assert [(p.amount, p.sub_category, p.comment) for p in parts] == [
        (-650.5, 'butik', None), (-349.5, 'övrigt', 'glödlampor')]

    listing = client.get('/1/transactions?year=2025').get_data(as_text=True)
    assert listing.count('>split<') == 2

    # The original's edit page leads to the split; a part links back to it.
    assert client.get(f'/1/transactions/{tid}').headers['Location'].endswith(f'/1/transactions/{tid}/split?back=')
    part_page = client.get(f'/1/transactions/{parts[0].id}').get_data(as_text=True)
    assert f'/1/transactions/{tid}/split' in part_page and 'Split…' not in part_page

    page = client.get(split_url).get_data(as_text=True)
    assert 'value="650,50"' in page and 'value="349,50"' in page and 'Undo split' in page

    client.post(f'/1/transactions/{tid}/unsplit?back=year%3D2025')
    assert not db.get_transaction(path, 1, tid).is_split
    assert db.get_split_parts(path, 1, tid) == []


def test_split_urls_pass_home_assistants_filter(client, path):
    from tests.test_webapp import HA_SECURITY_FILTER
    tid = receipt(path)
    operations.split_transaction(path, 1, tid, [SplitPart(-700), SplitPart(-300)])
    part = db.get_split_parts(path, 1, tid)[0]
    for page in (f'/1/transactions/{tid}/split?back=year%3D2025&month%3D3',
                 f'/1/transactions/{part.id}?back=year%3D2025', '/1/transactions?year=2025'):
        html = client.get(page).get_data(as_text=True)
        for url in re.findall(r'(?:href|action)="([^"]+)"', html):
            assert not HA_SECURITY_FILTER.search(url.replace('&amp;', '&')), (page, url)


def test_split_from_the_command_line(path):
    tid = receipt(path)
    runner = CliRunner()
    result = runner.invoke(cli, ['--db', path, 'trans', 'split', str(tid),
                                 '--part', '700:mat/butik', '--part', '300:hushåll/övrigt:lampa'])
    assert result.exit_code == 0, result.output
    assert sorted(t.amount for t in db.get_transactions(path, 1)) == [-700, -300]

    result = runner.invoke(cli, ['--db', path, 'trans', 'split', str(tid), '--part', '1000:nope/x',
                                 '--part', '0'])
    assert result.exit_code != 0 and 'Unknown category' in result.output

    result = runner.invoke(cli, ['--db', path, 'trans', 'unsplit', str(tid)])
    assert result.exit_code == 0, result.output
    assert [t.amount for t in db.get_transactions(path, 1)] == [-1000]


def test_format_exact():
    from webapp import format_exact
    assert format_exact(-808.26) == '−808,26'
    assert format_exact(1234567) == '1 234 567'
    assert format_exact(0.5) == '0,50'
