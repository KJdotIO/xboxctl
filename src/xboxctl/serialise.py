from typing import TypedDict

from xboxctl.models import Console, InstalledApp, StorageDevice


class StoragePayload(TypedDict):
    name: str
    used_gb: int
    total_gb: int


class AppPayload(TypedDict):
    name: str
    product_id: str
    running: bool


class ConsolePayload(TypedDict):
    id: str
    name: str
    power_state: str
    active_title: str


class CommandPayload(TypedDict):
    command: str
    requires_confirm: bool


class McpPayload(TypedDict):
    name: str
    version: str
    provider: str
    commands: list[CommandPayload]


def storage_payload(storage: StorageDevice) -> StoragePayload:
    return {
        "name": storage.name,
        "used_gb": storage.used_gb,
        "total_gb": storage.total_gb,
    }


def app_payload(app: InstalledApp) -> AppPayload:
    return {
        "name": app.name,
        "product_id": app.product_id,
        "running": app.running,
    }


def console_payload(console: Console) -> ConsolePayload:
    return {
        "id": console.id,
        "name": console.name,
        "power_state": console.power_state.value,
        "active_title": console.active_title,
    }
