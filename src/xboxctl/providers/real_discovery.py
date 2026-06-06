from dataclasses import dataclass
from pathlib import Path
from typing import Final

import anyio
from httpx import AsyncClient

from xboxctl.auth import validate_auth_tokens
from xboxctl.models import (
    Console,
    ConsoleId,
    InstalledApp,
    PowerState,
    ProductId,
    StorageDevice,
)
from xboxctl.providers.xccs_models import (
    XccsApiStatus,
    XccsConsoleDevice,
    XccsConsoleList,
    XccsConsoleStatus,
    XccsInstalledPackage,
    XccsInstalledPackagesList,
    XccsStorageDevice,
    XccsStorageDevicesList,
)
from xboxctl.typing_compat import override

XCCS_URL: Final = "https://xccs.xboxlive.com"
XCCS_CONTRACT_VERSION: Final = "4"
REMOTE_MANAGEMENT_SKILL: Final = "RemoteManagement"
UNKNOWN_ACTIVE_TITLE: Final = "Unknown"
BYTES_PER_GIB: Final = 1024 * 1024 * 1024
REAL_PROVIDER_NOT_CONFIGURED: Final = (
    "Xbox is not configured. Run `uv run xboxctl auth login`, then "
    "`uv run xboxctl auth validate`. For local tests, use --provider fake. "
    "No console command was sent."
)
MISSING_REAL_PROVIDER_TOOLS: Final = (
    "Xbox command dependencies are missing. Run: uv sync --extra real"
)
MISSING_XSTS_AUTH_MESSAGE: Final = "Xbox authentication did not return an XSTS token."
NO_CONSOLES_RETURNED: Final = "No Xbox consoles were returned for this account."


@dataclass(frozen=True, slots=True)
class RealDiscoveryError(Exception):
    reason: str

    @override
    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class XccsClient:
    tokens_file: Path

    def list_consoles(self) -> tuple[Console, ...]:
        return anyio.run(self.list_consoles_async)

    def status(self) -> Console:
        return anyio.run(self.status_async)

    async def list_consoles_async(self) -> tuple[Console, ...]:
        session = await build_session(self.tokens_file)
        try:
            console_list = await fetch_console_list(session=session)
        finally:
            await session.aclose()
        return tuple(console_from_device(device) for device in console_list.result)

    async def status_async(self) -> Console:
        session = await build_session(self.tokens_file)
        try:
            console_list = await fetch_console_list(session=session)
            if not console_list.result:
                raise RealDiscoveryError(NO_CONSOLES_RETURNED)
            device = console_list.result[0]
            console_status = await fetch_console_status(
                session=session,
                device_id=device.id,
            )
            packages = await fetch_installed_packages(
                session=session,
                device_id=device.id,
            )
            storage = await fetch_storage_devices(session=session, device_id=device.id)
        finally:
            await session.aclose()
        return console_from_status(
            device=device,
            status=console_status,
            packages=packages.result,
            storage_devices=storage.result,
        )


async def build_session(tokens_file: Path) -> AsyncClient:
    try:
        from pythonxbox.authentication.manager import (  # noqa: PLC0415
            AuthenticationManager,
        )
        from pythonxbox.authentication.models import (  # noqa: PLC0415
            OAuth2TokenResponse,
        )
        from pythonxbox.common.signed_session import (  # noqa: PLC0415
            SignedSession,
        )
        from pythonxbox.scripts import CLIENT_ID, CLIENT_SECRET  # noqa: PLC0415
    except ImportError as error:
        raise RealDiscoveryError(MISSING_REAL_PROVIDER_TOOLS) from error

    raw_tokens = await anyio.Path(tokens_file).read_text(encoding="utf-8")
    session: AsyncClient = SignedSession()
    auth_mgr = AuthenticationManager(session, CLIENT_ID, CLIENT_SECRET, "")
    auth_mgr.oauth = OAuth2TokenResponse.model_validate_json(raw_tokens)
    await auth_mgr.refresh_tokens()
    _ = await anyio.Path(tokens_file).write_text(
        auth_mgr.oauth.model_dump_json(),
        encoding="utf-8",
    )
    xsts_token = auth_mgr.xsts_token
    if xsts_token is None:
        await session.aclose()
        raise RealDiscoveryError(MISSING_XSTS_AUTH_MESSAGE)
    session.headers.update(
        {
            "Authorization": xsts_token.authorization_header_value,
            "x-xbl-contract-version": XCCS_CONTRACT_VERSION,
            "skillplatform": REMOTE_MANAGEMENT_SKILL,
        }
    )
    return session


def fetch_real_consoles(tokens_file: Path | None = None) -> tuple[Console, ...]:
    validation = validate_auth_tokens(tokens_file)
    if not validation.valid:
        raise RealDiscoveryError(REAL_PROVIDER_NOT_CONFIGURED)
    return XccsClient(tokens_file=validation.tokens_file).list_consoles()


def fetch_real_status(tokens_file: Path | None = None) -> Console:
    validation = validate_auth_tokens(tokens_file)
    if not validation.valid:
        raise RealDiscoveryError(REAL_PROVIDER_NOT_CONFIGURED)
    return XccsClient(tokens_file=validation.tokens_file).status()


async def fetch_console_list(session: AsyncClient) -> XccsConsoleList:
    params = {
        "queryCurrentDevice": "false",
        "includeStorageDevices": "true",
    }
    response = await session.get(f"{XCCS_URL}/lists/devices", params=params)
    _ = response.raise_for_status()
    payload = XccsConsoleList.model_validate_json(response.text)
    ensure_xccs_ok(payload.status)
    return payload


async def fetch_console_status(
    session: AsyncClient,
    device_id: str,
) -> XccsConsoleStatus:
    response = await session.get(f"{XCCS_URL}/consoles/{device_id}")
    _ = response.raise_for_status()
    payload = XccsConsoleStatus.model_validate_json(response.text)
    ensure_xccs_ok(payload.status)
    return payload


async def fetch_installed_packages(
    session: AsyncClient,
    device_id: str,
) -> XccsInstalledPackagesList:
    response = await session.get(
        f"{XCCS_URL}/lists/installedApps",
        params={"deviceId": device_id},
    )
    _ = response.raise_for_status()
    payload = XccsInstalledPackagesList.model_validate_json(response.text)
    ensure_xccs_ok(payload.status)
    return payload


async def fetch_storage_devices(
    session: AsyncClient,
    device_id: str,
) -> XccsStorageDevicesList:
    response = await session.get(
        f"{XCCS_URL}/lists/storageDevices",
        params={"deviceId": device_id},
    )
    _ = response.raise_for_status()
    payload = XccsStorageDevicesList.model_validate_json(response.text)
    ensure_xccs_ok(payload.status)
    return payload


def ensure_xccs_ok(status: XccsApiStatus) -> None:
    if status.error_code == "OK":
        return
    message = status.error_message or status.error_code
    reason = f"Xbox remote management returned {message}."
    raise RealDiscoveryError(reason)


def console_from_device(device: XccsConsoleDevice) -> Console:
    return Console(
        id=ConsoleId(device.id),
        name=device.name,
        power_state=map_power_state(device.power_state),
        active_title=UNKNOWN_ACTIVE_TITLE,
        storage=storage_from_xccs(device.storage_devices or []),
        apps=(),
    )


def console_from_status(
    device: XccsConsoleDevice,
    status: XccsConsoleStatus,
    packages: list[XccsInstalledPackage],
    storage_devices: list[XccsStorageDevice],
) -> Console:
    focus_app_aumid = status.focus_app_aumid or ""
    return Console(
        id=ConsoleId(device.id),
        name=device.name,
        power_state=map_power_state(status.power_state),
        active_title=active_title_from_packages(focus_app_aumid, packages),
        storage=storage_from_xccs(status.storage_devices or storage_devices),
        apps=tuple(app_from_package(package, focus_app_aumid) for package in packages),
    )


def app_from_package(
    package: XccsInstalledPackage,
    focus_app_aumid: str,
) -> InstalledApp:
    product_id = package.one_store_product_id or package.unique_id or package.aumid
    return InstalledApp(
        name=package.name or package.aumid or "Unknown app",
        product_id=ProductId(product_id or "unknown"),
        running=package.aumid == focus_app_aumid,
    )


def active_title_from_packages(
    focus_app_aumid: str,
    packages: list[XccsInstalledPackage],
) -> str:
    for package in packages:
        if package.aumid == focus_app_aumid:
            return package.name or focus_app_aumid or UNKNOWN_ACTIVE_TITLE
    return focus_app_aumid or UNKNOWN_ACTIVE_TITLE


def storage_from_xccs(devices: list[XccsStorageDevice]) -> tuple[StorageDevice, ...]:
    return tuple(storage_device_from_xccs(device) for device in devices)


def storage_device_from_xccs(device: XccsStorageDevice) -> StorageDevice:
    total_gb = round(device.total_space_bytes / BYTES_PER_GIB)
    free_gb = round(device.free_space_bytes / BYTES_PER_GIB)
    return StorageDevice(
        name=device.storage_device_name,
        used_gb=max(total_gb - free_gb, 0),
        total_gb=total_gb,
    )


def map_power_state(value: str) -> PowerState:
    match value:
        case "On" | "SystemUpdate":
            return PowerState.ON
        case "Off":
            return PowerState.OFF
        case "ConnectedStandby" | "Unknown":
            return PowerState.STANDBY
        case _:
            return PowerState.STANDBY
