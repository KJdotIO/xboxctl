from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console as RichConsole

from xboxctl.observe import (
    DEFAULT_JPEG_QUALITY,
    DEFAULT_SETTLE_MS,
    OBSERVE_TIMEOUT_SECONDS,
    ObserveCaptureFormat,
    ObserveError,
    ObserveFlowRequest,
    ObserveScreenshotRequest,
    capture_observe_flow,
    capture_observe_screenshot,
    observe_command,
    observe_flow_command,
)
from xboxctl.observe_session import (
    DEFAULT_SESSION_FILE,
    DEFAULT_SESSION_IDLE_TIMEOUT_SECONDS,
    DEFAULT_SESSION_START_TIMEOUT_SECONDS,
    ObserveSessionError,
    ObserveStartSessionRequest,
    capture_observe_session,
    cleanup_observe_session,
    observe_start_command,
    press_observe_session,
    start_observe_session,
    status_observe_session,
    stop_observe_session,
)

observe_app = typer.Typer(help="Experimental Remote Play observation commands.")
console = RichConsole()
DEFAULT_OBSERVE_OUTPUT = Path("xbox-observe.png")


@observe_app.command("screenshot")
def screenshot(  # noqa: PLR0913
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="PNG path to write."),
    ] = DEFAULT_OBSERVE_OUTPUT,
    server_id: Annotated[
        str | None,
        typer.Option("--server-id", help="xHome console server ID."),
    ] = None,
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="Capture timeout in seconds."),
    ] = OBSERVE_TIMEOUT_SECONDS,
    capture_format: Annotated[
        ObserveCaptureFormat,
        typer.Option("--format", help="Image format to write."),
    ] = ObserveCaptureFormat.PNG,
    width: Annotated[
        int | None,
        typer.Option("--width", min=1, help="Resize capture to this pixel width."),
    ] = None,
    quality: Annotated[
        int,
        typer.Option(
            "--quality",
            min=1,
            max=100,
            help="JPEG quality from 1 to 100.",
        ),
    ] = DEFAULT_JPEG_QUALITY,
    settle_ms: Annotated[
        int,
        typer.Option(
            "--settle-ms",
            min=0,
            help="Milliseconds to wait after Remote Play starts before capture.",
        ),
    ] = DEFAULT_SETTLE_MS,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print the helper command without running it."),
    ] = False,
) -> None:
    request = ObserveScreenshotRequest(
        output=output,
        server_id=server_id,
        timeout_seconds=timeout,
        capture_format=capture_format,
        width=width,
        quality=quality,
        settle_ms=settle_ms,
    )
    if dry_run:
        typer.echo(" ".join(observe_command(request)))
        return
    try:
        capture_observe_screenshot(request)
    except ObserveError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    console.print(f"Wrote Xbox screenshot to {output}.")


@observe_app.command("flow")
def flow(  # noqa: PLR0913
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", "-o", help="Directory to write captured frames."),
    ],
    step: Annotated[
        list[str],
        typer.Option(
            "--step",
            help="Flow step: capture:name, press:button[:repeat], or wait:ms.",
        ),
    ],
    server_id: Annotated[
        str | None,
        typer.Option("--server-id", help="xHome console server ID."),
    ] = None,
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="Flow timeout in seconds."),
    ] = OBSERVE_TIMEOUT_SECONDS,
    capture_format: Annotated[
        ObserveCaptureFormat,
        typer.Option("--format", help="Image format to write."),
    ] = ObserveCaptureFormat.PNG,
    width: Annotated[
        int | None,
        typer.Option("--width", min=1, help="Resize captures to this pixel width."),
    ] = None,
    quality: Annotated[
        int,
        typer.Option(
            "--quality",
            min=1,
            max=100,
            help="JPEG quality from 1 to 100.",
        ),
    ] = DEFAULT_JPEG_QUALITY,
    settle_ms: Annotated[
        int,
        typer.Option(
            "--settle-ms",
            min=0,
            help="Milliseconds to wait after Remote Play starts before running steps.",
        ),
    ] = DEFAULT_SETTLE_MS,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print the helper command without running it."),
    ] = False,
) -> None:
    request = ObserveFlowRequest(
        output_dir=output_dir,
        steps=tuple(step),
        server_id=server_id,
        timeout_seconds=timeout,
        capture_format=capture_format,
        width=width,
        quality=quality,
        settle_ms=settle_ms,
    )
    if dry_run:
        typer.echo(" ".join(observe_flow_command(request)))
        return
    try:
        capture_observe_flow(request)
    except ObserveError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    console.print(f"Wrote Xbox flow captures to {output_dir}.")


@observe_app.command("start")
def start(  # noqa: PLR0913
    session_file: Annotated[
        Path,
        typer.Option("--session-file", help="Path to write session details."),
    ] = DEFAULT_SESSION_FILE,
    server_id: Annotated[
        str | None,
        typer.Option("--server-id", help="xHome console server ID."),
    ] = None,
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="Session start timeout in seconds."),
    ] = DEFAULT_SESSION_START_TIMEOUT_SECONDS,
    idle_timeout: Annotated[
        int,
        typer.Option("--idle-timeout", help="Auto-stop after idle seconds."),
    ] = DEFAULT_SESSION_IDLE_TIMEOUT_SECONDS,
    capture_format: Annotated[
        ObserveCaptureFormat,
        typer.Option("--format", help="Default capture image format."),
    ] = ObserveCaptureFormat.PNG,
    width: Annotated[
        int | None,
        typer.Option("--width", min=1, help="Default capture pixel width."),
    ] = None,
    quality: Annotated[
        int,
        typer.Option("--quality", min=1, max=100, help="Default JPEG quality."),
    ] = DEFAULT_JPEG_QUALITY,
    settle_ms: Annotated[
        int,
        typer.Option("--settle-ms", min=0, help="Initial settle wait in milliseconds."),
    ] = DEFAULT_SETTLE_MS,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print the helper command without running it."),
    ] = False,
) -> None:
    request = ObserveStartSessionRequest(
        session_file=session_file,
        server_id=server_id,
        timeout_seconds=timeout,
        capture_format=capture_format,
        width=width,
        quality=quality,
        settle_ms=settle_ms,
        idle_timeout_seconds=idle_timeout,
    )
    if dry_run:
        typer.echo(" ".join(observe_start_command(request)))
        return
    try:
        info = start_observe_session(request)
    except (ObserveError, ObserveSessionError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    message = (
        f"Started Xbox observe session on 127.0.0.1:{info.port}. "
        f"Session file: {session_file}"
    )
    console.print(message)


@observe_app.command("capture")
def capture(
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Image path to write."),
    ],
    session_file: Annotated[
        Path,
        typer.Option("--session-file", help="Path to session details."),
    ] = DEFAULT_SESSION_FILE,
    capture_format: Annotated[
        ObserveCaptureFormat | None,
        typer.Option("--format", help="Override capture image format."),
    ] = None,
    width: Annotated[
        int | None,
        typer.Option("--width", min=1, help="Override capture pixel width."),
    ] = None,
    quality: Annotated[
        int | None,
        typer.Option("--quality", min=1, max=100, help="Override JPEG quality."),
    ] = None,
) -> None:
    try:
        capture_observe_session(
            session_file=session_file,
            output=output,
            capture_format=capture_format,
            width=width,
            quality=quality,
        )
    except (ObserveError, ObserveSessionError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    console.print(f"Wrote Xbox session screenshot to {output}.")


@observe_app.command("press")
def session_press(
    button: Annotated[str, typer.Argument(help="Controller button name.")],
    repeat: Annotated[int, typer.Option("--repeat", min=1, max=20)] = 1,
    session_file: Annotated[
        Path,
        typer.Option("--session-file", help="Path to session details."),
    ] = DEFAULT_SESSION_FILE,
) -> None:
    try:
        press_observe_session(session_file=session_file, button=button, repeat=repeat)
    except (ObserveError, ObserveSessionError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    console.print(f"Pressed {button} {repeat} time{'s' if repeat != 1 else ''}.")


@observe_app.command("stop")
def stop(
    session_file: Annotated[
        Path,
        typer.Option("--session-file", help="Path to session details."),
    ] = DEFAULT_SESSION_FILE,
) -> None:
    try:
        stop_observe_session(session_file)
    except (ObserveError, ObserveSessionError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    console.print(f"Stopped Xbox observe session: {session_file}.")


@observe_app.command("status")
def status(
    session_file: Annotated[
        Path,
        typer.Option("--session-file", help="Path to session details."),
    ] = DEFAULT_SESSION_FILE,
) -> None:
    session_status = status_observe_session(session_file)
    if not session_status.exists:
        console.print(f"No observe session: {session_file}.")
        return
    if session_status.active:
        message = (
            f"Observe session active on 127.0.0.1:{session_status.port} "
            f"(pid {session_status.pid})."
        )
        console.print(message)
        return
    reason = (
        f" {session_status.reason}"
        if session_status.reason is not None
        else ""
    )
    console.print(f"Observe session is stale: {session_file}.{reason}")


@observe_app.command("cleanup")
def cleanup(
    session_file: Annotated[
        Path,
        typer.Option("--session-file", help="Path to session details."),
    ] = DEFAULT_SESSION_FILE,
) -> None:
    try:
        result = cleanup_observe_session(session_file)
    except (ObserveError, ObserveSessionError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error
    if not result.status.exists:
        console.print(f"No observe session to clean: {session_file}.")
        return
    if result.stopped:
        console.print(f"Stopped Xbox observe session: {session_file}.")
        return
    if result.removed:
        console.print(f"Removed stale observe session: {session_file}.")
