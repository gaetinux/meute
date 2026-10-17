"""The `meute task` command group, shared by the modules that add commands to it."""

import typer

task_app = typer.Typer(no_args_is_help=True, help="Add, list and show tasks.")
