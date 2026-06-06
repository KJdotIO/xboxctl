from dataclasses import dataclass
from pathlib import Path
from typing import Final

import anyio

from xboxctl.auth import default_tokens_file
from xboxctl.typing_compat import override

PROFILE_URL: Final = "https://profile.xboxlive.com"
PROFILE_CONTRACT_VERSION: Final = "3"
PROFILE_GAMERTAG: Final = "Gamertag"
PROFILE_MODERN_GAMERTAG: Final = "ModernGamertag"
PROFILE_UNIQUE_MODERN_GAMERTAG: Final = "UniqueModernGamertag"
PROFILE_GAMERSCORE: Final = "Gamerscore"
PROFILE_ACCOUNT_TIER: Final = "AccountTier"
PROFILE_SETTINGS: Final = (
    PROFILE_GAMERTAG,
    PROFILE_MODERN_GAMERTAG,
    "ModernGamertagSuffix",
    PROFILE_UNIQUE_MODERN_GAMERTAG,
    PROFILE_GAMERSCORE,
    PROFILE_ACCOUNT_TIER,
)
MISSING_REAL_PROVIDER_TOOLS: Final = (
    "Xbox command dependencies are missing. Run: uv sync --extra real"
)
MISSING_XSTS_AUTH_MESSAGE: Final = "Xbox authentication did not return an XSTS token."


@dataclass(frozen=True, slots=True)
class XboxIdentityUnavailableError(Exception):
    reason: str

    @override
    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class WhoamiResult:
    xuid: str
    gamertag: str | None
    modern_gamertag: str | None
    unique_modern_gamertag: str | None
    gamerscore: str | None
    account_tier: str | None


def fetch_whoami(tokens_file: Path | None = None) -> WhoamiResult:
    return anyio.run(fetch_whoami_async, tokens_file)


async def fetch_whoami_async(tokens_file: Path | None = None) -> WhoamiResult:
    try:
        from pythonxbox.api.provider.profile.models import (  # noqa: PLC0415
            ProfileResponse,
        )
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
        raise XboxIdentityUnavailableError(MISSING_REAL_PROVIDER_TOOLS) from error

    resolved_tokens_file = default_tokens_file() if tokens_file is None else tokens_file
    raw_tokens = resolved_tokens_file.read_text(encoding="utf-8")

    async with SignedSession() as session:
        auth_mgr = AuthenticationManager(session, CLIENT_ID, CLIENT_SECRET, "")
        auth_mgr.oauth = OAuth2TokenResponse.model_validate_json(raw_tokens)
        await auth_mgr.refresh_tokens()
        _ = resolved_tokens_file.write_text(
            auth_mgr.oauth.model_dump_json(),
            encoding="utf-8",
        )

        xsts_token = auth_mgr.xsts_token
        if xsts_token is None:
            raise XboxIdentityUnavailableError(MISSING_XSTS_AUTH_MESSAGE)
        headers = {
            "Authorization": xsts_token.authorization_header_value,
            "x-xbl-contract-version": PROFILE_CONTRACT_VERSION,
        }
        params = {"settings": ",".join(PROFILE_SETTINGS)}
        profile_url = f"{PROFILE_URL}/users/xuid({xsts_token.xuid})/profile/settings"
        response = await session.get(profile_url, params=params, headers=headers)
        _ = response.raise_for_status()
        profile = ProfileResponse.model_validate_json(response.text)

    if not profile.profile_users:
        return WhoamiResult(
            xuid=xsts_token.xuid,
            gamertag=None,
            modern_gamertag=None,
            unique_modern_gamertag=None,
            gamerscore=None,
            account_tier=None,
        )

    profile_user = profile.profile_users[0]
    settings = {setting.id: setting.value for setting in profile_user.settings}
    return WhoamiResult(
        xuid=profile_user.id,
        gamertag=settings.get(PROFILE_GAMERTAG),
        modern_gamertag=settings.get(PROFILE_MODERN_GAMERTAG),
        unique_modern_gamertag=settings.get(PROFILE_UNIQUE_MODERN_GAMERTAG),
        gamerscore=settings.get(PROFILE_GAMERSCORE),
        account_tier=settings.get(PROFILE_ACCOUNT_TIER),
    )
