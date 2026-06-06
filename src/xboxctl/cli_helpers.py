import json
from typing import NoReturn

import typer
from rich.console import Console as RichConsole

from xboxctl import __version__
from xboxctl.providers.real import ProviderUnavailableError
from xboxctl.serialise import AppPayload, ConsolePayload, McpPayload, StoragePayload

type JsonPayload = (
    McpPayload | list[ConsolePayload] | list[StoragePayload] | list[AppPayload]
)

MIN_REPEAT = 1
MAX_REPEAT = 20
REPEAT_RANGE_ERROR = "repeat must be between 1 and 20"
EMPTY_TEXT_ERROR = "text must not be empty"


def version_callback(value: bool) -> None:
    if value:
        RichConsole().print(f"xboxctl {__version__}")
        raise typer.Exit


def exit_provider_unavailable(error: ProviderUnavailableError) -> NoReturn:
    typer.echo(str(error), err=True)
    raise typer.Exit(1) from error


def require_confirm(confirm: bool) -> None:
    if confirm:
        return
    typer.echo("Add --confirm to run mutating commands.", err=True)
    raise typer.Exit(2)


def require_repeat_range(repeat: int) -> None:
    if MIN_REPEAT <= repeat <= MAX_REPEAT:
        return
    typer.echo(REPEAT_RANGE_ERROR, err=True)
    raise typer.Exit(2)


def require_non_empty_text(value: str) -> str:
    if value.strip():
        return value
    typer.echo(EMPTY_TEXT_ERROR, err=True)
    raise typer.Exit(2)


def print_json(console: RichConsole, payload: JsonPayload) -> None:
    console.print(json.dumps(payload, indent=2))
