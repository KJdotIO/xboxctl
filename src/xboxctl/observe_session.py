import json
import os
import secrets
import subprocess
import time
from dataclasses import dataclass
from http.client import HTTPConnection
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, ValidationError

from xboxctl.auth import default_tokens_file
from xboxctl.observe import (
    DEFAULT_JPEG_QUALITY,
    DEFAULT_SETTLE_MS,
    OBSERVE_TIMEOUT_SECONDS,
    ObserveCaptureFormat,
    ObserveError,
    observe_helper_script,
    resolve_node,
)
from xboxctl.typing_compat import override

DEFAULT_SESSION_FILE = Path(".xboxctl-observe-session.json")
DEFAULT_SESSION_START_TIMEOUT_SECONDS = 120
DEFAULT_SESSION_IDLE_TIMEOUT_SECONDS = 600
HTTP_ERROR_STATUS = 400
SESSION_REQUEST_TIMEOUT_SECONDS = 30
SESSION_STATUS_TIMEOUT_SECONDS = 2


@dataclass(frozen=True, slots=True)
class ObserveStartSessionRequest:
    session_file: Path
    tokens_file: Path | None = None
    server_id: str | None = None
    timeout_seconds: int = OBSERVE_TIMEOUT_SECONDS
    capture_format: ObserveCaptureFormat = ObserveCaptureFormat.PNG
    width: int | None = None
    quality: int = DEFAULT_JPEG_QUALITY
    settle_ms: int = DEFAULT_SETTLE_MS
    idle_timeout_seconds: int = DEFAULT_SESSION_IDLE_TIMEOUT_SECONDS


@dataclass(frozen=True, slots=True)
class ObserveSessionError(Exception):
    reason: str

    @override
    def __str__(self) -> str:
        return self.reason


class ObserveSessionInfo(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    pid: int
    port: int
    token: str


@dataclass(frozen=True, slots=True)
class ObserveSessionStatus:
    session_file: Path
    exists: bool
    active: bool
    pid: int | None = None
    port: int | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ObserveSessionCleanup:
    status: ObserveSessionStatus
    stopped: bool
    removed: bool


def observe_start_command(
    request: ObserveStartSessionRequest,
    environ: dict[str, str] | None = None,
) -> tuple[str, ...]:
    resolved_environ = os.environ if environ is None else environ
    tokens_file = (
        default_tokens_file(environ=resolved_environ)
        if request.tokens_file is None
        else request.tokens_file
    )
    command = (
        resolve_node(resolved_environ),
        str(observe_helper_script()),
        "--serve",
        "--tokens",
        str(tokens_file),
        "--session-file",
        str(request.session_file),
        "--timeout",
        str(request.timeout_seconds),
        "--idle-timeout",
        str(request.idle_timeout_seconds),
    )
    if request.server_id is not None:
        command = (*command, "--server-id", request.server_id)
    if request.capture_format != ObserveCaptureFormat.PNG:
        command = (*command, "--format", request.capture_format.value)
    if request.width is not None:
        command = (*command, "--width", str(request.width))
    if request.quality != DEFAULT_JPEG_QUALITY:
        command = (*command, "--quality", str(request.quality))
    if request.settle_ms != DEFAULT_SETTLE_MS:
        command = (*command, "--settle-ms", str(request.settle_ms))
    return command


def start_observe_session(request: ObserveStartSessionRequest) -> ObserveSessionInfo:
    session_token = secrets.token_urlsafe(24)
    command = (*observe_start_command(request), "--session-token", session_token)
    request.session_file.unlink(missing_ok=True)
    request.session_file.parent.mkdir(parents=True, exist_ok=True)
    log_file = request.session_file.with_suffix(".log")
    with log_file.open("ab") as log:
        process = subprocess.Popen(  # noqa: S603
            command,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    deadline = time.monotonic() + request.timeout_seconds
    while time.monotonic() < deadline:
        info = maybe_load_observe_session(request.session_file)
        if info is not None:
            return info
        if process.poll() is not None:
            raise ObserveSessionError(
                reason=f"Observe session exited early. See log: {log_file}",
            )
        time.sleep(0.2)
    process.terminate()
    raise ObserveSessionError(reason=f"Timed out starting observe session: {log_file}")


def load_observe_session(session_file: Path) -> ObserveSessionInfo:
    info = maybe_load_observe_session(session_file)
    if info is None:
        raise ObserveSessionError(
            reason=f"Observe session file not found: {session_file}",
        )
    return info


def maybe_load_observe_session(session_file: Path) -> ObserveSessionInfo | None:
    try:
        raw = session_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        return ObserveSessionInfo.model_validate_json(raw)
    except ValidationError as error:
        raise ObserveSessionError(
            reason=f"Invalid observe session file: {error}",
        ) from error


def capture_observe_session(
    session_file: Path,
    output: Path,
    capture_format: ObserveCaptureFormat | None = None,
    width: int | None = None,
    quality: int | None = None,
) -> None:
    info = load_observe_session(session_file)
    payload: dict[str, str | int] = {}
    if capture_format is not None:
        payload["format"] = capture_format.value
    if width is not None:
        payload["width"] = width
    if quality is not None:
        payload["quality"] = quality
    data = session_request(info=info, path="/capture", payload=payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    _ = output.write_bytes(data)


def press_observe_session(session_file: Path, button: str, repeat: int) -> None:
    info = load_observe_session(session_file)
    _ = session_request(
        info=info,
        path="/press",
        payload={"button": button, "repeat": repeat},
    )


def stop_observe_session(session_file: Path) -> None:
    info = load_observe_session(session_file)
    _ = session_request(info=info, path="/session", payload={}, method="DELETE")
    session_file.unlink(missing_ok=True)


def status_observe_session(session_file: Path) -> ObserveSessionStatus:
    try:
        info = maybe_load_observe_session(session_file)
    except ObserveSessionError as error:
        return ObserveSessionStatus(
            session_file=session_file,
            exists=True,
            active=False,
            reason=str(error),
        )
    if info is None:
        return ObserveSessionStatus(
            session_file=session_file,
            exists=False,
            active=False,
            reason="missing",
        )
    try:
        _ = session_request(
            info=info,
            path="/status",
            payload={},
            method="GET",
            timeout_seconds=SESSION_STATUS_TIMEOUT_SECONDS,
        )
    except ObserveError as error:
        return ObserveSessionStatus(
            session_file=session_file,
            exists=True,
            active=False,
            pid=info.pid,
            port=info.port,
            reason=str(error),
        )
    return ObserveSessionStatus(
        session_file=session_file,
        exists=True,
        active=True,
        pid=info.pid,
        port=info.port,
    )


def cleanup_observe_session(session_file: Path) -> ObserveSessionCleanup:
    status = status_observe_session(session_file)
    if not status.exists:
        return ObserveSessionCleanup(status=status, stopped=False, removed=False)
    if status.active:
        stop_observe_session(session_file)
        return ObserveSessionCleanup(status=status, stopped=True, removed=True)
    session_file.unlink(missing_ok=True)
    session_file.with_suffix(".log").unlink(missing_ok=True)
    return ObserveSessionCleanup(status=status, stopped=False, removed=True)


def session_request(
    info: ObserveSessionInfo,
    path: str,
    payload: dict[str, str | int],
    method: str = "POST",
    timeout_seconds: int = SESSION_REQUEST_TIMEOUT_SECONDS,
) -> bytes:
    body = json.dumps(payload).encode("utf-8")
    connection = HTTPConnection("127.0.0.1", info.port, timeout=timeout_seconds)
    try:
        connection.request(
            method=method,
            url=path,
            body=body,
            headers={
                "authorization": f"Bearer {info.token}",
                "content-type": "application/json",
            },
        )
        response = connection.getresponse()
        data = response.read()
    except OSError as error:
        raise ObserveError(reason=f"Observe session request failed: {error}") from error
    finally:
        connection.close()
    if response.status >= HTTP_ERROR_STATUS:
        reason = data.decode("utf-8", errors="replace") or response.reason
        raise ObserveError(reason=f"Observe session returned {reason}.")
    return data
