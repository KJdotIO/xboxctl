from dataclasses import dataclass
from enum import StrEnum
from typing import NewType

ConsoleId = NewType("ConsoleId", str)
ProductId = NewType("ProductId", str)


class PowerState(StrEnum):
    ON = "on"
    OFF = "off"
    STANDBY = "standby"


class MediaAction(StrEnum):
    PLAY = "play"
    PAUSE = "pause"
    NEXT = "next"
    PREVIOUS = "previous"


class PowerAction(StrEnum):
    ON = "on"
    OFF = "off"
    REBOOT = "reboot"


@dataclass(frozen=True, slots=True)
class StorageDevice:
    name: str
    used_gb: int
    total_gb: int


@dataclass(frozen=True, slots=True)
class InstalledApp:
    name: str
    product_id: ProductId
    running: bool


@dataclass(frozen=True, slots=True)
class Console:
    id: ConsoleId
    name: str
    power_state: PowerState
    active_title: str
    storage: tuple[StorageDevice, ...]
    apps: tuple[InstalledApp, ...]


@dataclass(frozen=True, slots=True)
class ProviderAction:
    message: str
