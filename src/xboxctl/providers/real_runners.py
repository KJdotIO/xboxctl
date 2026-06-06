from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import anyio

from xboxctl.providers.real_commands import (
    CloudButtonCommand,
    LaunchCommand,
    MediaCommand,
    PowerCommand,
    TextCommand,
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
