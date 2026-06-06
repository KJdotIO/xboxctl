from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

import pytest
from mcp.types import ImageContent, TextContent

from xboxctl import mcp_server
from xboxctl.mcp_content import screenshot_content
from xboxctl.observe import ObserveCaptureFormat
from xboxctl.providers.select import ProviderName
from xboxctl.youtube import YouTubeCommandResult, YouTubeStatus


def test_mcp_status_returns_fake_console_when_fake_provider_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the MCP server is using the explicit fake provider.
    monkeypatch.setattr(mcp_server, "selected_provider", ProviderName.FAKE)

    # When: the status tool is called.
    payload = mcp_server.get_xbox_status()

    # Then: stable sample console state is returned.
    assert payload["name"] == "Living Room Series X"
    assert payload["active_title"] == "Halo Infinite"


def test_mcp_launch_returns_action_message_when_fake_provider_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the MCP server is using the explicit fake provider.
    monkeypatch.setattr(mcp_server, "selected_provider", ProviderName.FAKE)

    # When: an app is launched through the MCP tool.
    payload = mcp_server.launch_xbox("Halo")

    # Then: the provider action message is returned as structured output.
    assert payload == {"message": "Launching Halo Infinite on Living Room Series X."}


def test_mcp_auth_validate_reports_missing_token_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: Xbox auth points at a missing token file.
    token_file = tmp_path / "tokens.json"
    monkeypatch.setenv("XBOXCTL_TOKENS_FILE", str(token_file))

    # When: auth is validated through the MCP tool.
    payload = mcp_server.validate_xbox_auth()

    # Then: the tool reports setup is still needed.
    assert payload["valid"] is False
    assert payload["reason"] == "missing_file"
    assert payload["can_use_xbox_commands"] is False


def test_mcp_observe_status_reports_missing_session_file(tmp_path: Path) -> None:
    # Given: no observe session file exists.
    session_file = tmp_path / "session.json"

    # When: observe status is requested through the MCP tool.
    payload = mcp_server.get_observe_status(str(session_file))

    # Then: the missing local session is reported without failing.
    assert payload["exists"] is False
    assert payload["active"] is False
    assert payload["reason"] == "missing"


def test_mcp_observe_cleanup_removes_invalid_session_file(tmp_path: Path) -> None:
    # Given: an invalid observe session file exists.
    session_file = tmp_path / "session.json"
    _ = session_file.write_text("not json", encoding="utf-8")

    # When: cleanup is requested through the MCP tool.
    payload = mcp_server.cleanup_observe(str(session_file))

    # Then: the stale session file is removed.
    assert payload["removed"] is True
    assert payload["stopped"] is False
    assert "Removed stale observe session" in payload["message"]
    assert not session_file.exists()


def test_mcp_observe_capture_returns_valid_mcp_image_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an observe capture writes a small PNG file.
    image_path = tmp_path / "capture.png"
    png_bytes = b"".join(
        (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
            b"\x00\x00\x00\x01\x00\x00\x00\x01",
            b"\x08\x02\x00\x00\x00\x90wS\xde",
        ),
    )
    _ = image_path.write_bytes(png_bytes)

    def capture_stub(
        output: str | None = None,
        session_file: str = mcp_server.DEFAULT_SESSION_FILE_TEXT,
        image_format: ObserveCaptureFormat = ObserveCaptureFormat.JPEG,
        width: int = 960,
        quality: int = 72,
    ) -> Path:
        _ = (output, session_file, image_format, width, quality)
        return image_path

    monkeypatch.setattr(mcp_server, "capture_xbox_observe", capture_stub)

    # When: the MCP capture helper prepares its response.
    content = mcp_server.capture_xbox_observe_content()

    # Then: strict MCP content models are returned, not FastMCP helper objects.
    assert isinstance(content[0], TextContent)
    assert isinstance(content[1], ImageContent)
    assert content[1].type == "image"
    assert content[1].mimeType == "image/png"
    assert content[1].data.startswith("iVBORw0KGgo")


def test_screenshot_content_serialises_image_as_base64_mcp_content(
    tmp_path: Path,
) -> None:
    # Given: a screenshot file exists on disk.
    image_path = tmp_path / "capture.jpeg"
    _ = image_path.write_bytes(b"fake-jpeg-bytes")

    # When: screenshot content is built for an MCP response.
    content = screenshot_content(image_path)

    # Then: the image is represented as canonical MCP image content.
    assert isinstance(content[0], TextContent)
    assert isinstance(content[1], ImageContent)
    assert content[1].mimeType == "image/jpeg"
    assert content[1].data == "ZmFrZS1qcGVnLWJ5dGVz"


def test_mcp_provider_args_default_to_normal_xbox_commands() -> None:
    # Given: no MCP server options are passed.
    arguments: list[str] = []

    # When: the MCP server config is parsed.
    config = mcp_server.parse_mcp_config(arguments)

    # Then: normal Xbox commands are selected.
    assert config.provider == ProviderName.REAL
    assert config.transport == mcp_server.McpTransport.STDIO


def test_mcp_provider_args_accept_fake_provider() -> None:
    # Given: fake mode is requested for local tests.
    arguments = ["--provider", "fake"]

    # When: the MCP server config is parsed.
    config = mcp_server.parse_mcp_config(arguments)

    # Then: fake mode is selected.
    assert config.provider == ProviderName.FAKE


def test_mcp_provider_args_accept_http_defaults() -> None:
    # Given: HTTP mode is requested for a local tunnel.
    arguments = ["--http"]

    # When: the MCP server config is parsed.
    config = mcp_server.parse_mcp_config(arguments)

    # Then: local HTTP defaults are selected.
    assert config.transport == mcp_server.McpTransport.HTTP
    assert config.host == "127.0.0.1"
    assert config.port == 3000
    assert config.path == "/mcp"


def test_mcp_provider_args_accept_sse_defaults() -> None:
    # Given: SSE mode is requested for clients that expect the older MCP HTTP transport.
    arguments = ["--sse"]

    # When: the MCP server config is parsed.
    config = mcp_server.parse_mcp_config(arguments)

    # Then: local SSE defaults are selected.
    assert config.transport == mcp_server.McpTransport.SSE
    assert config.host == "127.0.0.1"
    assert config.port == 3000
    assert config.path == "/sse"


def test_mcp_provider_args_accept_dual_http_defaults() -> None:
    # Given: combined HTTP mode is requested for clients that probe transports.
    arguments = ["--dual-http"]

    # When: the MCP server config is parsed.
    config = mcp_server.parse_mcp_config(arguments)

    # Then: local combined HTTP defaults are selected.
    assert config.transport == mcp_server.McpTransport.DUAL_HTTP
    assert config.host == "127.0.0.1"
    assert config.port == 3000
    assert config.path is None


def test_mcp_provider_args_accept_custom_http_address() -> None:
    # Given: a custom local HTTP address is requested.
    arguments = ["--http", "--host", "localhost", "--port", "3210", "--path", "/xbox"]

    # When: the MCP server config is parsed.
    config = mcp_server.parse_mcp_config(arguments)

    # Then: the custom address is selected.
    assert config.transport == mcp_server.McpTransport.HTTP
    assert config.host == "localhost"
    assert config.port == 3210
    assert config.path == "/xbox"


def test_mcp_provider_args_accept_allowed_hosts() -> None:
    # Given: public tunnel hostnames are explicitly trusted.
    arguments = [
        "--dual-http",
        "--allow-host",
        "xboxctl.example.test",
        "--allow-host",
        "example.test",
    ]

    # When: the MCP server config is parsed.
    config = mcp_server.parse_mcp_config(arguments)

    # Then: both hostnames are preserved.
    assert config.allowed_hosts == ("xboxctl.example.test", "example.test")


@pytest.mark.anyio
async def test_mcp_youtube_status_returns_structured_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the YouTube status helper reports a paired app.
    async def status_stub(device_name: str = "xboxctl") -> YouTubeStatus:
        assert device_name == "xboxctl"
        return YouTubeStatus(
            paired=True,
            available=True,
            screen_name="Xbox YouTube",
            token_file=tmp_path / "youtube.json",
        )

    monkeypatch.setattr(mcp_server, "get_youtube_status", status_stub)

    # When: the MCP status wrapper is called.
    status_tool = cast(
        "Callable[[], Awaitable[mcp_server.YouTubeStatusPayload]]",
        mcp_server.youtube_status,
    )
    payload = await status_tool()

    # Then: the result is simple JSON for agents.
    assert payload["paired"] is True
    assert payload["available"] is True
    assert payload["screen_name"] == "Xbox YouTube"


@pytest.mark.anyio
async def test_mcp_youtube_play_returns_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the YouTube play helper succeeds.
    async def play_stub(video: str) -> YouTubeCommandResult:
        assert video == "dQw4w9WgXcQ"
        return YouTubeCommandResult(
            message="Playing YouTube video dQw4w9WgXcQ.",
            token_file=tmp_path / "youtube.json",
        )

    monkeypatch.setattr(mcp_server, "play_youtube_video", play_stub)

    # When: the MCP play wrapper is called.
    play_tool = cast(
        "Callable[[str], Awaitable[mcp_server.MessagePayload]]",
        mcp_server.youtube_play,
    )
    payload = await play_tool("dQw4w9WgXcQ")

    # Then: the action message is returned.
    assert payload == {"message": "Playing YouTube video dQw4w9WgXcQ."}
