from functools import partial
from pathlib import Path
from typing import Annotated, NoReturn

import anyio
import typer
from rich.console import Console as RichConsole
from rich.table import Table

from xboxctl.cli_helpers import print_json, require_confirm
from xboxctl.youtube import (
    DEFAULT_DEVICE_NAME,
    YouTubeLoungeError,
    disconnect_youtube,
    get_youtube_status,
    next_youtube,
    pair_youtube,
    pause_youtube,
    play_youtube_video,
    previous_youtube,
    resume_youtube,
    seek_youtube,
)

youtube_app = typer.Typer(help="YouTube TV pairing and controls.")
console = RichConsole()


def exit_youtube_error(error: YouTubeLoungeError) -> NoReturn:
    typer.echo(str(error), err=True)
    raise typer.Exit(1) from error


@youtube_app.command("pair")
def pair(
    code: Annotated[str, typer.Argument(help="TV code from the YouTube app.")],
    device_name: Annotated[
        str,
        typer.Option("--device-name", help="Name shown in YouTube linked devices."),
    ] = DEFAULT_DEVICE_NAME,
    token_file: Annotated[
        Path | None,
        typer.Option("--token-file", help="Path for the YouTube pairing file."),
    ] = None,
) -> None:
    try:
        result = anyio.run(
            partial(pair_youtube, code, device_name=device_name, token_file=token_file),
        )
    except YouTubeLoungeError as error:
        exit_youtube_error(error)
    target = result.screen_name or "YouTube"
    console.print(f"Paired {target}. Token file: {result.token_file}")


@youtube_app.command("status")
def status(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print JSON output."),
    ] = False,
    device_name: Annotated[
        str,
        typer.Option("--device-name", help="Name shown in YouTube linked devices."),
    ] = DEFAULT_DEVICE_NAME,
    token_file: Annotated[
        Path | None,
        typer.Option("--token-file", help="Path for the YouTube pairing file."),
    ] = None,
) -> None:
    result = anyio.run(
        partial(
            get_youtube_status,
            device_name=device_name,
            token_file=token_file,
        ),
    )
    payload = {
        "paired": result.paired,
        "available": result.available,
        "screen_name": result.screen_name,
        "token_file": str(result.token_file),
        "reason": result.reason,
    }
    if json_output:
        print_json(console, payload)
        return

    table = Table("Paired", "Available", "Screen", "Token file")
    table.add_row(
        str(result.paired),
        "unknown" if result.available is None else str(result.available),
        result.screen_name or "",
        str(result.token_file),
    )
    console.print(table)
    if result.reason:
        console.print(result.reason)


@youtube_app.command("play")
def play(
    video: Annotated[str, typer.Argument(help="YouTube video ID or URL.")],
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="Confirm the requested action."),
    ] = False,
) -> None:
    require_confirm(confirm)
    try:
        result = anyio.run(play_youtube_video, video)
    except YouTubeLoungeError as error:
        exit_youtube_error(error)
    console.print(result.message)


@youtube_app.command("pause")
def pause(
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="Confirm the requested action."),
    ] = False,
) -> None:
    require_confirm(confirm)
    try:
        result = anyio.run(pause_youtube)
    except YouTubeLoungeError as error:
        exit_youtube_error(error)
    console.print(result.message)


@youtube_app.command("resume")
def resume(
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="Confirm the requested action."),
    ] = False,
) -> None:
    require_confirm(confirm)
    try:
        result = anyio.run(resume_youtube)
    except YouTubeLoungeError as error:
        exit_youtube_error(error)
    console.print(result.message)


@youtube_app.command("seek")
def seek(
    seconds: Annotated[float, typer.Argument(help="Time to seek to, in seconds.")],
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="Confirm the requested action."),
    ] = False,
) -> None:
    require_confirm(confirm)
    try:
        result = anyio.run(seek_youtube, seconds)
    except YouTubeLoungeError as error:
        exit_youtube_error(error)
    console.print(result.message)


@youtube_app.command("next")
def next_video(
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="Confirm the requested action."),
    ] = False,
) -> None:
    require_confirm(confirm)
    try:
        result = anyio.run(next_youtube)
    except YouTubeLoungeError as error:
        exit_youtube_error(error)
    console.print(result.message)


@youtube_app.command("previous")
def previous(
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="Confirm the requested action."),
    ] = False,
) -> None:
    require_confirm(confirm)
    try:
        result = anyio.run(previous_youtube)
    except YouTubeLoungeError as error:
        exit_youtube_error(error)
    console.print(result.message)


@youtube_app.command("disconnect")
def disconnect(
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="Confirm the requested action."),
    ] = False,
) -> None:
    require_confirm(confirm)
    try:
        result = anyio.run(disconnect_youtube)
    except YouTubeLoungeError as error:
        exit_youtube_error(error)
    console.print(result.message)
