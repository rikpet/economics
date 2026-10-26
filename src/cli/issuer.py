import click
import questionary
from database import get_issuer_classification_by_id, get_issuer_classifications, classify_issuer, modify_issuer_classification, remove_issuer_classification
from app_types import IssuerClassification
from cli.context import AppContext, category_tree, pass_app
from printout import generate_table

@click.command(name='list')
@pass_app
def list_issuers(app: AppContext):
    """List all issuer classifications."""

    issuers = get_issuer_classifications(app.database_path, app.account_id)

    if len(issuers) == 0:
        click.echo('No issuers found.')
        return

    click.echo('Listing issuers:\n')
    click.echo(generate_table(
        header=["ID", "ISSUER", "MAIN CATEGORY", "SUB CATEGORY"],
        rows=[(id, issuer.issuer, issuer.main_category, issuer.sub_category) for id, issuer in issuers]
    ))


@click.command(name='add')
@pass_app
def add_issuer(app: AppContext):
    """Add a new issuer classification."""
    issuer = click.prompt("Issuer name")

    tree = category_tree(app)

    main_category = click.prompt(
        "Main category",
        type=click.Choice(list(tree), case_sensitive=False)
    )
    sub_category = click.prompt(
        "Sub category",
        type=click.Choice(tree[main_category.lower()], case_sensitive=False)
    )
    classify_issuer(app.database_path, app.account_id, IssuerClassification(
        issuer=issuer,
        main_category=main_category,
        sub_category=sub_category
    ))
    click.echo(f'Issuer classification for {issuer} added.')


@click.command(name='remove')
@click.option('--issuer-id', prompt='Issuer ID to remove', type=int)
@pass_app
def remove_issuer(app: AppContext, issuer_id: int):
    """Remove an issuer classification by ID."""
    remove_issuer_classification(app.database_path, app.account_id, issuer_id)
    click.echo(f'Issuer classification with ID {issuer_id} removed.')


@click.command(name="modify")
@click.option('--issuer-id', prompt='Issuer ID to modify', type=int)
@pass_app
def modify_issuer(app: AppContext, issuer_id: int):
    """Modify an existing issuer classification."""
    tree = category_tree(app)

    issuer = get_issuer_classification_by_id(app.database_path, app.account_id, issuer_id)
    if issuer is None:
        click.echo(f'Issuer with ID {issuer_id} not found.')
        return

    click.echo(f'Current classification for issuer ID {issuer_id}:')
    click.echo(f'Issuer: {issuer.issuer}, Main Category: {issuer.main_category}, Sub Category: {issuer.sub_category}\n')

    main_category=questionary.select(
            "Main category for this transaction",
            choices=list(tree)
        ).ask()
    if main_category is None:
        return

    sub_category = questionary.select(
            "Sub category for this transaction",
            choices=tree[main_category]
        ).ask()
    if sub_category is None:
        return

    modify_issuer_classification(app.database_path, app.account_id, issuer_id, main_category, sub_category)
    click.echo(f'Issuer classification with ID {issuer_id} modified.')
