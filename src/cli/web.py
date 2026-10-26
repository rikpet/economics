import click

from cli.context import AppContext, pass_app


@click.command(name='web')
@click.option('--host', default='127.0.0.1', show_default=True, help="Interface to listen on.")
@click.option('--port', default=8100, show_default=True, type=int, help="Port to listen on.")
@pass_app
def web(app: AppContext, host, port):
    """Start the web interface."""
    from waitress import serve

    from webapp import create_app

    click.echo(f'Serving on http://{host}:{port}')
    serve(create_app(app.database_path), host=host, port=port)
