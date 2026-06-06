from dataclasses import dataclass

import anyio
from pythonxbox.api.provider.smartglass.models import InputKeyType

from xboxctl.models import ConsoleId, MediaAction, PowerAction, ProductId
from xboxctl.providers.real_commands import (
    CloudButtonCommand,
    LaunchCommand,
    MediaCommand,
    PowerCommand,
    RealCommandError,
    TextCommand,
)
from xboxctl.providers.real_launch import (
    OperationVerificationConfig,
    launch_app_async,
    send_button_async,
    send_media_action_async,
    send_power_action_async,
    send_text_async,
    verify_operation_succeeded,
)


@dataclass(frozen=True, slots=True)
class FakeLaunchResponse:
    accepted: bool


@dataclass(frozen=True, slots=True)
class FakeCommandResponse:
    op_id: str


@dataclass(frozen=True, slots=True)
class FakeOperationLabel:
    value: str


@dataclass(frozen=True, slots=True)
class FakeOperationNode:
    op_id: str
    succeeded: bool
    operation_status: FakeOperationLabel


@dataclass(frozen=True, slots=True)
class FakeOperationStatus:
    op_status_list: list[FakeOperationNode]


class FakeSmartGlassClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.command_calls: list[tuple[str, str]] = []
        self.operation_succeeded: bool = True
        self.operation_statuses: list[FakeOperationLabel] = []

    async def launch_app(
        self,
        device_id: str,
        one_store_product_id: str,
    ) -> FakeLaunchResponse:
        self.calls.append((device_id, one_store_product_id))
        return FakeLaunchResponse(accepted=True)

    async def pause(self, device_id: str) -> FakeLaunchResponse:
        self.command_calls.append(("pause", device_id))
        return FakeLaunchResponse(accepted=True)

    async def play(self, device_id: str) -> FakeLaunchResponse:
        self.command_calls.append(("play", device_id))
        return FakeLaunchResponse(accepted=True)

    async def next(self, device_id: str) -> FakeLaunchResponse:
        self.command_calls.append(("next", device_id))
        return FakeLaunchResponse(accepted=True)

    async def previous(self, device_id: str) -> FakeLaunchResponse:
        self.command_calls.append(("previous", device_id))
        return FakeLaunchResponse(accepted=True)

    async def insert_text(self, device_id: str, text: str) -> FakeLaunchResponse:
        self.command_calls.append(("text", f"{device_id}:{text}"))
        return FakeLaunchResponse(accepted=True)

    async def go_home(self, device_id: str) -> FakeLaunchResponse:
        self.command_calls.append(("home", device_id))
        return FakeLaunchResponse(accepted=True)

    async def press_button(
        self,
        device_id: str,
        button: InputKeyType,
    ) -> FakeLaunchResponse:
        self.command_calls.append(("button", f"{device_id}:{button.value}"))
        return FakeLaunchResponse(accepted=True)

    async def reboot(self, device_id: str) -> FakeCommandResponse:
        self.command_calls.append(("reboot", device_id))
        return FakeCommandResponse(op_id="op-1")

    async def wake_up(self, device_id: str) -> FakeCommandResponse:
        self.command_calls.append(("wake", device_id))
        return FakeCommandResponse(op_id="op-1")

    async def turn_off(self, device_id: str) -> FakeCommandResponse:
        self.command_calls.append(("off", device_id))
        return FakeCommandResponse(op_id="op-1")

    async def get_op_status(
        self,
        device_id: str,
        op_id: str,
    ) -> FakeOperationStatus:
        self.command_calls.append(("op", f"{device_id}:{op_id}"))
        status_label = (
            self.operation_statuses.pop(0)
            if self.operation_statuses
            else FakeOperationLabel(value="Succeeded")
        )
        return FakeOperationStatus(
            op_status_list=[
                FakeOperationNode(
                    op_id=op_id,
                    succeeded=(
                        self.operation_succeeded and status_label.value != "Pending"
                    ),
                    operation_status=status_label,
                ),
            ],
        )


def test_launch_app_async_calls_smartglass_provider() -> None:
    # Given: a cloud launch command and fake SmartGlass provider.
    smartglass = FakeSmartGlassClient()
    command = LaunchCommand(
        console_id=ConsoleId("console-id"),
        product_id=ProductId("9NDP7KTLK7W3"),
    )

    # When: the launch command is sent.
    anyio.run(launch_app_async, command, smartglass)

    # Then: the provider receives the console id and OneStore product id.
    assert smartglass.calls == [("console-id", "9NDP7KTLK7W3")]


def test_send_media_action_async_calls_smartglass_provider() -> None:
    # Given: a media command and fake SmartGlass provider.
    smartglass = FakeSmartGlassClient()
    command = MediaCommand(
        console_id=ConsoleId("console-id"),
        action=MediaAction.PAUSE,
    )

    # When: the media command is sent.
    anyio.run(send_media_action_async, command, smartglass)

    # Then: the provider receives the matching media action.
    assert smartglass.command_calls == [("pause", "console-id")]


def test_send_text_async_calls_smartglass_provider() -> None:
    # Given: a text command and fake SmartGlass provider.
    smartglass = FakeSmartGlassClient()
    command = TextCommand(console_id=ConsoleId("console-id"), text="hello")

    # When: the text command is sent.
    anyio.run(send_text_async, command, smartglass)

    # Then: the provider receives the text payload.
    assert smartglass.command_calls == [("text", "console-id:hello")]


def test_send_button_async_calls_smartglass_provider() -> None:
    # Given: a cloud button command and fake SmartGlass provider.
    smartglass = FakeSmartGlassClient()
    command = CloudButtonCommand(
        console_id=ConsoleId("console-id"),
        button="Right",
        repeat=2,
    )

    # When: the button command is sent.
    anyio.run(send_button_async, command, smartglass)

    # Then: the provider receives each repeated button press.
    assert smartglass.command_calls == [
        ("button", "console-id:Right"),
        ("button", "console-id:Right"),
    ]


def test_send_button_async_uses_go_home_for_home_button() -> None:
    # Given: a cloud home command and fake SmartGlass provider.
    smartglass = FakeSmartGlassClient()
    command = CloudButtonCommand(
        console_id=ConsoleId("console-id"),
        button="Home",
        repeat=1,
    )

    # When: the home command is sent.
    anyio.run(send_button_async, command, smartglass)

    # Then: the provider receives one shell home command instead of key repeats.
    assert smartglass.command_calls == [("home", "console-id")]


def test_send_button_async_repeats_go_home_for_home_button() -> None:
    # Given: a repeated cloud home command and fake SmartGlass provider.
    smartglass = FakeSmartGlassClient()
    command = CloudButtonCommand(
        console_id=ConsoleId("console-id"),
        button="Home",
        repeat=3,
    )

    # When: the home command is sent.
    anyio.run(send_button_async, command, smartglass)

    # Then: the provider receives one shell home command per repeat.
    assert smartglass.command_calls == [
        ("home", "console-id"),
        ("home", "console-id"),
        ("home", "console-id"),
    ]


def test_send_power_action_async_verifies_operation_success() -> None:
    # Given: a power command and fake SmartGlass provider.
    smartglass = FakeSmartGlassClient()
    command = PowerCommand(
        console_id=ConsoleId("console-id"),
        action=PowerAction.REBOOT,
    )

    # When: the power command is sent.
    anyio.run(send_power_action_async, command, smartglass)

    # Then: the provider command is followed by an operation-status check.
    assert smartglass.command_calls == [
        ("reboot", "console-id"),
        ("op", "console-id:op-1"),
    ]


def test_send_power_action_async_rejects_failed_operation() -> None:
    # Given: a power command whose operation status reports failure.
    smartglass = FakeSmartGlassClient()
    smartglass.operation_succeeded = False
    command = PowerCommand(
        console_id=ConsoleId("console-id"),
        action=PowerAction.OFF,
    )

    # When: the power command is sent.
    try:
        anyio.run(send_power_action_async, command, smartglass)
    except RealCommandError as error:
        message = str(error)
    else:
        message = "power command unexpectedly succeeded"

    # Then: the failed operation is surfaced as a real-command error.
    assert "Xbox power off operation did not succeed" in message


def test_verify_operation_succeeded_polls_pending_operation() -> None:
    # Given: an operation that is pending before it succeeds.
    smartglass = FakeSmartGlassClient()
    smartglass.operation_statuses = [
        FakeOperationLabel(value="Pending"),
        FakeOperationLabel(value="Succeeded"),
    ]

    # When: operation status is verified.
    anyio.run(
        verify_operation_succeeded,
        smartglass,
        "console-id",
        "op-1",
        PowerAction.OFF,
        OperationVerificationConfig(attempts=2, poll_seconds=0),
    )

    # Then: verification polls until the operation reaches success.
    assert smartglass.command_calls == [
        ("op", "console-id:op-1"),
        ("op", "console-id:op-1"),
    ]
