from typing import Annotated

import typer
from rich.console import Console as RichConsole
from rich.table import Table

from xboxctl import __version__
from xboxctl.auth import SETUP_COMMAND, validate_auth_tokens
from xboxctl.auth_cli import auth_app
from xboxctl.cli_helpers import (
    exit_provider_unavailable,
    print_json,
    require_confirm,
    require_non_empty_text,
    require_repeat_range,
    version_callback,
)
from xboxctl.models import MediaAction, PowerAction
from xboxctl.observe_cli import observe_app
from xboxctl.providers.app_resolution import AmbiguousAppError, AppNotFoundError
from xboxctl.providers.base import XboxProvider
from xboxctl.providers.network import LocalRouteError, preferred_local_ip_for_remote
from xboxctl.providers.real import ProviderUnavailableError
from xboxctl.providers.select import ProviderName, build_provider
from xboxctl.serialise import (
    McpPayload,
    app_payload,
    console_payload,
    storage_payload,
)

app = typer.Typer(
    help="Xbox CLI controls.",
    no_args_is_help=True,
)
mcp_app = typer.Typer(help="Machine-readable command descriptions.")
app.add_typer(mcp_app, name="mcp")
app.add_typer(auth_app, name="auth")
app.add_typer(observe_app, name="observe")
console = RichConsole()
DEFAULT_PROVIDER = ProviderName.REAL
selected_provider = DEFAULT_PROVIDER


@app.callback()
def main(
    _version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=version_callback,
            help="Show the installed version.",
            is_eager=True,
        ),
    ] = False,
    provider_name: Annotated[
        ProviderName,
        typer.Option(
            "--provider",
            envvar="XBOXCTL_PROVIDER",
            help="Advanced: select a provider backend. Use fake for local tests.",
        ),
    ] = DEFAULT_PROVIDER,
) -> None:
    global selected_provider  # noqa: PLW0603
    selected_provider = provider_name


def current_provider() -> XboxProvider:
    return build_provider(selected_provider)


@app.command()
def consoles() -> None:
    table = Table("Name", "Power", "Active title")
    try:
        consoles_list = current_provider().list_consoles()
    except ProviderUnavailableError as error:
        exit_provider_unavailable(error)
    for item in consoles_list:
        table.add_row(item.name, item.power_state.value, item.active_title)
    console.print(table)


@app.command()
def status(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print JSON output."),
    ] = False,
) -> None:
    try:
        payload = console_payload(current_provider().status())
    except ProviderUnavailableError as error:
        exit_provider_unavailable(error)
    if json_output:
        print_json(console, [payload])
        return
    table = Table("Name", "Power", "Active title")
    table.add_row(payload["name"], payload["power_state"], payload["active_title"])
    console.print(table)


@app.command()
def storage(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print JSON output."),
    ] = False,
) -> None:
    try:
        items = [storage_payload(item) for item in current_provider().status().storage]
    except ProviderUnavailableError as error:
        exit_provider_unavailable(error)
    if json_output:
        print_json(console, items)
        return
    table = Table("Device", "Used GB", "Total GB")
    for item in items:
        table.add_row(item["name"], str(item["used_gb"]), str(item["total_gb"]))
    console.print(table)


@app.command()
def apps(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print JSON output."),
    ] = False,
) -> None:
    try:
        items = [app_payload(item) for item in current_provider().status().apps]
    except ProviderUnavailableError as error:
        exit_provider_unavailable(error)
    if json_output:
        print_json(console, items)
        return
    table = Table("Name", "Product ID", "Running")
    for item in items:
        table.add_row(item["name"], item["product_id"], str(item["running"]))
    console.print(table)


@app.command()
def launch(
    target: Annotated[str, typer.Argument(help="App name or product ID.")],
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="Confirm the requested action."),
    ] = False,
) -> None:
    require_confirm(confirm)
    try:
        action = current_provider().launch(target)
    except (AmbiguousAppError, AppNotFoundError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    except ProviderUnavailableError as error:
        exit_provider_unavailable(error)
    console.print(action.message)


@app.command()
def press(
    button: Annotated[str, typer.Argument(help="Controller button name.")],
    repeat: Annotated[int, typer.Option("--repeat")] = 1,
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="Confirm the requested action."),
    ] = False,
) -> None:
    require_confirm(confirm)
    require_repeat_range(repeat)
    try:
        action = current_provider().press(button, repeat)
    except ProviderUnavailableError as error:
        exit_provider_unavailable(error)
    console.print(action.message)


@app.command()
def doctor(
    console_ip: Annotated[
        str | None,
        typer.Option("--console-ip", help="Console LAN IP for route diagnostics."),
    ] = None,
) -> None:
    validation = validate_auth_tokens()
    if selected_provider == ProviderName.FAKE:
        typer.echo("Mode: fake provider")
    typer.echo(f"Auth token file: {validation.tokens_file}")
    typer.echo(f"Auth token shape: {validation.reason.value}")
    if not validation.valid:
        typer.echo(f"Auth setup: {SETUP_COMMAND}")
    if console_ip is None:
        typer.echo("Preferred local IP: not checked")
        return
    try:
        local_ip = preferred_local_ip_for_remote(console_ip)
    except LocalRouteError as error:
        typer.echo(f"Preferred local IP: {error}")
        return
    typer.echo(f"Preferred local IP: {local_ip}")


@app.command()
def text(
    value: Annotated[str, typer.Argument(help="Text to send.")],
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="Confirm the requested action."),
    ] = False,
) -> None:
    require_confirm(confirm)
    text_value = require_non_empty_text(value)
    try:
        action = current_provider().send_text(text_value)
    except ProviderUnavailableError as error:
        exit_provider_unavailable(error)
    console.print(action.message)


@app.command()
def media(
    action: Annotated[MediaAction, typer.Argument(help="Media action.")],
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="Confirm the requested action."),
    ] = False,
) -> None:
    require_confirm(confirm)
    try:
        provider_action = current_provider().media(action)
    except ProviderUnavailableError as error:
        exit_provider_unavailable(error)
    console.print(provider_action.message)


@app.command()
def power(
    action: Annotated[PowerAction, typer.Argument(help="Power action.")],
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="Confirm the requested action."),
    ] = False,
) -> None:
    require_confirm(confirm)
    try:
        provider_action = current_provider().power(action)
    except ProviderUnavailableError as error:
        exit_provider_unavailable(error)
    console.print(provider_action.message)


@mcp_app.command("describe")
def mcp_describe() -> None:
    manifest: McpPayload = {
        "name": "xboxctl",
        "version": __version__,
        "commands": [
            {"command": "consoles", "requires_confirm": False},
            {"command": "status", "requires_confirm": False},
            {"command": "storage", "requires_confirm": False},
            {"command": "apps", "requires_confirm": False},
            {"command": "auth", "requires_confirm": False},
            {"command": "launch", "requires_confirm": True},
            {"command": "press", "requires_confirm": True},
            {"command": "text", "requires_confirm": True},
            {"command": "media", "requires_confirm": True},
            {"command": "power", "requires_confirm": True},
            {"command": "observe", "requires_confirm": False},
        ],
    }
    if selected_provider == ProviderName.FAKE:
        manifest["provider"] = selected_provider.value
    print_json(console, manifest)
