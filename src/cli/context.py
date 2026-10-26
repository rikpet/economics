from dataclasses import dataclass, field

import click

import database as db
from app_types import Account


@dataclass
class AppContext:
    """Passed to every command as click's obj: which database and account to work on."""
    database_path: str
    account_name: str | None = None
    _account: Account | None = field(default=None, repr=False)

    @property
    def account(self) -> Account:
        if self._account is None:
            self._account = db.find_account(self.database_path, self.account_name)
            if self._account is None:
                names = ', '.join(a.name for a in db.get_accounts(self.database_path))
                raise click.ClickException(
                    f"Unknown account: {self.account_name!r}. Available accounts: {names}")
        return self._account

    @property
    def account_id(self) -> int:
        return self.account.id


pass_app = click.make_pass_decorator(AppContext)


def category_tree(app: AppContext) -> dict[str, list[str]]:
    """The account's categories as {main: [sub, ...]} in display order."""
    tree: dict[str, list[str]] = {}
    for c in db.get_categories(app.database_path, app.account_id):
        tree.setdefault(c.main_category, []).append(c.sub_category)
    return tree
