import os
import subprocess
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import anyio

from xboxctl.auth import default_tokens_file
from xboxctl.models import PowerAction
from xboxctl.providers.real_commands import (
    SMARTGLASS_TIMEOUT_SECONDS,
    CloudButtonCommand,
    LaunchCommand,
    MediaCommand,
    PowerCommand,
    RealCommandError,
    TextCommand,
    ensure_helper_venv,
    resolve_helper_python,
)
from xboxctl.providers.real_launch import (
    SmartGlassLaunchProvider,
    build_xbox_live_client,
    launch_app_async,
    send_button_async,
    send_media_action_async,
    send_power_action_async,
    send_text_async,
)

WAKE_ADDRESS_ENV: Final = "XBOXCTL_WAKE_ADDRESS"


@dataclass(frozen=True, slots=True)
class CloudLaunchRunner:
    tokens_file: Path | None = None
    launcher: Callable[[LaunchCommand, SmartGlassLaunchProvider], Awaitable[None]] = (
        launch_app_async
    )

    def __call__(self, command: LaunchCommand) -> None:
        anyio.run(self.launch_async, command)

    async def launch_async(self, command: LaunchCommand) -> None:
        client = await build_xbox_live_client(self.tokens_file)
        try:
            await self.launcher(command, client.smartglass)
        finally:
            await client.close()


@dataclass(frozen=True, slots=True)
class CloudPowerRunner:
    tokens_file: Path | None = None
    sender: Callable[[PowerCommand, SmartGlassLaunchProvider], Awaitable[None]] = (
        send_power_action_async
    )

    def __call__(self, command: PowerCommand) -> None:
        anyio.run(self.send_async, command)

    async def send_async(self, command: PowerCommand) -> None:
        client = await build_xbox_live_client(self.tokens_file)
        try:
            await self.sender(command, client.smartglass)
        finally:
            await client.close()


@dataclass(frozen=True, slots=True)
class CloudButtonRunner:
    tokens_file: Path | None = None
    sender: Callable[
        [CloudButtonCommand, SmartGlassLaunchProvider],
        Awaitable[None],
    ] = send_button_async

    def __call__(self, command: CloudButtonCommand) -> None:
        anyio.run(self.send_async, command)

    async def send_async(self, command: CloudButtonCommand) -> None:
        client = await build_xbox_live_client(self.tokens_file)
        try:
            await self.sender(command, client.smartglass)
        finally:
            await client.close()


@dataclass(frozen=True, slots=True)
class CloudMediaRunner:
    tokens_file: Path | None = None
    sender: Callable[[MediaCommand, SmartGlassLaunchProvider], Awaitable[None]] = (
        send_media_action_async
    )

    def __call__(self, command: MediaCommand) -> None:
        anyio.run(self.send_async, command)

    async def send_async(self, command: MediaCommand) -> None:
        client = await build_xbox_live_client(self.tokens_file)
        try:
            await self.sender(command, client.smartglass)
        finally:
            await client.close()


@dataclass(frozen=True, slots=True)
class CloudTextRunner:
    tokens_file: Path | None = None
    sender: Callable[[TextCommand, SmartGlassLaunchProvider], Awaitable[None]] = (
        send_text_async
    )

    def __call__(self, command: TextCommand) -> None:
        anyio.run(self.send_async, command)

    async def send_async(self, command: TextCommand) -> None:
        client = await build_xbox_live_client(self.tokens_file)
        try:
            await self.sender(command, client.smartglass)
        finally:
            await client.close()


def address_cache_path(tokens_file: Path | None) -> Path:
    resolved = default_tokens_file() if tokens_file is None else tokens_file
    return resolved.parent / "console_address"


def read_cached_address(tokens_file: Path | None) -> str | None:
    cache_file = address_cache_path(tokens_file)
    try:
        content = cache_file.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
        return None
    else:
        return content or None


@dataclass(frozen=True, slots=True)
class SmartGlassWakeRunner:
    environ: Mapping[str, str] = field(default_factory=lambda: os.environ)
    project_root: Path = Path(__file__).resolve().parents[3]
    tries: int = 8
    tokens_file: Path | None = None

    def __call__(self, command: PowerCommand) -> None:
        if command.action != PowerAction.ON:
            raise RealCommandError(
                reason=f"Local SmartGlass wake cannot send {command.action.value}.",
            )
        helper_python = resolve_helper_python(self.environ)
        if helper_python is None:
            helper_python = ensure_helper_venv(self.environ)
        address = self.environ.get(WAKE_ADDRESS_ENV)
        if address is None:
            address = read_cached_address(self.tokens_file)
        run_wake_worker(
            helper_python=helper_python,
            command=command,
            project_root=self.project_root,
            address=address,
            tries=self.tries,
        )


def run_wake_worker(
    helper_python: Path,
    command: PowerCommand,
    project_root: Path,
    address: str | None,
    tries: int,
) -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(project_root / "src")
    worker_command = [
        str(helper_python),
        "-m",
        "xboxctl.providers.smartglass_worker",
        "wake",
        "--liveid",
        str(command.console_id),
        "--tries",
        str(tries),
    ]
    if address is not None:
        worker_command.extend(("--address", address))
    try:
        _ = subprocess.run(  # noqa: S603
            tuple(worker_command),
            check=True,
            capture_output=True,
            text=True,
            timeout=SMARTGLASS_TIMEOUT_SECONDS,
            env=environment,
        )
    except subprocess.TimeoutExpired as timeout_error:
        raise RealCommandError(
            reason="Timed out while waking the Xbox.",
        ) from timeout_error
    except subprocess.CalledProcessError as process_error:
        raise RealCommandError(reason="Xbox wake failed.") from process_error
    except FileNotFoundError as file_error:
        raise RealCommandError(
            reason="Could not run the SmartGlass helper.",
        ) from file_error


@dataclass(frozen=True, slots=True)
class ComposedWakeRunner:
    """Tries cloud wake first (same path as the Xbox mobile app).

    Falls back to local SmartGlass when the cloud request doesn't reach
    the console.
    """

    tokens_file: Path | None = None
    environ: Mapping[str, str] = field(default_factory=lambda: os.environ)
    project_root: Path = Path(__file__).resolve().parents[3]
    tries: int = 8

    def __call__(self, command: PowerCommand) -> None:
        if command.action != PowerAction.ON:
            raise RealCommandError(
                reason=f"Wake runner cannot send {command.action.value}.",
            )
        try:
            CloudPowerRunner(tokens_file=self.tokens_file)(command)
        except RealCommandError:
            SmartGlassWakeRunner(
                environ=self.environ,
                project_root=self.project_root,
                tries=self.tries,
                tokens_file=self.tokens_file,
            )(command)
