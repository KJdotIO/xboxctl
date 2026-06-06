from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field


class XccsModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="ignore",
        frozen=True,
        populate_by_name=True,
    )


class XccsApiStatus(XccsModel):
    error_code: str = Field(alias="errorCode")
    error_message: str | None = Field(default=None, alias="errorMessage")


class XccsStorageDevice(XccsModel):
    storage_device_name: str = Field(alias="storageDeviceName")
    total_space_bytes: float = Field(alias="totalSpaceBytes")
    free_space_bytes: float = Field(alias="freeSpaceBytes")


class XccsConsoleDevice(XccsModel):
    id: str
    name: str
    power_state: str = Field(alias="powerState")
    storage_devices: list[XccsStorageDevice] | None = Field(
        default=None,
        alias="storageDevices",
    )


class XccsConsoleList(XccsModel):
    result: list[XccsConsoleDevice]
    status: XccsApiStatus


class XccsConsoleStatus(XccsModel):
    power_state: str = Field(alias="powerState")
    focus_app_aumid: str | None = Field(default=None, alias="focusAppAumid")
    storage_devices: list[XccsStorageDevice] | None = Field(
        default=None,
        alias="storageDevices",
    )
    status: XccsApiStatus


class XccsInstalledPackage(XccsModel):
    one_store_product_id: str | None = Field(default=None, alias="oneStoreProductId")
    aumid: str | None = None
    name: str | None = None
    unique_id: str | None = Field(default=None, alias="uniqueId")


class XccsInstalledPackagesList(XccsModel):
    result: list[XccsInstalledPackage]
    status: XccsApiStatus


class XccsStorageDevicesList(XccsModel):
    result: list[XccsStorageDevice]
    status: XccsApiStatus
