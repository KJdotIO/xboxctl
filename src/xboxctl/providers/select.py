from enum import StrEnum

from xboxctl.providers.base import XboxProvider
from xboxctl.providers.fake import build_fake_provider
from xboxctl.providers.real import PythonXboxProvider


class ProviderName(StrEnum):
    FAKE = "fake"
    REAL = "real"


def build_provider(name: ProviderName) -> XboxProvider:
    match name:
        case ProviderName.FAKE:
            return build_fake_provider()
        case ProviderName.REAL:
            return PythonXboxProvider()
