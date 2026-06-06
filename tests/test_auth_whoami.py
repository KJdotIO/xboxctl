import json
from pathlib import Path

from _pytest.monkeypatch import MonkeyPatch
from typer.testing import CliRunner, Result

from xboxctl.auth import AuthValidationReason
from xboxctl.auth_identity import WhoamiResult
from xboxctl.cli import app


def run_cli_with_env(arguments: list[str], env: dict[str, str]) -> Result:
    runner = CliRunner(env=env)
    return runner.invoke(app, arguments)


def write_valid_token_shape(token_file: Path) -> None:
    payload = {
        "token_type": "bearer",
        "expires_in": 3600,
        "scope": "XboxLive.signin XboxLive.offline_access",
        "access_token": "access",
        "refresh_token": "refresh",
        "user_id": "12345",
        "issued": "2026-06-06T12:00:00Z",
    }
    _ = token_file.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def test_auth_whoami_json_prints_account_summary(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: auth is valid and the real identity call returns a profile summary.
    token_file = tmp_path / "tokens.json"
    write_valid_token_shape(token_file)
    result = WhoamiResult(
        xuid="12345",
        gamertag="ActualAccount",
        modern_gamertag="ActualAccount",
        unique_modern_gamertag="ActualAccount#1234",
        gamerscore="9001",
        account_tier="Gold",
    )

    def return_whoami(_tokens_file: Path) -> WhoamiResult:
        return result

    monkeypatch.setattr("xboxctl.auth_cli.fetch_whoami", return_whoami)

    # When: whoami is requested as JSON.
    cli_result = run_cli_with_env(
        ["auth", "whoami", "--json"],
        {"XBOXCTL_TOKENS_FILE": str(token_file)},
    )

    # Then: a small account summary is printed.
    assert cli_result.exit_code == 0
    assert '"gamertag": "ActualAccount"' in cli_result.stdout
    assert '"unique_modern_gamertag": "ActualAccount#1234"' in cli_result.stdout
    assert '"access_token"' not in cli_result.stdout
    assert '"refresh_token"' not in cli_result.stdout


def test_auth_whoami_reports_invalid_auth_without_network(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: the token file is missing.
    token_file = tmp_path / "tokens.json"
    called = False

    def fail_if_called() -> WhoamiResult:
        nonlocal called
        called = True
        return WhoamiResult(
            xuid="unexpected",
            gamertag=None,
            modern_gamertag=None,
            unique_modern_gamertag=None,
            gamerscore=None,
            account_tier=None,
        )

    monkeypatch.setattr("xboxctl.auth_cli.fetch_whoami", fail_if_called)

    # When: whoami is requested.
    cli_result = run_cli_with_env(
        ["auth", "whoami", "--json"],
        {"XBOXCTL_TOKENS_FILE": str(token_file)},
    )

    # Then: the command refuses before any network identity call.
    assert cli_result.exit_code == 1
    assert '"valid": false' in cli_result.stdout
    assert f'"reason": "{AuthValidationReason.MISSING_FILE.value}"' in cli_result.stdout
    assert called is False
