import os
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final, TypedDict

import anyio
import uvicorn
from anyio import to_thread
from mcp.server.fastmcp import FastMCP
from mcp.types import ImageContent, TextContent, ToolAnnotations
from starlette.applications import Starlette

from xboxctl import __version__
from xboxctl.auth import validate_auth_tokens
from xboxctl.auth_cli import AuthValidationPayload, auth_validation_payload
from xboxctl.mcp_content import screenshot_content
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

HTTP_HOST: Final = "127.0.0.1"
HTTP_PORT: Final = 3000
HTTP_PATH: Final = "/mcp"
SSE_PATH: Final = "/sse"
MCP_USAGE: Final = (
    "usage: xboxctl-mcp [--http|--sse|--dual-http] [--provider fake|real] "
    "[--host HOST] [--port PORT] [--path PATH] "
    "[--allow-host HOST] [--version]"
)

mcp = FastMCP(
    name="xboxctl",
    log_level="WARNING",
    json_response=True,
    stateless_http=True,
    host=HTTP_HOST,
    port=HTTP_PORT,
    streamable_http_path=HTTP_PATH,
)
selected_provider = ProviderName.REAL
DEFAULT_SESSION_FILE_TEXT: Final = str(DEFAULT_SESSION_FILE)


class McpTransport(StrEnum):
    STDIO = "stdio"
    HTTP = "http"
    SSE = "sse"
    DUAL_HTTP = "dual-http"


TRANSPORT_OPTIONS: Final[dict[str, tuple[McpTransport, str | None]]] = {
    "--http": (McpTransport.HTTP, HTTP_PATH),
    "--sse": (McpTransport.SSE, SSE_PATH),
    "--dual-http": (McpTransport.DUAL_HTTP, None),
}


@dataclass(frozen=True, slots=True)
class McpServerConfig:
    provider: ProviderName = ProviderName.REAL
    transport: McpTransport = McpTransport.STDIO
    host: str = HTTP_HOST
    port: int = HTTP_PORT
    path: str | None = None
    allowed_hosts: tuple[str, ...] = ()


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


class ObserveCleanupPayload(TypedDict):
    message: str
    stopped: bool
    removed: bool
    status: ObserveStatusPayload


def provider() -> XboxProvider:
    return build_provider(selected_provider)


async def run_sync_tool[**P, T](
    function: Callable[P, T],
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    return await to_thread.run_sync(lambda: function(*args, **kwargs))


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
async def xbox_auth_validate() -> AuthValidationPayload:
    return await run_sync_tool(validate_xbox_auth)


def list_xbox_consoles() -> list[ConsolePayload]:
    return [console_payload(console) for console in provider().list_consoles()]


@mcp.tool(
    name="xbox_consoles",
    description="List Xbox consoles for the signed-in account.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
async def xbox_consoles() -> list[ConsolePayload]:
    return await run_sync_tool(list_xbox_consoles)


def get_xbox_status() -> ConsolePayload:
    return console_payload(provider().status())


@mcp.tool(
    name="xbox_status",
    description="Get the current Xbox status.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
async def xbox_status() -> ConsolePayload:
    return await run_sync_tool(get_xbox_status)


def list_xbox_apps() -> list[AppPayload]:
    return [app_payload(app) for app in provider().status().apps]


@mcp.tool(
    name="xbox_apps",
    description="List installed Xbox apps and games.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
async def xbox_apps() -> list[AppPayload]:
    return await run_sync_tool(list_xbox_apps)


def list_xbox_storage() -> list[StoragePayload]:
    return [storage_payload(storage) for storage in provider().status().storage]


@mcp.tool(
    name="xbox_storage",
    description="List Xbox storage devices.",
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
async def xbox_storage() -> list[StoragePayload]:
    return await run_sync_tool(list_xbox_storage)


def launch_xbox(target: str) -> MessagePayload:
    return {"message": provider().launch(target).message}


@mcp.tool(
    name="xbox_launch",
    description="Launch an installed Xbox app or game by name or product ID.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
async def xbox_launch(target: str) -> MessagePayload:
    return await run_sync_tool(launch_xbox, target)


def press_xbox(button: str, repeat: int = 1) -> MessagePayload:
    return {"message": provider().press(button, repeat).message}


@mcp.tool(
    name="xbox_press",
    description="Press an Xbox controller button.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
async def xbox_press(button: str, repeat: int = 1) -> MessagePayload:
    return await run_sync_tool(press_xbox, button=button, repeat=repeat)


def send_xbox_text(text: str) -> MessagePayload:
    return {"message": provider().send_text(text).message}


@mcp.tool(
    name="xbox_text",
    description="Send text input to the Xbox.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
async def xbox_text(text: str) -> MessagePayload:
    return await run_sync_tool(send_xbox_text, text)


@mcp.tool(
    name="xbox_media",
    description="Send a media command: play, pause, next, or previous.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
async def xbox_media(action: MediaAction) -> MessagePayload:
    return await run_sync_tool(lambda: {"message": provider().media(action).message})


@mcp.tool(
    name="xbox_power",
    description="Send a power command: on, off, or reboot.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
)
async def xbox_power(
    action: PowerAction,
    wake_address: str | None = None,
) -> MessagePayload:
    return await run_sync_tool(
        power_xbox, action=action, wake_address=wake_address,
    )


def power_xbox(action: PowerAction, wake_address: str | None = None) -> MessagePayload:
    if wake_address is not None:
        os.environ["XBOXCTL_WAKE_ADDRESS"] = wake_address
    return {"message": provider().power(action).message}


@mcp.tool(
    name="xbox_observe_start",
    description="Start a persistent Remote Play observe session.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
async def xbox_observe_start(
    session_file: str = DEFAULT_SESSION_FILE_TEXT,
    image_format: ObserveCaptureFormat = ObserveCaptureFormat.JPEG,
    width: int = 960,
    quality: int = 72,
    settle_ms: int = 5000,
) -> ObserveStartPayload:
    return await run_sync_tool(
        start_xbox_observe,
        session_file=session_file,
        image_format=image_format,
        width=width,
        quality=quality,
        settle_ms=settle_ms,
    )


def start_xbox_observe(
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
async def xbox_observe_status(
    session_file: str = DEFAULT_SESSION_FILE_TEXT,
) -> ObserveStatusPayload:
    return await run_sync_tool(get_observe_status, session_file)


def get_observe_status(
    session_file: str = DEFAULT_SESSION_FILE_TEXT,
) -> ObserveStatusPayload:
    return observe_status_payload(Path(session_file))


@mcp.tool(
    name="xbox_observe_capture",
    description="Capture a screenshot from a persistent observe session.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
async def xbox_observe_capture(
    output: str | None = None,
    session_file: str = DEFAULT_SESSION_FILE_TEXT,
    image_format: ObserveCaptureFormat = ObserveCaptureFormat.JPEG,
    width: int = 960,
    quality: int = 72,
) -> list[TextContent | ImageContent]:
    return await run_sync_tool(
        capture_xbox_observe_content,
        output=output,
        session_file=session_file,
        image_format=image_format,
        width=width,
        quality=quality,
    )


def capture_xbox_observe_content(
    output: str | None = None,
    session_file: str = DEFAULT_SESSION_FILE_TEXT,
    image_format: ObserveCaptureFormat = ObserveCaptureFormat.JPEG,
    width: int = 960,
    quality: int = 72,
) -> list[TextContent | ImageContent]:
    output_path = capture_xbox_observe(
        output=output,
        session_file=session_file,
        image_format=image_format,
        width=width,
        quality=quality,
    )
    if not output_path.is_file() or output_path.stat().st_size == 0:
        msg = f"Capture did not produce a valid file: {output_path}"
        raise ValueError(msg)

    return screenshot_content(output_path)


def capture_xbox_observe(
    output: str | None = None,
    session_file: str = DEFAULT_SESSION_FILE_TEXT,
    image_format: ObserveCaptureFormat = ObserveCaptureFormat.JPEG,
    width: int = 960,
    quality: int = 72,
) -> Path:
    output_path = (
        Path(tempfile.gettempdir()) / f"xboxctl-screenshot.{image_format.value}"
        if output is None
        else Path(output)
    )
    capture_observe_session(
        session_file=Path(session_file),
        output=output_path,
        capture_format=image_format,
        width=width,
        quality=quality,
    )
    return output_path


@mcp.tool(
    name="xbox_observe_press",
    description="Press a controller button through a persistent observe session.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
)
async def xbox_observe_press(
    button: str,
    repeat: int = 1,
    session_file: str = DEFAULT_SESSION_FILE_TEXT,
) -> MessagePayload:
    return await run_sync_tool(
        press_xbox_observe,
        button=button,
        repeat=repeat,
        session_file=session_file,
    )


def press_xbox_observe(
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
async def xbox_observe_stop(
    session_file: str = DEFAULT_SESSION_FILE_TEXT,
) -> MessagePayload:
    return await run_sync_tool(stop_xbox_observe, session_file)


def stop_xbox_observe(
    session_file: str = DEFAULT_SESSION_FILE_TEXT,
) -> MessagePayload:
    stop_observe_session(Path(session_file))
    return {"message": f"Stopped Xbox observe session: {session_file}."}


@mcp.tool(
    name="xbox_observe_cleanup",
    description="Remove a stale observe session or stop a live one.",
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
)
async def xbox_observe_cleanup(
    session_file: str = DEFAULT_SESSION_FILE_TEXT,
) -> ObserveCleanupPayload:
    return await run_sync_tool(cleanup_observe, session_file)


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


def argument_value(arguments: Sequence[str], index: int, option: str) -> str:
    try:
        return arguments[index + 1]
    except IndexError:
        print(f"{option} requires a value\n{MCP_USAGE}", file=sys.stderr)  # noqa: T201
        raise SystemExit(2) from None


def parse_mcp_config(argv: Sequence[str]) -> McpServerConfig:
    provider_name = ProviderName.REAL
    transport = McpTransport.STDIO
    host = HTTP_HOST
    port = HTTP_PORT
    path: str | None = None
    allowed_hosts: list[str] = []
    index = 0
    while index < len(argv):
        option = argv[index]
        if option in TRANSPORT_OPTIONS:
            transport, default_path = TRANSPORT_OPTIONS[option]
            path = path or default_path
            index += 1
        elif option == "--version":
            print(f"xboxctl {__version__}")  # noqa: T201
            raise SystemExit(0)
        elif option == "--stdio":
            transport = McpTransport.STDIO
            index += 1
        elif option == "--provider":
            provider_name = ProviderName(argument_value(argv, index, option))
            index += 2
        elif option == "--host":
            host = argument_value(argv, index, option)
            index += 2
        elif option == "--port":
            port = int(argument_value(argv, index, option))
            index += 2
        elif option == "--path":
            path = argument_value(argv, index, option)
            index += 2
        elif option == "--allow-host":
            allowed_hosts.append(argument_value(argv, index, option))
            index += 2
        else:
            print(MCP_USAGE, file=sys.stderr)  # noqa: T201
            raise SystemExit(2)
    return McpServerConfig(
        provider=provider_name,
        transport=transport,
        host=host,
        port=port,
        path=path,
        allowed_hosts=tuple(allowed_hosts),
    )


def apply_http_settings(config: McpServerConfig) -> None:
    mcp.settings.host = config.host
    mcp.settings.port = config.port
    transport_security = mcp.settings.transport_security
    if transport_security is None:
        return
    for allowed_host in config.allowed_hosts:
        if allowed_host not in transport_security.allowed_hosts:
            transport_security.allowed_hosts.append(allowed_host)


def run_dual_http_server(config: McpServerConfig) -> None:
    async def serve() -> None:
        apply_http_settings(config)
        mcp.settings.streamable_http_path = HTTP_PATH
        mcp.settings.sse_path = SSE_PATH
        streamable_app = mcp.streamable_http_app()
        sse_app = mcp.sse_app()
        app = Starlette(
            debug=mcp.settings.debug,
            routes=[*streamable_app.routes, *sse_app.routes],
            middleware=streamable_app.user_middleware,
            lifespan=streamable_app.router.lifespan_context,
        )
        server_config = uvicorn.Config(
            app,
            host=config.host,
            port=config.port,
            log_level=mcp.settings.log_level.lower(),
        )
        await uvicorn.Server(server_config).serve()

    anyio.run(serve)


def run_mcp_server(config: McpServerConfig) -> None:
    global selected_provider  # noqa: PLW0603
    selected_provider = config.provider
    match config.transport:
        case McpTransport.STDIO:
            mcp.run()
        case McpTransport.HTTP:
            apply_http_settings(config)
            mcp.settings.streamable_http_path = config.path or HTTP_PATH
            mcp.run(transport="streamable-http")
        case McpTransport.SSE:
            apply_http_settings(config)
            mcp.settings.sse_path = config.path or SSE_PATH
            mcp.run(transport="sse")
        case McpTransport.DUAL_HTTP:
            run_dual_http_server(config)


def main(argv: Sequence[str] | None = None) -> None:
    run_mcp_server(parse_mcp_config(sys.argv[1:] if argv is None else argv))
