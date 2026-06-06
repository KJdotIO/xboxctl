import os
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from xboxctl.auth import default_tokens_file
from xboxctl.typing_compat import override

OBSERVE_TIMEOUT_SECONDS: Final = 120
NODE_BINARY_ENV: Final = "XBOXCTL_NODE"
DEFAULT_JPEG_QUALITY: Final = 80
DEFAULT_SETTLE_MS: Final = 5000


class ObserveCaptureFormat(StrEnum):
    PNG = "png"
    JPEG = "jpeg"


@dataclass(frozen=True, slots=True)
class ObserveError(Exception):
    reason: str

    @override
    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class ObserveScreenshotRequest:
    output: Path
    tokens_file: Path | None = None
    server_id: str | None = None
    timeout_seconds: int = OBSERVE_TIMEOUT_SECONDS
    capture_format: ObserveCaptureFormat = ObserveCaptureFormat.PNG
    width: int | None = None
    quality: int = DEFAULT_JPEG_QUALITY
    settle_ms: int = DEFAULT_SETTLE_MS


@dataclass(frozen=True, slots=True)
class ObserveFlowRequest:
    output_dir: Path
    steps: tuple[str, ...]
    tokens_file: Path | None = None
    server_id: str | None = None
    timeout_seconds: int = OBSERVE_TIMEOUT_SECONDS
    capture_format: ObserveCaptureFormat = ObserveCaptureFormat.PNG
    width: int | None = None
    quality: int = DEFAULT_JPEG_QUALITY
    settle_ms: int = DEFAULT_SETTLE_MS


def observe_helper_script() -> Path:
    return Path(__file__).with_name("observe_xhome.mjs")


def resolve_node(environ: Mapping[str, str] = os.environ) -> str:
    configured = environ.get(NODE_BINARY_ENV)
    if configured is not None:
        return configured
    node = shutil.which("node")
    if node is None:
        raise ObserveError(reason="Node.js is required for observe commands.")
    return node


def observe_command(
    request: ObserveScreenshotRequest,
    environ: Mapping[str, str] = os.environ,
) -> tuple[str, ...]:
    tokens_file = (
        default_tokens_file(environ=environ)
        if request.tokens_file is None
        else request.tokens_file
    )
    command = (
        resolve_node(environ),
        str(observe_helper_script()),
        "--tokens",
        str(tokens_file),
        "--output",
        str(request.output),
        "--timeout",
        str(request.timeout_seconds),
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


def observe_flow_command(
    request: ObserveFlowRequest,
    environ: Mapping[str, str] = os.environ,
) -> tuple[str, ...]:
    tokens_file = (
        default_tokens_file(environ=environ)
        if request.tokens_file is None
        else request.tokens_file
    )
    command = (
        resolve_node(environ),
        str(observe_helper_script()),
        "--tokens",
        str(tokens_file),
        "--output-dir",
        str(request.output_dir),
        "--timeout",
        str(request.timeout_seconds),
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
    for step in request.steps:
        command = (*command, "--step", step)
    return command


def capture_observe_screenshot(request: ObserveScreenshotRequest) -> None:
    command = observe_command(request)
    run_observe_helper(command=command, timeout_seconds=request.timeout_seconds)


def capture_observe_flow(request: ObserveFlowRequest) -> None:
    command = observe_flow_command(request)
    run_observe_helper(command=command, timeout_seconds=request.timeout_seconds)


def run_observe_helper(command: tuple[str, ...], timeout_seconds: int) -> None:
    result = subprocess.run(  # noqa: S603
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds + 15,
    )
    if result.returncode == 0:
        return
    details = (result.stderr or result.stdout).strip()
    if not details:
        details = f"observe helper exited with code {result.returncode}"
    raise ObserveError(reason=details)
