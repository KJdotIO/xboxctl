from pathlib import Path

import pytest

from xboxctl import mcp_server
from xboxctl.providers.select import ProviderName


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


def test_mcp_provider_args_default_to_normal_xbox_commands() -> None:
    # Given: no MCP server options are passed.
    arguments: list[str] = []

    # When: the provider is parsed.
    provider = mcp_server.provider_from_args(arguments)

    # Then: normal Xbox commands are selected.
    assert provider == ProviderName.REAL


def test_mcp_provider_args_accept_fake_provider() -> None:
    # Given: fake mode is requested for local tests.
    arguments = ["--provider", "fake"]

    # When: the provider is parsed.
    provider = mcp_server.provider_from_args(arguments)

    # Then: fake mode is selected.
    assert provider == ProviderName.FAKE
