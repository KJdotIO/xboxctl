import json
import subprocess
import sys
from typing import Annotated, NoReturn, TypedDict

import typer

from xboxctl.auth import (
    DEFAULT_AUTH_PORT,
    DEFAULT_AUTH_REDIRECT_URI,
    SETUP_COMMAND,
    AuthPrompt,
    AuthStatus,
    AuthValidation,
    AuthValidationReason,
    RequiredTokenField,
    build_auth_login_config,
    inspect_auth_status,
    validate_auth_tokens,
)
from xboxctl.auth_identity import (
    WhoamiResult,
    XboxIdentityUnavailableError,
    fetch_whoami,
)


class AuthStatusPayload(TypedDict):
    configured: bool
    tokens_file: str
    setup_command: str
    note: str


class AuthValidationPayload(TypedDict):
    valid: bool
    reason: str
    tokens_file: str
    missing_fields: list[RequiredTokenField]
    can_attempt_real_provider: bool
    setup_command: str
    note: str


class WhoamiPayload(TypedDict):
    xuid: str
    gamertag: str | None
    modern_gamertag: str | None
    unique_modern_gamertag: str | None
    gamerscore: str | None
    account_tier: str | None
    note: str


auth_app = typer.Typer(
    help="Real-provider authentication setup.",
    no_args_is_help=True,
)


def auth_status_payload(status: AuthStatus) -> AuthStatusPayload:
    note = (
        "Token file found, but tokens are not validated yet."
        if status.configured
        else "Token file not found. Run the setup command before using real mode."
    )
    return {
        "configured": status.configured,
        "tokens_file": str(status.tokens_file),
        "setup_command": SETUP_COMMAND,
        "note": note,
    }


def auth_validation_payload(validation: AuthValidation) -> AuthValidationPayload:
    match validation.reason:
        case AuthValidationReason.OK:
            note = "Token file has the expected python-xbox OAuth token shape."
        case AuthValidationReason.MISSING_FILE:
            note = "Token file not found. Run the setup command before using real mode."
        case AuthValidationReason.MALFORMED_JSON:
            note = "Token file is not valid JSON. Re-run authentication."
        case AuthValidationReason.MISSING_FIELDS:
            note = "Token file is missing required OAuth fields. Re-run authentication."
    return {
        "valid": validation.valid,
        "reason": validation.reason.value,
        "tokens_file": str(validation.tokens_file),
        "missing_fields": list(validation.missing_fields),
        "can_attempt_real_provider": validation.can_attempt_real_provider,
        "setup_command": SETUP_COMMAND,
        "note": note,
    }


def whoami_payload(result: WhoamiResult) -> WhoamiPayload:
    return {
        "xuid": result.xuid,
        "gamertag": result.gamertag,
        "modern_gamertag": result.modern_gamertag,
        "unique_modern_gamertag": result.unique_modern_gamertag,
        "gamerscore": result.gamerscore,
        "account_tier": result.account_tier,
        "note": "Read-only Xbox profile summary. No console command was sent.",
    }


def exit_missing_auth() -> NoReturn:
    raise typer.Exit(1)


def print_auth_handoff(command: str) -> None:
    typer.echo("Microsoft sign-in is required to create the Xbox token file.")
    typer.echo("The browser will ask you to choose the Microsoft account to use.")
    typer.echo("Approve Xbox Live access after choosing the correct account.")
    typer.echo("No console command was sent.")
    typer.echo(f"Helper command: {command}")


def run_auth_helper(command: tuple[str, ...]) -> int:
    result = subprocess.run(command, check=False)  # noqa: S603
    return result.returncode


@auth_app.command("status")
def status(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print JSON output."),
    ] = False,
) -> None:
    payload = auth_status_payload(inspect_auth_status())
    if json_output:
        typer.echo(json.dumps(payload, indent=2))
    else:
        typer.echo(payload["note"])
        typer.echo(f"Token file: {payload['tokens_file']}")
        typer.echo(f"Setup: {payload['setup_command']}")
    if not payload["configured"]:
        exit_missing_auth()


@auth_app.command("login")
def login(
    client_id: Annotated[
        str | None,
        typer.Option("--client-id", help="Optional Microsoft OAuth client ID."),
    ] = None,
    redirect_uri: Annotated[
        str,
        typer.Option("--redirect-uri", help="OAuth redirect URI."),
    ] = DEFAULT_AUTH_REDIRECT_URI,
    port: Annotated[
        int,
        typer.Option("--port", help="Local callback server port."),
    ] = DEFAULT_AUTH_PORT,
    prompt: Annotated[
        AuthPrompt,
        typer.Option("--prompt", help="Microsoft sign-in prompt behaviour."),
    ] = AuthPrompt.SELECT_ACCOUNT,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print the handoff without running auth."),
    ] = False,
) -> None:
    config = build_auth_login_config(
        client_id=client_id,
        redirect_uri=redirect_uri,
        port=port,
        prompt=prompt,
    )
    print_auth_handoff(config.display_command())
    if dry_run:
        return
    typer.echo("Opening the Microsoft sign-in flow now.")
    exit_code = run_auth_helper(config.helper_command(executable=sys.executable))
    if exit_code != 0:
        raise typer.Exit(exit_code)
    typer.echo("Authentication helper finished. Next: uv run xboxctl auth validate")


@auth_app.command("validate")
def validate(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print JSON output."),
    ] = False,
) -> None:
    payload = auth_validation_payload(validate_auth_tokens())
    if json_output:
        typer.echo(json.dumps(payload, indent=2))
    else:
        typer.echo(payload["note"])
        typer.echo(f"Token file: {payload['tokens_file']}")
        if payload["missing_fields"]:
            typer.echo(f"Missing fields: {', '.join(payload['missing_fields'])}")
        typer.echo(f"Can attempt real provider: {payload['can_attempt_real_provider']}")
    if not payload["valid"]:
        exit_missing_auth()


@auth_app.command("whoami")
def whoami(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print JSON output."),
    ] = False,
) -> None:
    validation = validate_auth_tokens()
    if not validation.valid:
        payload = auth_validation_payload(validation)
        if json_output:
            typer.echo(json.dumps(payload, indent=2))
        else:
            typer.echo(payload["note"])
            typer.echo(f"Token file: {payload['tokens_file']}")
        exit_missing_auth()

    try:
        payload = whoami_payload(fetch_whoami(validation.tokens_file))
    except XboxIdentityUnavailableError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error

    if json_output:
        typer.echo(json.dumps(payload, indent=2))
    else:
        typer.echo(payload["note"])
        typer.echo(f"XUID: {payload['xuid']}")
        if payload["gamertag"] is not None:
            typer.echo(f"Gamertag: {payload['gamertag']}")
        if payload["unique_modern_gamertag"] is not None:
            typer.echo(f"Modern gamertag: {payload['unique_modern_gamertag']}")


@auth_app.command("instructions")
def instructions() -> None:
    typer.echo("1. Install the optional real-provider tools:")
    typer.echo("   uv sync --extra real")
    typer.echo("2. Start Microsoft sign-in and approve Xbox Live access:")
    typer.echo("   uv run xboxctl auth login")
    typer.echo("3. If you use your own Microsoft OAuth app, pass its client ID:")
    typer.echo("   uv run xboxctl auth login --client-id <client-id>")
    typer.echo(f"4. The default redirect URI is: {DEFAULT_AUTH_REDIRECT_URI}")
    typer.echo("5. Check the local token file without reading it:")
    typer.echo("   uv run xboxctl auth status")
    typer.echo("6. Validate the local token shape:")
    typer.echo("   uv run xboxctl auth validate")
    typer.echo("7. Check which Xbox account the token belongs to:")
    typer.echo("   uv run xboxctl auth whoami")
