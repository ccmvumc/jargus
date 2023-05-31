import click
import pprint
import logging

from .jargus import Jargus


logging.basicConfig(
    format='%(asctime)s - %(levelname)s:%(name)s:%(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S')

# Top level command line group with global debug option
@click.group()
@click.option('--debug/--no-debug', default=False)
def cli(debug):
    if debug:
        click.echo('jargus! debug')
        logging.getLogger().setLevel(logging.DEBUG)


# update subcommand to update reports database
@cli.command('update')
@click.argument(
    'choice', 
    type=click.Choice(['reports']),
    required=False,
    nargs=-1)
@click.option('--name', '-n', 'name', multiple=True)
def update(choice, name):
    click.echo('jargus! update')
    j = Jargus()
    j.update(names=name, choices=choice)
    click.echo('done!')

# report subcommand to create a local report
@cli.command('report')
@click.option('--name', '-n', 'name', required=True)
def report(name):
    click.echo('jargus! report')
    Jargus().report(name)
