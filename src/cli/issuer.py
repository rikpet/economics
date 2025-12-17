import click
import questionary
from balance import Balance
from database import get_issuer_classification, get_issuer_classification_by_id, get_issuer_classifications, classify_issuer, modify_issuer_classification, remove_issuer_classification
from app_types import IssuerClassification
from constants import DATABASE_PATH

@click.command(name='list')
def list_issuers():
    """List all issuer classifications."""

    issuers = get_issuer_classifications(DATABASE_PATH)

    if len(issuers) == 0:
        click.echo('No issuers found.')
        return
    
    max_issuer_length = max(len(t[1].issuer) for t in issuers)

    click.echo('Listing issuers:\n')
    click.echo(f'{"ID":<5} | {"ISSUER":<{max_issuer_length + 3}} | {"MAIN CATEGORY":<15} | {"SUB CATEGORY":<15}')
    click.echo('-' * (5 + 3 + max_issuer_length + 3 + 3 + 15 + 3 + 15))
    
    for id, issuer in issuers:
        click.echo(f'{id:<5} | {issuer.issuer:<{max_issuer_length + 3}} | {issuer.main_category:<15} | {issuer.sub_category:<15}')


@click.command(name='add')
def add_issuer():
    """Add a new issuer classification."""
    issuer = click.prompt("Issuer name")

    mock = Balance(2025, 1)

    main_category = click.prompt(
        "Main category",
        type=click.Choice(mock.categories(), case_sensitive=False)
    )
    sub_category = click.prompt(
        "Sub category",
        type=click.Choice(mock.sub_categories(main_category), case_sensitive=False)
    )
    classify_issuer(DATABASE_PATH, IssuerClassification(
        issuer=issuer,
        main_category=main_category,
        sub_category=sub_category
    ))
    click.echo(f'Issuer classification for {issuer} added.')


@click.command(name='remove')
@click.option('--issuer-id', prompt='Issuer ID to remove', type=int)
def remove_issuer(issuer_id: int):
    """Remove an issuer classification by ID."""
    

    remove_issuer_classification(DATABASE_PATH, issuer_id)
    click.echo(f'Issuer classification with ID {issuer_id} removed.')


@click.command(name="modify")
@click.option('--issuer-id', prompt='Issuer ID to modify', type=int)
def modify_issuer(issuer_id: int):
    """Modify an existing issuer classification."""
    mock = Balance(2025, 1)

    issuer = get_issuer_classification_by_id(DATABASE_PATH, issuer_id)
    if issuer is None:
        click.echo(f'Issuer with ID {issuer_id} not found.')
        return

    click.echo(f'Current classification for issuer ID {issuer_id}:')
    click.echo(f'Issuer: {issuer.issuer}, Main Category: {issuer.main_category}, Sub Category: {issuer.sub_category}\n')

    main_category=questionary.select(
            "Main category for this transaction",
            choices=list(mock.categories())
        ).ask()

    sub_category = questionary.select(
            "Sub category for this transaction",
            choices=mock.sub_categories(main_category)
        ).ask()

    modify_issuer_classification(DATABASE_PATH, issuer_id, main_category, sub_category)
    click.echo(f'Issuer classification with ID {issuer_id} modified.')