from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Protocol

from xboxctl.models import (
    Console,
    MediaAction,
    PowerAction,
    ProviderAction,
)
from xboxctl.providers.app_resolution import find_installed_app
from xboxctl.providers.real_commands import (
    CloudButtonCommand,
    CloudButtonRunner,
    LaunchCommand,
    LaunchRunner,
    MediaCommand,
    MediaRunner,
    PowerCommand,
    PowerRunner,
    PressCommand,
    PressRunner,
    RealCommandError,
    SmartGlassPressRunner,
    TextCommand,
    TextRunner,
)
from xboxctl.providers.real_discovery import (
    REAL_PROVIDER_NOT_CONFIGURED,
    RealDiscoveryError,
    fetch_real_consoles,
    fetch_real_status,
)
from xboxctl.providers.real_runners import (
    CloudButtonRunner as CloudButtonRunnerImpl,
)
from xboxctl.providers.real_runners import (
    CloudLaunchRunner,
    CloudMediaRunner,
    CloudPowerRunner,
    CloudTextRunner,
)
from xboxctl.typing_compat import override

DEFAULT_PROVIDER_UNAVAILABLE: str = REAL_PROVIDER_NOT_CONFIGURED
MUTATING_REAL_COMMAND_UNAVAILABLE: str = (
    "Real Xbox read-only discovery is enabled, but mutating console commands are "
    "not wired yet. No console command was sent."
)
SUPPORTED_BUTTONS: Final[dict[str, str]] = {
    "a": "PadA",
    "b": "PadB",
    "x": "PadX",
    "y": "PadY",
    "dpad-up": "DPadUp",
    "up": "DPadUp",
    "dpad-down": "DPadDown",
    "down": "DPadDown",
    "dpad-left": "DPadLeft",
    "left": "DPadLeft",
    "dpad-right": "DPadRight",
    "right": "DPadRight",
    "menu": "Menu",
    "view": "View",
    "home": "Nexu",
    "xbox": "Nexu",
}

class ConsoleListDiscovery(Protocol):
    def __call__(self, tokens_file: Path | None = None) -> tuple[Console, ...]: ...


class ConsoleStatusDiscovery(Protocol):
    def __call__(self, tokens_file: Path | None = None) -> Console: ...


@dataclass(frozen=True, slots=True)
class ProviderUnavailableError(Exception):
    reason: str = DEFAULT_PROVIDER_UNAVAILABLE

    @override
    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class PythonXboxProvider:
    list_discovery: ConsoleListDiscovery = field(default=fetch_real_consoles)
    status_discovery: ConsoleStatusDiscovery = field(default=fetch_real_status)
    launch_runner: LaunchRunner | None = None
    cloud_button_runner: CloudButtonRunner | None = None
    press_runner: PressRunner | None = None
    media_runner: MediaRunner | None = None
    text_runner: TextRunner | None = None
    power_runner: PowerRunner | None = None
    tokens_file: Path | None = None

    def list_consoles(self) -> tuple[Console, ...]:
        try:
            return self.list_discovery(self.tokens_file)
        except RealDiscoveryError as error:
            raise ProviderUnavailableError(reason=str(error)) from error

    def status(self) -> Console:
        try:
            return self.status_discovery(self.tokens_file)
        except RealDiscoveryError as error:
            raise ProviderUnavailableError(reason=str(error)) from error

    def launch(self, target: str) -> ProviderAction:
        console = self.status()
        app = find_installed_app(console=console, target=target)
        try:
            self.resolved_launch_runner()(
                LaunchCommand(console_id=console.id, product_id=app.product_id),
            )
        except RealCommandError as error:
            raise ProviderUnavailableError(reason=str(error)) from error
        return ProviderAction(message=f"Launching {app.name} on {console.name}.")

    def press(self, button: str, repeat: int) -> ProviderAction:
        cloud_button = normalise_cloud_button(button)
        local_button = normalise_button(button)
        console = self.status()
        try:
            self.resolved_cloud_button_runner()(
                CloudButtonCommand(
                    console_id=console.id,
                    button=cloud_button,
                    repeat=repeat,
                ),
            )
        except RealCommandError:
            try:
                self.resolved_press_runner()(
                    PressCommand(button=local_button, repeat=repeat),
                )
            except RealCommandError as error:
                raise ProviderUnavailableError(reason=str(error)) from error
        suffix = "time" if repeat == 1 else "times"
        return ProviderAction(
            message=f"Pressed {button} {repeat} {suffix} on {console.name}.",
        )

    def send_text(self, text: str) -> ProviderAction:
        console = self.status()
        try:
            self.resolved_text_runner()(TextCommand(console_id=console.id, text=text))
        except RealCommandError as error:
            raise ProviderUnavailableError(reason=str(error)) from error
        return ProviderAction(message=f"Sent text to {console.name}.")

    def media(self, action: MediaAction) -> ProviderAction:
        console = self.status()
        try:
            self.resolved_media_runner()(
                MediaCommand(console_id=console.id, action=action),
            )
        except RealCommandError as error:
            raise ProviderUnavailableError(reason=str(error)) from error
        return ProviderAction(message=f"Sent {action.value} to {console.name}.")

    def power(self, action: PowerAction) -> ProviderAction:
        console = self.status()
        try:
            self.resolved_power_runner()(
                PowerCommand(console_id=console.id, action=action),
            )
        except RealCommandError as error:
            raise ProviderUnavailableError(reason=str(error)) from error
        return ProviderAction(message=f"Sent {action.value} to {console.name}.")

    def resolved_launch_runner(self) -> LaunchRunner:
        if self.launch_runner is not None:
            return self.launch_runner
        return CloudLaunchRunner(tokens_file=self.tokens_file)

    def resolved_cloud_button_runner(self) -> CloudButtonRunner:
        if self.cloud_button_runner is not None:
            return self.cloud_button_runner
        return CloudButtonRunnerImpl(tokens_file=self.tokens_file)

    def resolved_press_runner(self) -> PressRunner:
        if self.press_runner is not None:
            return self.press_runner
        return SmartGlassPressRunner(tokens_file=self.tokens_file)

    def resolved_media_runner(self) -> MediaRunner:
        if self.media_runner is not None:
            return self.media_runner
        return CloudMediaRunner(tokens_file=self.tokens_file)

    def resolved_text_runner(self) -> TextRunner:
        if self.text_runner is not None:
            return self.text_runner
        return CloudTextRunner(tokens_file=self.tokens_file)

    def resolved_power_runner(self) -> PowerRunner:
        if self.power_runner is not None:
            return self.power_runner
        return CloudPowerRunner(tokens_file=self.tokens_file)


CLOUD_BUTTONS: Final[dict[str, str]] = {
    "a": "A",
    "b": "B",
    "x": "X",
    "y": "Y",
    "dpad-up": "Up",
    "up": "Up",
    "dpad-down": "Down",
    "down": "Down",
    "dpad-left": "Left",
    "left": "Left",
    "dpad-right": "Right",
    "right": "Right",
    "menu": "Menu",
    "view": "View",
    "home": "Home",
    "xbox": "Nexus",
    "guide": "Guide",
}


def normalise_cloud_button(button: str) -> str:
    key = button.strip().lower()
    normalised = CLOUD_BUTTONS.get(key)
    if normalised is None:
        supported = ", ".join(sorted(CLOUD_BUTTONS))
        raise ProviderUnavailableError(
            reason=(
                f"Unsupported Xbox button: {button}. Supported buttons: {supported}."
            ),
        )
    return normalised

def normalise_button(button: str) -> str:
    key = button.strip().lower()
    normalised = SUPPORTED_BUTTONS.get(key)
    if normalised is None:
        supported = ", ".join(sorted(SUPPORTED_BUTTONS))
        raise ProviderUnavailableError(
            reason=(
                f"Unsupported Xbox button: {button}. Supported buttons: {supported}."
            ),
        )
    return normalised
