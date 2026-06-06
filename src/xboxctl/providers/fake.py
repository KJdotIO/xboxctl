from dataclasses import dataclass

from xboxctl.models import (
    Console,
    ConsoleId,
    InstalledApp,
    MediaAction,
    PowerAction,
    PowerState,
    ProductId,
    ProviderAction,
    StorageDevice,
)
from xboxctl.providers.app_resolution import find_installed_app
from xboxctl.providers.base import XboxProvider


@dataclass(frozen=True, slots=True)
class FakeXboxProvider:
    consoles: tuple[Console, ...]

    def list_consoles(self) -> tuple[Console, ...]:
        return self.consoles

    def status(self) -> Console:
        return self.consoles[0]

    def launch(self, target: str) -> ProviderAction:
        console = self.status()
        app = find_installed_app(console=console, target=target)
        return ProviderAction(
            message=f"Launching {app.name} on {console.name}.",
        )

    def press(self, button: str, repeat: int) -> ProviderAction:
        return ProviderAction(
            message=f"Pressed {button} {repeat} times on {self.status().name}.",
        )

    def send_text(self, text: str) -> ProviderAction:
        return ProviderAction(
            message=f"Sent text to {self.status().name}: {text}",
        )

    def media(self, action: MediaAction) -> ProviderAction:
        return ProviderAction(
            message=f"Sent {action.value} to {self.status().name}.",
        )

    def power(self, action: PowerAction) -> ProviderAction:
        return ProviderAction(
            message=f"Sent {action.value} to {self.status().name}.",
        )


def build_fake_provider() -> XboxProvider:
    return FakeXboxProvider(
        consoles=(
            Console(
                id=ConsoleId("console-living-room"),
                name="Living Room Series X",
                power_state=PowerState.ON,
                active_title="Halo Infinite",
                storage=(
                    StorageDevice(name="Internal SSD", used_gb=512, total_gb=802),
                ),
                apps=(
                    InstalledApp(
                        name="Halo Infinite",
                        product_id=ProductId("9PP5G1F0C2B6"),
                        running=True,
                    ),
                    InstalledApp(
                        name="Forza Horizon 5",
                        product_id=ProductId("9NNX1VVR3KNQ"),
                        running=False,
                    ),
                    InstalledApp(
                        name="YouTube",
                        product_id=ProductId("9NBLGGH4R315"),
                        running=False,
                    ),
                ),
            ),
        ),
    )
