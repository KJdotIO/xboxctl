import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final, TypedDict

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from xboxctl import __version__
from xboxctl.auth import validate_auth_tokens
from xboxctl.auth_cli import AuthValidationPayload, auth_validation_payload
from xboxctl.models import MediaAction, PowerAction
from xboxctl.observe import ObserveCaptureFormat
from xboxctl.observe_session import (
    DEFAULT_SESSION_FILE,
    DEFAULT_SESSION_IDLE_TIMEOUT_SECONDS,
    DEFAULT_SESSION_START_TIMEOUT_SECONDS,
    ObserveStartSessionRequest,
    capture_observe_session,
    cleanup_observe_session,
    press_observe_session,
    start_observe_session,
    status_observe_session,
    stop_observe_session,
)
from xboxctl.providers.base import XboxProvider
from xboxctl.providers.select import ProviderName, build_provider
from xboxctl.serialise import (
    AppPayload,
    ConsolePayload,
    StoragePayload,
    app_payload,
    console_payload,
    storage_payload,
)

mcp = FastMCP(name="xboxctl")
selected_provider = ProviderName.REAL
DEFAULT_SESSION_FILE_TEXT: Final = str(DEFAULT_SESSION_FILE)
MCP_USAGE: Final = "usage: xboxctl-mcp [--provider fake|real] [--version]"


class MessagePayload(TypedDict):
    message: str


class ObserveStartPayload(TypedDict):
    message: str
    session_file: str
    pid: int
    port: int


class ObserveStatusPayload(TypedDict):
    session_file: str
    exists: bool
    active: bool
    pid: int | None
    port: int | None
    reason: str | None


class ObserveCapturePayload(TypedDict):
    message: str
    output: str


class ObserveCleanupPayload(TypedDict):
    message: str
    stopped: bool
    removed: bool
    status: ObserveStatusPayload


def provider() -> XboxProvider:
    return build_provider(selected_provider)


def observe_status_payload(session_file: Path) -> ObserveStatusPayload:
    status = status_observe_session(session_file)
    return {
        "session_file": str(status.session_file),
        "exists": status.exists,
        "active": status.active,
        "pid": status.pid,
        "port": status.port,
        "reason": status.reason,
    }


def validate_xbox_auth() -> AuthValidationPayload:
    return auth_validation_payload(validate_auth_tokens())


@mcp.tool(
    name="xbox_auth_validate",
    description="Check whether Xbox authentication is ready.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
def xbox_auth_validate() -> AuthValidationPayload:
    return validate_xbox_auth()


def list_xbox_consoles() -> list[ConsolePayload]:
    return [console_payload(console) for console in provider().list_consoles()]


@mcp.tool(
    name="xbox_consoles",
    description="List Xbox consoles for the signed-in account.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
def xbox_consoles() -> list[ConsolePayload]:
    return list_xbox_consoles()


def get_xbox_status() -> ConsolePayload:
    return console_payload(provider().status())


@mcp.tool(
    name="xbox_status",
    description="Get the current Xbox status.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
def xbox_status() -> ConsolePayload:
    return get_xbox_status()


def list_xbox_apps() -> list[AppPayload]:
    return [app_payload(app) for app in provider().status().apps]


@mcp.tool(
    name="xbox_apps",
    description="List installed Xbox apps and games.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
def xbox_apps() -> list[AppPayload]:
    return list_xbox_apps()


def list_xbox_storage() -> list[StoragePayload]:
    return [storage_payload(storage) for storage in provider().status().storage]


@mcp.tool(
    name="xbox_storage",
    description="List Xbox storage devices.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
def xbox_storage() -> list[StoragePayload]:
    return list_xbox_storage()


def launch_xbox(target: str) -> MessagePayload:
    return {"message": provider().launch(target).message}


@mcp.tool(
    name="xbox_launch",
    description="Launch an installed Xbox app or game by name or product ID.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def xbox_launch(target: str) -> MessagePayload:
    return launch_xbox(target)


def press_xbox(button: str, repeat: int = 1) -> MessagePayload:
    return {"message": provider().press(button, repeat).message}


@mcp.tool(
    name="xbox_press",
    description="Press an Xbox controller button.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def xbox_press(button: str, repeat: int = 1) -> MessagePayload:
    return press_xbox(button=button, repeat=repeat)


def send_xbox_text(text: str) -> MessagePayload:
    return {"message": provider().send_text(text).message}


@mcp.tool(
    name="xbox_text",
    description="Send text input to the Xbox.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def xbox_text(text: str) -> MessagePayload:
    return send_xbox_text(text)


@mcp.tool(
    name="xbox_media",
    description="Send a media command: play, pause, next, or previous.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def xbox_media(action: MediaAction) -> MessagePayload:
    return {"message": provider().media(action).message}


@mcp.tool(
    name="xbox_power",
    description="Send a power command: on, off, or reboot.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
)
def xbox_power(action: PowerAction) -> MessagePayload:
    return {"message": provider().power(action).message}


@mcp.tool(
    name="xbox_observe_start",
    description="Start a persistent Remote Play observe session.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def xbox_observe_start(
    session_file: str = DEFAULT_SESSION_FILE_TEXT,
    image_format: ObserveCaptureFormat = ObserveCaptureFormat.JPEG,
    width: int = 960,
    quality: int = 72,
    settle_ms: int = 5000,
) -> ObserveStartPayload:
    path = Path(session_file)
    info = start_observe_session(
        ObserveStartSessionRequest(
            session_file=path,
            capture_format=image_format,
            width=width,
            quality=quality,
            settle_ms=settle_ms,
            timeout_seconds=DEFAULT_SESSION_START_TIMEOUT_SECONDS,
            idle_timeout_seconds=DEFAULT_SESSION_IDLE_TIMEOUT_SECONDS,
        ),
    )
    return {
        "message": f"Started Xbox observe session on 127.0.0.1:{info.port}.",
        "session_file": str(path),
        "pid": info.pid,
        "port": info.port,
    }


@mcp.tool(
    name="xbox_observe_status",
    description="Check a persistent Remote Play observe session.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
def xbox_observe_status(
    session_file: str = DEFAULT_SESSION_FILE_TEXT,
) -> ObserveStatusPayload:
    return get_observe_status(session_file)


def get_observe_status(
    session_file: str = DEFAULT_SESSION_FILE_TEXT,
) -> ObserveStatusPayload:
    return observe_status_payload(Path(session_file))


@mcp.tool(
    name="xbox_observe_capture",
    description="Capture a screenshot from a persistent observe session.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def xbox_observe_capture(
    output: str,
    session_file: str = DEFAULT_SESSION_FILE_TEXT,
    image_format: ObserveCaptureFormat = ObserveCaptureFormat.JPEG,
    width: int = 960,
    quality: int = 72,
) -> ObserveCapturePayload:
    output_path = Path(output)
    capture_observe_session(
        session_file=Path(session_file),
        output=output_path,
        capture_format=image_format,
        width=width,
        quality=quality,
    )
    return {"message": f"Wrote Xbox screenshot to {output_path}.", "output": output}


@mcp.tool(
    name="xbox_observe_press",
    description="Press a controller button through a persistent observe session.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def xbox_observe_press(
    button: str,
    repeat: int = 1,
    session_file: str = DEFAULT_SESSION_FILE_TEXT,
) -> MessagePayload:
    press_observe_session(session_file=Path(session_file), button=button, repeat=repeat)
    suffix = "time" if repeat == 1 else "times"
    return {"message": f"Pressed {button} {repeat} {suffix}."}


@mcp.tool(
    name="xbox_observe_stop",
    description="Stop a persistent Remote Play observe session.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
def xbox_observe_stop(
    session_file: str = DEFAULT_SESSION_FILE_TEXT,
) -> MessagePayload:
    stop_observe_session(Path(session_file))
    return {"message": f"Stopped Xbox observe session: {session_file}."}


@mcp.tool(
    name="xbox_observe_cleanup",
    description="Remove a stale observe session or stop a live one.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
)
def xbox_observe_cleanup(
    session_file: str = DEFAULT_SESSION_FILE_TEXT,
) -> ObserveCleanupPayload:
    return cleanup_observe(session_file)


def cleanup_observe(
    session_file: str = DEFAULT_SESSION_FILE_TEXT,
) -> ObserveCleanupPayload:
    result = cleanup_observe_session(Path(session_file))
    if not result.status.exists:
        message = f"No observe session to clean: {session_file}."
    elif result.stopped:
        message = f"Stopped Xbox observe session: {session_file}."
    else:
        message = f"Removed stale observe session: {session_file}."
    return {
        "message": message,
        "stopped": result.stopped,
        "removed": result.removed,
        "status": observe_status_payload(Path(session_file)),
    }


def provider_from_args(argv: Sequence[str]) -> ProviderName:
    match tuple(argv):
        case ():
            return ProviderName.REAL
        case ("--version",):
            print(f"xboxctl {__version__}")  # noqa: T201
            raise SystemExit(0)
        case ("--provider", provider_value):
            return ProviderName(provider_value)
        case _:
            print(MCP_USAGE, file=sys.stderr)  # noqa: T201
            raise SystemExit(2)


def main(argv: Sequence[str] | None = None) -> None:
    global selected_provider  # noqa: PLW0603
    selected_provider = provider_from_args(sys.argv[1:] if argv is None else argv)
    mcp.run()
