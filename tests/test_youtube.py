from pathlib import Path

import pytest

from xboxctl.youtube import (
    YouTubeLoungeError,
    default_youtube_file,
    disconnect_youtube,
    get_youtube_status,
    load_youtube_auth,
    normalise_youtube_video_id,
    pair_youtube,
    pause_youtube,
    play_youtube_video,
    save_youtube_auth,
    seek_youtube,
)
from xboxctl.youtube_lounge import LoungeAuth, LoungeStatus


def test_default_youtube_file_uses_xbox_app_data_dir() -> None:
    # Given: Xbox tokens are stored in the normal app data directory.
    environ = {"XBOXCTL_TOKENS_FILE": "/tmp/xbox/tokens.json"}

    # When: the YouTube token path is resolved.
    path = default_youtube_file(environ)

    # Then: YouTube pairing lives beside the Xbox auth file.
    assert path == Path("/tmp/xbox/youtube_lounge.json")


def test_default_youtube_file_accepts_explicit_override() -> None:
    # Given: a YouTube-specific token file is configured.
    environ = {
        "XBOXCTL_TOKENS_FILE": "/tmp/xbox/tokens.json",
        "XBOXCTL_YOUTUBE_FILE": "/tmp/youtube.json",
    }

    # When: the YouTube token path is resolved.
    path = default_youtube_file(environ)

    # Then: the YouTube override wins.
    assert path == Path("/tmp/youtube.json")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ],
)
def test_normalise_youtube_video_id_accepts_ids_and_urls(
    value: str,
    expected: str,
) -> None:
    assert normalise_youtube_video_id(value) == expected


def test_normalise_youtube_video_id_rejects_non_video_values() -> None:
    with pytest.raises(YouTubeLoungeError, match="Expected a YouTube video ID"):
        _ = normalise_youtube_video_id("https://www.youtube.com/@Xbox")


def test_save_and_load_youtube_auth_round_trip(tmp_path: Path) -> None:
    # Given: a paired YouTube auth payload.
    token_file = tmp_path / "youtube.json"
    auth = LoungeAuth(
        screen_id="screen-1",
        lounge_token="token-1",
        screen_name="Xbox YouTube",
    )

    # When: the payload is saved and loaded.
    save_youtube_auth(auth, token_file)
    loaded = load_youtube_auth(token_file)

    # Then: the important pairing fields are preserved.
    assert loaded == auth


@pytest.mark.anyio
async def test_pair_youtube_saves_pairing_result(tmp_path: Path) -> None:
    # Given: a fake YouTube pairing response.
    token_file = tmp_path / "youtube.json"

    async def pair_stub(pairing_code: str, device_name: str) -> LoungeAuth:
        assert pairing_code == "123456"
        assert device_name == "xboxctl-test"
        return LoungeAuth(
            screen_id="screen-1",
            lounge_token="token-1",
            screen_name="Xbox YouTube",
        )

    # When: pairing succeeds.
    result = await pair_youtube(
        "123456",
        device_name="xboxctl-test",
        token_file=token_file,
        pair_function=pair_stub,
    )

    # Then: the token file is written for later commands.
    assert result.screen_name == "Xbox YouTube"
    assert load_youtube_auth(token_file).screen_id == "screen-1"


@pytest.mark.anyio
async def test_play_youtube_video_loads_auth_runs_command_and_saves_refresh(
    tmp_path: Path,
) -> None:
    # Given: YouTube has already been paired.
    token_file = tmp_path / "youtube.json"
    save_youtube_auth(LoungeAuth("screen-1", "token-1", "Xbox YouTube"), token_file)

    async def play_stub(
        auth: LoungeAuth,
        device_name: str,
        video_id: str,
    ) -> LoungeAuth:
        assert auth.screen_id == "screen-1"
        assert auth.lounge_token == "token-1"
        assert device_name == "xboxctl-test"
        assert video_id == "dQw4w9WgXcQ"
        return LoungeAuth("screen-1", "token-2", auth.screen_name)

    # When: a video URL is played.
    result = await play_youtube_video(
        "https://youtu.be/dQw4w9WgXcQ",
        device_name="xboxctl-test",
        token_file=token_file,
        play_function=play_stub,
    )

    # Then: the command message is clear and refreshed auth is retained.
    assert result.message == "Playing YouTube video dQw4w9WgXcQ."
    assert load_youtube_auth(token_file).lounge_token == "token-2"


@pytest.mark.anyio
async def test_youtube_status_reports_pairing_and_availability(
    tmp_path: Path,
) -> None:
    # Given: YouTube has already been paired.
    token_file = tmp_path / "youtube.json"
    save_youtube_auth(LoungeAuth("screen-1", "token-1", "Xbox YouTube"), token_file)

    async def refresh_stub(auth: LoungeAuth, device_name: str) -> LoungeAuth:
        assert device_name == "xboxctl-test"
        return LoungeAuth(auth.screen_id, "token-2", auth.screen_name)

    async def status_stub(auth: LoungeAuth, device_name: str) -> LoungeStatus:
        assert auth.lounge_token == "token-2"
        assert device_name == "xboxctl-test"
        return LoungeStatus(available=True)

    # When: status is checked.
    result = await get_youtube_status(
        device_name="xboxctl-test",
        token_file=token_file,
        refresh_function=refresh_stub,
        status_function=status_stub,
    )

    # Then: the paired app is reported as reachable.
    assert result.paired is True
    assert result.available is True
    assert result.screen_name == "Xbox YouTube"
    assert load_youtube_auth(token_file).lounge_token == "token-2"


@pytest.mark.anyio
async def test_mutating_youtube_commands_require_pairing(tmp_path: Path) -> None:
    # Given: no YouTube token file exists.
    token_file = tmp_path / "missing.json"

    # When/Then: mutating commands fail with the pairing instruction.
    with pytest.raises(YouTubeLoungeError, match="YouTube is not paired yet"):
        _ = await pause_youtube(token_file=token_file)


@pytest.mark.anyio
async def test_seek_rejects_negative_seconds(tmp_path: Path) -> None:
    token_file = tmp_path / "youtube.json"
    save_youtube_auth(LoungeAuth("screen-1", "token-1"), token_file)

    with pytest.raises(YouTubeLoungeError, match="zero or higher"):
        _ = await seek_youtube(-1, token_file=token_file)


@pytest.mark.anyio
async def test_disconnect_uses_injected_command(tmp_path: Path) -> None:
    # Given: YouTube has already been paired.
    token_file = tmp_path / "youtube.json"
    save_youtube_auth(LoungeAuth("screen-1", "token-1"), token_file)

    async def disconnect_stub(auth: LoungeAuth, device_name: str) -> LoungeAuth:
        assert device_name == "xboxctl-test"
        return LoungeAuth(auth.screen_id, "token-2", auth.screen_name)

    # When: disconnect is requested.
    result = await disconnect_youtube(
        device_name="xboxctl-test",
        token_file=token_file,
        disconnect_function=disconnect_stub,
    )

    # Then: the command path is the same as the other YouTube controls.
    assert result.message == "Disconnected from YouTube."
