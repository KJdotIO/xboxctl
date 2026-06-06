# pyright: reportAny=false, reportUnnecessaryComparison=false
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, assert_never

import anyio

from xboxctl.auth import default_tokens_file
from xboxctl.models import MediaAction, PowerAction
from xboxctl.providers.real_commands import (
    CloudButtonCommand,
    LaunchCommand,
    MediaCommand,
    PowerCommand,
    RealCommandError,
    TextCommand,
)

if TYPE_CHECKING:
    from pythonxbox.api.provider.smartglass.models import InputKeyType

POWER_OPERATION_ATTEMPTS = 8
POWER_OPERATION_POLL_SECONDS = 4


@dataclass(frozen=True, slots=True)
class OperationVerificationConfig:
    attempts: int = POWER_OPERATION_ATTEMPTS
    poll_seconds: float = POWER_OPERATION_POLL_SECONDS


DEFAULT_OPERATION_VERIFICATION_CONFIG = OperationVerificationConfig()


class SmartGlassLaunchResult(Protocol):
    pass


class SmartGlassLaunchProvider(Protocol):
    def launch_app(
        self,
        device_id: str,
        one_store_product_id: str,
    ) -> Awaitable[SmartGlassLaunchResult]: ...

    def play(self, device_id: str) -> Awaitable[SmartGlassLaunchResult]: ...

    def pause(self, device_id: str) -> Awaitable[SmartGlassLaunchResult]: ...

    def next(self, device_id: str) -> Awaitable[SmartGlassLaunchResult]: ...

    def previous(self, device_id: str) -> Awaitable[SmartGlassLaunchResult]: ...

    def insert_text(
        self,
        device_id: str,
        text: str,
    ) -> Awaitable[SmartGlassLaunchResult]: ...

    def go_home(self, device_id: str) -> Awaitable[SmartGlassLaunchResult]: ...

    def press_button(
        self,
        device_id: str,
        button: "InputKeyType",
    ) -> Awaitable[SmartGlassLaunchResult]: ...

    def wake_up(self, device_id: str) -> Awaitable["SmartGlassCommandResult"]: ...

    def turn_off(self, device_id: str) -> Awaitable["SmartGlassCommandResult"]: ...

    def reboot(self, device_id: str) -> Awaitable["SmartGlassCommandResult"]: ...

    def get_op_status(
        self,
        device_id: str,
        op_id: str,
    ) -> Awaitable["SmartGlassOperationStatus"]: ...


class SmartGlassCommandResult(Protocol):
    @property
    def op_id(self) -> str: ...


class SmartGlassOperationLabel(Protocol):
    @property
    def value(self) -> str: ...


class SmartGlassOperationNode(Protocol):
    @property
    def op_id(self) -> str: ...

    @property
    def succeeded(self) -> bool: ...

    @property
    def operation_status(self) -> SmartGlassOperationLabel: ...


class SmartGlassOperationStatus(Protocol):
    @property
    def op_status_list(self) -> Sequence[SmartGlassOperationNode]: ...


@dataclass(frozen=True, slots=True)
class XboxLiveLaunchClient:
    smartglass: SmartGlassLaunchProvider
    close: Callable[[], Awaitable[None]]


async def launch_app_async(
    command: LaunchCommand,
    smartglass: SmartGlassLaunchProvider,
) -> None:
    _ = await smartglass.launch_app(
        device_id=str(command.console_id),
        one_store_product_id=str(command.product_id),
    )


async def send_media_action_async(
    command: MediaCommand,
    smartglass: SmartGlassLaunchProvider,
) -> None:
    device_id = str(command.console_id)
    match command.action:
        case MediaAction.PLAY:
            _ = await smartglass.play(device_id)
        case MediaAction.PAUSE:
            _ = await smartglass.pause(device_id)
        case MediaAction.NEXT:
            _ = await smartglass.next(device_id)
        case MediaAction.PREVIOUS:
            _ = await smartglass.previous(device_id)
        case unreachable:
            assert_never(unreachable)


async def send_text_async(
    command: TextCommand,
    smartglass: SmartGlassLaunchProvider,
) -> None:
    _ = await smartglass.insert_text(str(command.console_id), command.text)


async def send_button_async(
    command: CloudButtonCommand,
    smartglass: SmartGlassLaunchProvider,
) -> None:
    try:
        from pythonxbox.api.provider.smartglass.models import (  # noqa: PLC0415
            InputKeyType,
        )
    except ImportError as error:
        raise RealCommandError(
            reason="Real-provider dependencies are missing.",
        ) from error

    if command.button == "Home":
        for _ in range(command.repeat):
            _ = await smartglass.go_home(str(command.console_id))
        return

    input_key = InputKeyType[command.button]
    for _ in range(command.repeat):
        _ = await smartglass.press_button(str(command.console_id), input_key)


async def send_power_action_async(
    command: PowerCommand,
    smartglass: SmartGlassLaunchProvider,
) -> None:
    device_id = str(command.console_id)
    match command.action:
        case PowerAction.ON:
            response = await smartglass.wake_up(device_id)
        case PowerAction.OFF:
            response = await smartglass.turn_off(device_id)
        case PowerAction.REBOOT:
            response = await smartglass.reboot(device_id)
        case unreachable:
            assert_never(unreachable)
    await verify_operation_succeeded(
        smartglass=smartglass,
        console_id=command.console_id,
        op_id=response.op_id,
        action=command.action,
    )


async def verify_operation_succeeded(
    smartglass: SmartGlassLaunchProvider,
    console_id: str,
    op_id: str,
    action: PowerAction,
    config: OperationVerificationConfig = DEFAULT_OPERATION_VERIFICATION_CONFIG,
) -> None:
    last_status = "missing"
    for attempt in range(config.attempts):
        status = await smartglass.get_op_status(console_id, op_id)
        matching_nodes = [node for node in status.op_status_list if node.op_id == op_id]
        if not matching_nodes:
            last_status = "missing"
        else:
            operation = matching_nodes[0]
            last_status = operation.operation_status.value
            if operation.succeeded:
                return
            if last_status != "Pending":
                break
        if attempt + 1 < config.attempts:
            await anyio.sleep(config.poll_seconds)
    raise RealCommandError(
        reason=(
            f"Xbox power {action.value} operation did not succeed: "
            f"{last_status}."
        ),
    )


async def build_xbox_live_client(tokens_file: Path | None) -> XboxLiveLaunchClient:
    try:
        from pythonxbox.api.client import XboxLiveClient  # noqa: PLC0415
        from pythonxbox.authentication.manager import (  # noqa: PLC0415
            AuthenticationManager,
        )
        from pythonxbox.authentication.models import (  # noqa: PLC0415
            OAuth2TokenResponse,
        )
        from pythonxbox.common.signed_session import SignedSession  # noqa: PLC0415
        from pythonxbox.scripts import CLIENT_ID, CLIENT_SECRET  # noqa: PLC0415
    except ImportError as error:
        raise RealCommandError(
            reason="Real-provider dependencies are missing.",
        ) from error

    resolved_tokens_file = default_tokens_file() if tokens_file is None else tokens_file
    raw_tokens = await anyio.Path(resolved_tokens_file).read_text(encoding="utf-8")
    auth_session = SignedSession()
    auth_mgr = AuthenticationManager(auth_session, CLIENT_ID, CLIENT_SECRET, "")
    auth_mgr.oauth = OAuth2TokenResponse.model_validate_json(raw_tokens)
    await auth_mgr.refresh_tokens()
    _ = await anyio.Path(resolved_tokens_file).write_text(
        auth_mgr.oauth.model_dump_json(),
        encoding="utf-8",
    )
    client = XboxLiveClient(auth_mgr)
    return XboxLiveLaunchClient(
        smartglass=client.smartglass,
        close=auth_session.aclose,
    )
