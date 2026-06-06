import os
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Final
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, ConfigDict, ValidationError

from xboxctl.auth import default_tokens_file
from xboxctl.youtube_lounge import (
    LoungeAuth,
    LoungeStatus,
    lounge_disconnect,
    lounge_next,
    lounge_pause,
    lounge_play_video,
    lounge_previous,
    lounge_resume,
    lounge_seek,
    lounge_status,
    pair_lounge,
    refresh_lounge,
)

YOUTUBE_FILE_ENV: Final = "XBOXCTL_YOUTUBE_FILE"
DEFAULT_DEVICE_NAME: Final = "xboxctl"
YOUTUBE_ID_PATTERN: Final = re.compile(r"^[A-Za-z0-9_-]{11}$")

type PairFunction = Callable[[str, str], Awaitable[LoungeAuth]]
type StatusFunction = Callable[[LoungeAuth, str], Awaitable[LoungeStatus]]
type AuthFunction = Callable[[LoungeAuth, str], Awaitable[LoungeAuth]]
type VideoFunction = Callable[[LoungeAuth, str, str], Awaitable[LoungeAuth]]
type SeekFunction = Callable[[LoungeAuth, str, float], Awaitable[LoungeAuth]]


class YouTubeLoungeError(RuntimeError):
    pass


class YouTubeAuthFile(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    screen_id: str
    lounge_token: str
    screen_name: str | None = None

    def to_lounge_auth(self) -> LoungeAuth:
        return LoungeAuth(
            screen_id=self.screen_id,
            lounge_token=self.lounge_token,
            screen_name=self.screen_name,
        )

    @classmethod
    def from_lounge_auth(cls, auth: LoungeAuth) -> "YouTubeAuthFile":
        return cls(
            screen_id=auth.screen_id,
            lounge_token=auth.lounge_token,
            screen_name=auth.screen_name,
        )


@dataclass(frozen=True, slots=True)
class YouTubePairResult:
    token_file: Path
    screen_name: str | None


@dataclass(frozen=True, slots=True)
class YouTubeCommandResult:
    message: str
    token_file: Path


@dataclass(frozen=True, slots=True)
class YouTubeStatus:
    paired: bool
    token_file: Path
    screen_name: str | None = None
    available: bool | None = None
    reason: str | None = None


def default_youtube_file(
    environ: Mapping[str, str] | None = None,
) -> Path:
    environment = os.environ if environ is None else environ
    override = environment.get(YOUTUBE_FILE_ENV)
    if override:
        return Path(override)
    return default_tokens_file(environment).parent / "youtube_lounge.json"


def normalise_youtube_video_id(value: str) -> str:
    candidate = _youtube_video_id_candidate(value.strip())
    if candidate is None or not YOUTUBE_ID_PATTERN.fullmatch(candidate):
        msg = "Expected a YouTube video ID or URL."
        raise YouTubeLoungeError(msg)
    return candidate


def load_youtube_auth(token_file: Path) -> LoungeAuth:
    try:
        raw = token_file.read_text(encoding="utf-8")
        return YouTubeAuthFile.model_validate_json(raw).to_lounge_auth()
    except FileNotFoundError as error:
        msg = (
            "YouTube is not paired yet. Open YouTube on the TV, go to "
            "Settings -> Link with TV code, then run "
            "uv run xboxctl youtube pair <code>."
        )
        raise YouTubeLoungeError(msg) from error
    except ValidationError as error:
        msg = f"YouTube token file is invalid: {token_file}."
        raise YouTubeLoungeError(msg) from error


def save_youtube_auth(auth: LoungeAuth, token_file: Path) -> None:
    token_file.parent.mkdir(parents=True, exist_ok=True)
    payload = YouTubeAuthFile.from_lounge_auth(auth)
    _ = token_file.write_text(payload.model_dump_json(indent=2), encoding="utf-8")


async def pair_youtube(
    pairing_code: str,
    *,
    device_name: str = DEFAULT_DEVICE_NAME,
    token_file: Path | None = None,
    pair_function: PairFunction = pair_lounge,
) -> YouTubePairResult:
    path = default_youtube_file() if token_file is None else token_file
    try:
        auth = await pair_function(pairing_code, device_name)
    except Exception as error:
        msg = f"YouTube pairing failed: {error}"
        raise YouTubeLoungeError(msg) from error
    save_youtube_auth(auth, path)
    return YouTubePairResult(token_file=path, screen_name=auth.screen_name)


async def get_youtube_status(
    *,
    device_name: str = DEFAULT_DEVICE_NAME,
    token_file: Path | None = None,
    status_function: StatusFunction = lounge_status,
    refresh_function: AuthFunction = refresh_lounge,
) -> YouTubeStatus:
    path = default_youtube_file() if token_file is None else token_file
    try:
        auth = load_youtube_auth(path)
    except YouTubeLoungeError as error:
        return YouTubeStatus(paired=False, token_file=path, reason=str(error))
    try:
        refreshed = await refresh_function(auth, device_name)
        save_youtube_auth(refreshed, path)
        status = await status_function(refreshed, device_name)
    except (RuntimeError, OSError) as error:
        return YouTubeStatus(
            paired=True,
            token_file=path,
            screen_name=auth.screen_name,
            reason=str(error),
        )
    return YouTubeStatus(
        paired=True,
        token_file=path,
        screen_name=refreshed.screen_name,
        available=status.available,
    )


async def play_youtube_video(
    video: str,
    *,
    device_name: str = DEFAULT_DEVICE_NAME,
    token_file: Path | None = None,
    play_function: VideoFunction = lounge_play_video,
) -> YouTubeCommandResult:
    video_id = normalise_youtube_video_id(video)
    return await _run_youtube_auth_command(
        f"Playing YouTube video {video_id}.",
        token_file=token_file,
        device_name=device_name,
        function=lambda auth, name: play_function(auth, name, video_id),
    )


async def pause_youtube(
    *,
    device_name: str = DEFAULT_DEVICE_NAME,
    token_file: Path | None = None,
    pause_function: AuthFunction = lounge_pause,
) -> YouTubeCommandResult:
    return await _run_youtube_auth_command(
        "Paused YouTube.",
        token_file=token_file,
        device_name=device_name,
        function=pause_function,
    )


async def resume_youtube(
    *,
    device_name: str = DEFAULT_DEVICE_NAME,
    token_file: Path | None = None,
    resume_function: AuthFunction = lounge_resume,
) -> YouTubeCommandResult:
    return await _run_youtube_auth_command(
        "Resumed YouTube.",
        token_file=token_file,
        device_name=device_name,
        function=resume_function,
    )


async def seek_youtube(
    seconds: float,
    *,
    device_name: str = DEFAULT_DEVICE_NAME,
    token_file: Path | None = None,
    seek_function: SeekFunction = lounge_seek,
) -> YouTubeCommandResult:
    if seconds < 0:
        msg = "Seek time must be zero or higher."
        raise YouTubeLoungeError(msg)
    return await _run_youtube_auth_command(
        f"Seeked YouTube to {seconds:g} seconds.",
        token_file=token_file,
        device_name=device_name,
        function=lambda auth, name: seek_function(auth, name, seconds),
    )


async def next_youtube(
    *,
    device_name: str = DEFAULT_DEVICE_NAME,
    token_file: Path | None = None,
    next_function: AuthFunction = lounge_next,
) -> YouTubeCommandResult:
    return await _run_youtube_auth_command(
        "Skipped to the next YouTube video.",
        token_file=token_file,
        device_name=device_name,
        function=next_function,
    )


async def previous_youtube(
    *,
    device_name: str = DEFAULT_DEVICE_NAME,
    token_file: Path | None = None,
    previous_function: AuthFunction = lounge_previous,
) -> YouTubeCommandResult:
    return await _run_youtube_auth_command(
        "Went to the previous YouTube video.",
        token_file=token_file,
        device_name=device_name,
        function=previous_function,
    )


async def disconnect_youtube(
    *,
    device_name: str = DEFAULT_DEVICE_NAME,
    token_file: Path | None = None,
    disconnect_function: AuthFunction = lounge_disconnect,
) -> YouTubeCommandResult:
    return await _run_youtube_auth_command(
        "Disconnected from YouTube.",
        token_file=token_file,
        device_name=device_name,
        function=disconnect_function,
    )


async def _run_youtube_auth_command(
    message: str,
    *,
    token_file: Path | None,
    device_name: str,
    function: AuthFunction,
) -> YouTubeCommandResult:
    path = default_youtube_file() if token_file is None else token_file
    auth = load_youtube_auth(path)
    try:
        updated = await function(auth, device_name)
    except Exception as error:
        msg = f"YouTube command failed: {error}"
        raise YouTubeLoungeError(msg) from error
    save_youtube_auth(updated, path)
    return YouTubeCommandResult(message=message, token_file=path)


def _youtube_video_id_candidate(value: str) -> str | None:
    if YOUTUBE_ID_PATTERN.fullmatch(value):
        return value

    parsed = urlparse(value)
    if not parsed.netloc:
        return None

    query_id = parse_qs(parsed.query).get("v", [None])[0]
    if query_id is not None:
        return query_id

    path_parts = [part for part in parsed.path.split("/") if part]
    return _youtube_video_id_from_path(parsed.netloc, path_parts)


def _youtube_video_id_from_path(netloc: str, path_parts: list[str]) -> str | None:
    if not path_parts:
        candidate = None
    elif netloc.endswith("youtu.be"):
        candidate = path_parts[0]
    elif path_parts[0] in {"shorts", "embed", "live"} and len(path_parts) > 1:
        candidate = path_parts[1]
    else:
        candidate = None
    return candidate
