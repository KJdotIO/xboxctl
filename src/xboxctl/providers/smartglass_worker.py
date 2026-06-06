# pyright: reportAny=false, reportAttributeAccessIssue=false
# pyright: reportMissingImports=false, reportOptionalMemberAccess=false
# pyright: reportPrivateUsage=false, reportUnknownArgumentType=false
# pyright: reportUnknownLambdaType=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnusedCallResult=false
import argparse
import asyncio
import socket
import sys
import types
from dataclasses import dataclass
from typing import Protocol

from xboxctl.providers.network import preferred_local_ip_for_remote
from xboxctl.typing_compat import override


@dataclass(frozen=True, slots=True)
class WorkerButton:
    name: str


@dataclass(frozen=True, slots=True)
class WorkerButtonError(Exception):
    button: str

    @override
    def __str__(self) -> str:
        return f"Unsupported SmartGlass button: {self.button}."


@dataclass(frozen=True, slots=True)
class ConsoleDiscoveryError(Exception):
    @override
    def __str__(self) -> str:
        return "No Xbox consoles were discovered on the local network."


@dataclass(frozen=True, slots=True)
class ConsoleConnectionTimeoutError(Exception):
    @override
    def __str__(self) -> str:
        return (
            "Timed out connecting to the Xbox over SmartGlass. "
            "If discovery still works, restart or sleep/wake the Xbox and try again."
        )


class SmartGlassConsole(Protocol):
    address: str
    protocol: object | None


def parse_worker_button(button: str) -> WorkerButton:
    try:
        from xbox.sg.enum import GamePadButton  # noqa: PLC0415
    except ImportError:
        known_buttons = {
            "Clear",
            "DPadDown",
            "DPadLeft",
            "DPadRight",
            "DPadUp",
            "Menu",
            "Nexu",
            "PadA",
            "PadB",
            "PadX",
            "PadY",
            "View",
        }
        if button in known_buttons:
            return WorkerButton(name=button)
        raise WorkerButtonError(button=button) from None

    try:
        enum_button = GamePadButton[button]
    except KeyError as error:
        raise WorkerButtonError(button=button) from error
    return WorkerButton(name=enum_button.name)


async def press_button(button: str, repeat: int) -> None:
    parsed_button = parse_worker_button(button)
    from xbox.sg.console import Console  # noqa: PLC0415
    from xbox.sg.enum import GamePadButton  # noqa: PLC0415
    from xbox.sg.manager import InputManager  # noqa: PLC0415
    from xbox.sg.protocol import SmartglassProtocol  # noqa: PLC0415

    enum_button = GamePadButton[parsed_button.name]
    consoles = await Console.discover(timeout=5)
    if not consoles:
        raise ConsoleDiscoveryError
    console = consoles[0]
    local_ip = preferred_local_ip_for_remote(console.address)
    console.add_manager(InputManager)
    transport_holder: dict[str, asyncio.DatagramTransport] = {}

    async def bound_ensure(self: SmartGlassConsole) -> None:
        if not self.protocol:
            loop = asyncio.get_running_loop()
            transport, self.protocol = await loop.create_datagram_endpoint(
                lambda: SmartglassProtocol(self.address, console._crypto),  # noqa: SLF001
                family=socket.AF_INET,
                local_addr=(local_ip, 0),
                remote_addr=(self.address, 5050),
                allow_broadcast=True,
            )
            transport_holder["transport"] = transport
            self.protocol.on_timeout += console._handle_timeout  # noqa: SLF001
            self.protocol.on_message += console._handle_message  # noqa: SLF001
            self.protocol.on_json += console._handle_json  # noqa: SLF001

    console._ensure_protocol_started = types.MethodType(  # noqa: SLF001
        bound_ensure,
        console,
    )
    try:
        try:
            await asyncio.wait_for(console.connect(), timeout=8)
        except TimeoutError as error:
            raise ConsoleConnectionTimeoutError from error
        for _ in range(repeat):
            await console.gamepad_input(enum_button)
            await asyncio.sleep(0.18)
            await console.gamepad_input(GamePadButton.Clear)
            await asyncio.sleep(0.08)
        await asyncio.wait_for(console.protocol.disconnect(), timeout=2)
    finally:
        transport = transport_holder.get("transport") or getattr(
            getattr(console, "protocol", None),
            "_transport",
            None,
        )
        if transport is not None:
            transport.close()
            await asyncio.sleep(0.2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="smartglass-worker")
    subparsers = parser.add_subparsers(dest="command", required=True)
    press_parser = subparsers.add_parser("press")
    _ = press_parser.add_argument("--button", required=True)
    _ = press_parser.add_argument("--repeat", type=int, required=True)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "press":
            asyncio.run(press_button(button=args.button, repeat=args.repeat))
            return 0
    except (
        ConsoleConnectionTimeoutError,
        ConsoleDiscoveryError,
        WorkerButtonError,
    ) as error:
        _ = sys.stderr.write(f"{error}\n")
        return 1
    else:
        return 2


if __name__ == "__main__":
    sys.exit(main())
