import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Final, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

AUTH_TOKENS_ENV: Final = "XBOXCTL_TOKENS_FILE"
SETUP_COMMAND: Final = (
    "uv run xboxctl auth login"
)
DEFAULT_AUTH_REDIRECT_URI: Final = "http://localhost:8080/auth/callback"
DEFAULT_AUTH_PORT: Final = 8080


@dataclass(frozen=True, slots=True)
class AuthStatus:
    tokens_file: Path
    configured: bool


class AuthValidationReason(StrEnum):
    OK = "ok"
    MISSING_FILE = "missing_file"
    MALFORMED_JSON = "malformed_json"
    MISSING_FIELDS = "missing_fields"


class AuthPrompt(StrEnum):
    SELECT_ACCOUNT = "select_account"
    LOGIN = "login"
    CONSENT = "consent"


type RequiredTokenField = Literal[
    "token_type",
    "expires_in",
    "scope",
    "access_token",
    "refresh_token",
    "user_id",
]


REQUIRED_TOKEN_FIELDS: Final[tuple[RequiredTokenField, ...]] = (
    "token_type",
    "expires_in",
    "scope",
    "access_token",
    "refresh_token",
    "user_id",
)


class TokenPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    token_type: str | None = None
    expires_in: int | None = None
    scope: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    user_id: str | None = None
    issued: str | None = None


@dataclass(frozen=True, slots=True)
class AuthValidation:
    tokens_file: Path
    valid: bool
    reason: AuthValidationReason
    missing_fields: tuple[RequiredTokenField, ...]

    @property
    def can_attempt_real_provider(self) -> bool:
        return self.valid


@dataclass(frozen=True, slots=True)
class AuthLoginConfig:
    tokens_file: Path
    redirect_uri: str
    port: int
    prompt: AuthPrompt
    client_id: str | None = None

    def helper_command(self, executable: str = "python") -> tuple[str, ...]:
        command = (
            executable,
            "-m",
            "xboxctl.auth_flow",
            "--tokens",
            str(self.tokens_file),
            "--redirect-uri",
            self.redirect_uri,
            "--port",
            str(self.port),
            "--prompt",
            self.prompt.value,
        )
        if self.client_id is None:
            return command
        return (*command, "--client-id", self.client_id)

    def display_command(self) -> str:
        parts = (quote_command_part(part) for part in self.helper_command())
        return "uv run " + " ".join(parts)


def quote_command_part(value: str) -> str:
    if " " in value:
        return f'"{value}"'
    return value


def default_tokens_file(
    environ: Mapping[str, str] = os.environ,
    home: Path | None = None,
    platform: str = sys.platform,
) -> Path:
    override = environ.get(AUTH_TOKENS_ENV)
    if override is not None:
        return Path(override).expanduser()

    root = Path.home() if home is None else home
    if platform == "darwin":
        return root / "Library" / "Application Support" / "xbox" / "tokens.json"
    if platform == "win32":
        local_app_data = environ.get("LOCALAPPDATA")
        base = (
            Path(local_app_data)
            if local_app_data is not None
            else root / "AppData" / "Local"
        )
        return base / "OpenXbox" / "xbox" / "tokens.json"
    return root / ".local" / "share" / "xbox" / "tokens.json"


def build_auth_login_config(
    client_id: str | None = None,
    redirect_uri: str = DEFAULT_AUTH_REDIRECT_URI,
    port: int = DEFAULT_AUTH_PORT,
    prompt: AuthPrompt = AuthPrompt.SELECT_ACCOUNT,
    tokens_file: Path | None = None,
) -> AuthLoginConfig:
    resolved_tokens_file = default_tokens_file() if tokens_file is None else tokens_file
    return AuthLoginConfig(
        tokens_file=resolved_tokens_file,
        redirect_uri=redirect_uri,
        port=port,
        prompt=prompt,
        client_id=client_id,
    )


def inspect_auth_status(tokens_file: Path | None = None) -> AuthStatus:
    resolved_tokens_file = default_tokens_file() if tokens_file is None else tokens_file
    return AuthStatus(
        tokens_file=resolved_tokens_file,
        configured=resolved_tokens_file.is_file(),
    )


def validate_auth_tokens(tokens_file: Path | None = None) -> AuthValidation:
    resolved_tokens_file = default_tokens_file() if tokens_file is None else tokens_file
    if not resolved_tokens_file.is_file():
        return AuthValidation(
            tokens_file=resolved_tokens_file,
            valid=False,
            reason=AuthValidationReason.MISSING_FILE,
            missing_fields=(),
        )

    raw_tokens = resolved_tokens_file.read_text(encoding="utf-8")
    malformed = is_malformed_json(raw_tokens)
    if malformed:
        return AuthValidation(
            tokens_file=resolved_tokens_file,
            valid=False,
            reason=AuthValidationReason.MALFORMED_JSON,
            missing_fields=(),
        )

    payload = TokenPayload.model_validate_json(raw_tokens)
    missing_fields = required_missing_fields(payload)
    return AuthValidation(
        tokens_file=resolved_tokens_file,
        valid=len(missing_fields) == 0,
        reason=(
            AuthValidationReason.OK
            if len(missing_fields) == 0
            else AuthValidationReason.MISSING_FIELDS
        ),
        missing_fields=missing_fields,
    )


def is_malformed_json(raw_tokens: str) -> bool:
    try:
        _ = TokenPayload.model_validate_json(raw_tokens)
    except ValidationError as error:
        return any(
            item["type"] in {"json_invalid", "model_type"} for item in error.errors()
        )
    return False


def required_missing_fields(payload: TokenPayload) -> tuple[RequiredTokenField, ...]:
    values = {
        "token_type": payload.token_type,
        "expires_in": payload.expires_in,
        "scope": payload.scope,
        "access_token": payload.access_token,
        "refresh_token": payload.refresh_token,
        "user_id": payload.user_id,
    }
    return tuple(field for field in REQUIRED_TOKEN_FIELDS if not values[field])
