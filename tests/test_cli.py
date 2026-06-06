from pathlib import Path

from typer.testing import CliRunner, Result

from xboxctl.cli import app


def run_cli(arguments: list[str]) -> Result:
    runner = CliRunner()
    return runner.invoke(app, arguments)


def run_cli_with_env(arguments: list[str], env: dict[str, str]) -> Result:
    runner = CliRunner(env=env)
    return runner.invoke(app, arguments)


def fake_arguments(arguments: list[str]) -> list[str]:
    return ["--provider", "fake", *arguments]


def test_version_prints_version() -> None:
    # Given: the installed CLI app.
    arguments = ["--version"]

    # When: the version flag is requested.
    result = run_cli(arguments)

    # Then: the current package version is printed.
    assert result.exit_code == 0
    assert "xboxctl 0.1.0" in result.stdout


def test_status_json_returns_sample_console_state() -> None:
    # Given: the offline fake provider is selected explicitly.
    arguments = fake_arguments(["status", "--json"])

    # When: status is requested as JSON.
    result = run_cli(arguments)

    # Then: the stable sample console state is returned.
    assert result.exit_code == 0
    assert '"name": "Living Room Series X"' in result.stdout
    assert '"power_state": "on"' in result.stdout
    assert '"active_title": "Halo Infinite"' in result.stdout


def test_default_consoles_requires_auth_without_token_file(tmp_path: Path) -> None:
    # Given: no provider flag or environment override, and no Xbox token file.
    token_file = tmp_path / "tokens.json"
    arguments = ["consoles"]

    # When: consoles are listed.
    result = run_cli_with_env(arguments, {"XBOXCTL_TOKENS_FILE": str(token_file)})

    # Then: the CLI asks for auth instead of falling back to fake data.
    assert result.exit_code == 1
    assert "Xbox is not configured." in result.output
    assert "uv run xboxctl auth login" in result.output


def test_fake_provider_can_be_selected_explicitly() -> None:
    # Given: the provider is selected with the global option.
    arguments = ["--provider", "fake", "status", "--json"]

    # When: status is requested.
    result = run_cli(arguments)

    # Then: the fake provider returns the same stable console state.
    assert result.exit_code == 0
    assert '"name": "Living Room Series X"' in result.stdout


def test_default_provider_without_auth_fails_with_setup_message() -> None:
    # Given: Xbox commands are requested without credentials.
    runner = CliRunner(env={"XBOXCTL_TOKENS_FILE": "/missing/xboxctl/tokens.json"})
    arguments = ["consoles"]

    # When: consoles are listed.
    result = runner.invoke(app, arguments)

    # Then: the CLI gives a clear setup failure without pretending success.
    assert result.exit_code == 1
    assert "Xbox is not configured." in result.output
    assert "uv run xboxctl auth login" in result.output
    assert "No console command was sent." in result.output


def test_provider_can_be_selected_from_environment() -> None:
    # Given: the default provider is requested through the environment.
    runner = CliRunner(
        env={
            "XBOXCTL_PROVIDER": "real",
            "XBOXCTL_TOKENS_FILE": "/missing/xboxctl/tokens.json",
        },
    )

    # When: status is requested.
    result = runner.invoke(app, ["status"])

    # Then: the same explicit setup message is shown.
    assert result.exit_code == 1
    assert "Xbox is not configured." in result.output


def test_auth_status_reports_missing_token_file(tmp_path: Path) -> None:
    # Given: the configured token file path does not exist.
    token_file = tmp_path / "tokens.json"
    arguments = ["auth", "status", "--json"]

    # When: auth status is requested.
    result = run_cli_with_env(arguments, {"XBOXCTL_TOKENS_FILE": str(token_file)})

    # Then: the CLI reports that Xbox auth is not configured.
    assert result.exit_code == 1
    assert '"configured": false' in result.stdout
    assert f'"tokens_file": "{token_file}"' in result.stdout
    assert "uv run xboxctl auth login" in result.stdout


def test_auth_status_reports_found_file_without_reading_it(tmp_path: Path) -> None:
    # Given: a token file exists, even if its contents are not validated yet.
    token_file = tmp_path / "tokens.json"
    _ = token_file.write_text("not json", encoding="utf-8")
    arguments = ["auth", "status"]

    # When: auth status is requested.
    result = run_cli_with_env(arguments, {"XBOXCTL_TOKENS_FILE": str(token_file)})

    # Then: the CLI reports file presence without claiming token validity.
    assert result.exit_code == 0
    assert "Token file found" in result.stdout
    assert "not validated" in result.stdout


def test_auth_instructions_show_xboxctl_login_setup_command() -> None:
    # Given: a user wants the safe setup path for Xbox auth.
    arguments = ["auth", "instructions"]

    # When: auth instructions are requested.
    result = run_cli(arguments)

    # Then: the CLI prints the external python-xbox auth steps.
    assert result.exit_code == 0
    assert "uv sync --extra real" in result.stdout
    assert "uv run xboxctl auth login" in result.stdout
    assert "uv run xboxctl auth login --client-id <client-id>" in result.stdout
    assert "http://localhost:8080/auth/callback" in result.stdout
    assert "--client-secret" not in result.stdout


def test_auth_validate_reports_missing_token_file(tmp_path: Path) -> None:
    # Given: the configured token file path does not exist.
    token_file = tmp_path / "tokens.json"
    arguments = ["auth", "validate", "--json"]

    # When: auth validation is requested.
    result = run_cli_with_env(arguments, {"XBOXCTL_TOKENS_FILE": str(token_file)})

    # Then: the CLI reports that the token file is missing.
    assert result.exit_code == 1
    assert '"valid": false' in result.stdout
    assert '"reason": "missing_file"' in result.stdout
    assert f'"tokens_file": "{token_file}"' in result.stdout


def test_auth_validate_reports_malformed_token_json(tmp_path: Path) -> None:
    # Given: the token file exists but is not JSON.
    token_file = tmp_path / "tokens.json"
    _ = token_file.write_text("not json", encoding="utf-8")
    arguments = ["auth", "validate", "--json"]

    # When: auth validation is requested.
    result = run_cli_with_env(arguments, {"XBOXCTL_TOKENS_FILE": str(token_file)})

    # Then: the CLI reports malformed JSON without leaking file contents.
    assert result.exit_code == 1
    assert '"valid": false' in result.stdout
    assert '"reason": "malformed_json"' in result.stdout
    assert "not json" not in result.stdout


def test_auth_validate_reports_wrong_token_json_shape(tmp_path: Path) -> None:
    # Given: the token file is JSON but not an object.
    token_file = tmp_path / "tokens.json"
    _ = token_file.write_text("[]", encoding="utf-8")
    arguments = ["auth", "validate", "--json"]

    # When: auth validation is requested.
    result = run_cli_with_env(arguments, {"XBOXCTL_TOKENS_FILE": str(token_file)})

    # Then: the CLI reports malformed JSON shape without crashing.
    assert result.exit_code == 1
    assert '"valid": false' in result.stdout
    assert '"reason": "malformed_json"' in result.stdout


def test_auth_validate_reports_missing_token_fields(tmp_path: Path) -> None:
    # Given: the token file is JSON but lacks required OAuth fields.
    token_file = tmp_path / "tokens.json"
    _ = token_file.write_text('{"access_token": "abc"}', encoding="utf-8")
    arguments = ["auth", "validate", "--json"]

    # When: auth validation is requested.
    result = run_cli_with_env(arguments, {"XBOXCTL_TOKENS_FILE": str(token_file)})

    # Then: the CLI reports the missing fields by name.
    assert result.exit_code == 1
    assert '"valid": false' in result.stdout
    assert '"reason": "missing_fields"' in result.stdout
    assert "refresh_token" in result.stdout
    assert "user_id" in result.stdout


def test_auth_validate_accepts_python_xbox_token_shape(tmp_path: Path) -> None:
    # Given: the token file has the OAuth fields produced by python-xbox.
    token_file = tmp_path / "tokens.json"
    _ = token_file.write_text(
        """
        {
          "token_type": "bearer",
          "expires_in": 3600,
          "scope": "XboxLive.signin XboxLive.offline_access",
          "access_token": "access",
          "refresh_token": "refresh",
          "user_id": "12345",
          "issued": "2026-06-06T12:00:00Z"
        }
        """,
        encoding="utf-8",
    )
    arguments = ["auth", "validate", "--json"]

    # When: auth validation is requested.
    result = run_cli_with_env(arguments, {"XBOXCTL_TOKENS_FILE": str(token_file)})

    # Then: the CLI reports that local token shape is valid.
    assert result.exit_code == 0
    assert '"valid": true' in result.stdout


def test_observe_status_reports_missing_session_file(tmp_path: Path) -> None:
    # Given: there is no persistent observe session file.
    session_file = tmp_path / "missing-session.json"

    # When: observe status is requested.
    result = run_cli(["observe", "status", "--session-file", str(session_file)])

    # Then: the CLI reports the missing session without failing.
    assert result.exit_code == 0
    assert "No observe session" in result.stdout


def test_observe_cleanup_removes_invalid_session_file(tmp_path: Path) -> None:
    # Given: an invalid persistent observe session file and stale log exist.
    session_file = tmp_path / "session.json"
    log_file = tmp_path / "session.log"
    _ = session_file.write_text("not json", encoding="utf-8")
    _ = log_file.write_text("old log", encoding="utf-8")

    # When: observe cleanup is requested.
    result = run_cli(["observe", "cleanup", "--session-file", str(session_file)])

    # Then: the stale files are removed without trying to control the console.
    assert result.exit_code == 0
    assert "Removed stale observe session" in result.stdout
    assert not session_file.exists()
    assert not log_file.exists()


def test_auth_login_dry_run_prints_consent_handoff(tmp_path: Path) -> None:
    # Given: auth login is run in dry-run mode with a test token path.
    token_file = tmp_path / "tokens.json"
    arguments = ["auth", "login", "--dry-run"]

    # When: the command is invoked.
    result = run_cli_with_env(arguments, {"XBOXCTL_TOKENS_FILE": str(token_file)})

    # Then: it prints the Microsoft consent handoff without starting auth.
    assert result.exit_code == 0
    assert "Microsoft sign-in is required" in result.stdout
    assert "Xbox Live access" in result.stdout
    assert "choose the Microsoft account" in result.stdout
    assert "No console command was sent." in result.stdout
    assert "uv run python -m xboxctl.auth_flow" in result.stdout
    assert f"--tokens {token_file}" in result.stdout
    assert "--prompt select_account" in result.stdout


def test_auth_login_dry_run_accepts_custom_client_id(tmp_path: Path) -> None:
    # Given: auth login is run with a custom client id.
    token_file = tmp_path / "tokens.json"
    arguments = ["auth", "login", "--dry-run", "--client-id", "client-123"]

    # When: the command is invoked.
    result = run_cli_with_env(arguments, {"XBOXCTL_TOKENS_FILE": str(token_file)})

    # Then: the helper command includes the custom client id.
    assert result.exit_code == 0
    assert "--client-id client-123" in result.stdout


def test_auth_login_dry_run_accepts_login_prompt(tmp_path: Path) -> None:
    # Given: auth login is run with the stricter login prompt.
    token_file = tmp_path / "tokens.json"
    arguments = ["auth", "login", "--dry-run", "--prompt", "login"]

    # When: the command is invoked.
    result = run_cli_with_env(arguments, {"XBOXCTL_TOKENS_FILE": str(token_file)})

    # Then: the helper command asks Microsoft to force login.
    assert result.exit_code == 0
    assert "--prompt login" in result.stdout


def test_auth_login_dry_run_does_not_print_secret(tmp_path: Path) -> None:
    # Given: a client secret is present for the upstream helper environment.
    token_file = tmp_path / "tokens.json"
    env = {
        "XBOXCTL_TOKENS_FILE": str(token_file),
        "CLIENT_SECRET": "super-secret-value",
    }
    arguments = ["auth", "login", "--dry-run"]

    # When: the command is invoked.
    result = run_cli_with_env(arguments, env)

    # Then: the secret value is never printed.
    assert result.exit_code == 0
    assert "super-secret-value" not in result.stdout
    assert "--client-secret" not in result.stdout


def test_storage_json_reports_usage() -> None:
    # Given: the offline fake provider is selected explicitly.
    arguments = fake_arguments(["storage", "--json"])

    # When: storage is requested as JSON.
    result = run_cli(arguments)

    # Then: storage totals are shown in gigabytes.
    assert result.exit_code == 0
    assert '"name": "Internal SSD"' in result.stdout
    assert '"used_gb": 512' in result.stdout
    assert '"total_gb": 802' in result.stdout


def test_apps_json_lists_known_titles() -> None:
    # Given: the offline fake provider is selected explicitly.
    arguments = fake_arguments(["apps", "--json"])

    # When: apps are requested as JSON.
    result = run_cli(arguments)

    # Then: known titles and product IDs are present.
    assert result.exit_code == 0
    assert '"name": "Halo Infinite"' in result.stdout
    assert '"product_id": "9PP5G1F0C2B6"' in result.stdout


def test_launch_refuses_without_confirm() -> None:
    # Given: a mutating launch request without confirmation.
    arguments = ["launch", "Halo"]

    # When: the command is invoked.
    result = run_cli(arguments)

    # Then: the command refuses to run.
    assert result.exit_code == 2
    assert "Add --confirm to run mutating commands." in result.output


def test_launch_accepts_known_app_with_confirm() -> None:
    # Given: a confirmed launch request for a known game.
    arguments = fake_arguments(["launch", "Halo", "--confirm"])

    # When: the command is invoked.
    result = run_cli(arguments)

    # Then: the fake provider reports the launch action.
    assert result.exit_code == 0
    assert "Launching Halo Infinite on Living Room Series X." in result.stdout


def test_press_rejects_invalid_repeat() -> None:
    # Given: a confirmed button press with an invalid repeat count.
    arguments = ["press", "a", "--repeat", "0", "--confirm"]

    # When: the command is invoked.
    result = run_cli(arguments)

    # Then: the CLI rejects the malformed repeat value.
    assert result.exit_code == 2
    assert "repeat must be between 1 and 20" in result.output


def test_text_rejects_empty_input() -> None:
    # Given: a confirmed text command with only whitespace.
    arguments = ["text", "   ", "--confirm"]

    # When: the command is invoked.
    result = run_cli(arguments)

    # Then: the CLI refuses to send an empty text payload.
    assert result.exit_code == 2
    assert "text must not be empty" in result.output


def test_text_keeps_meaningful_outer_spaces() -> None:
    # Given: a confirmed text command with meaningful surrounding spaces.
    arguments = fake_arguments(["text", " hello ", "--confirm"])

    # When: the command is invoked.
    result = run_cli(arguments)

    # Then: the fake provider receives the original text.
    assert result.exit_code == 0
    assert "Sent text to Living Room Series X:  hello " in result.output


def test_doctor_reports_fake_mode_and_route_for_console_ip() -> None:
    # Given: a local route diagnostic request for a reachable loopback address.
    arguments = fake_arguments(["doctor", "--console-ip", "127.0.0.1"])

    # When: diagnostics are requested.
    result = run_cli(arguments)

    # Then: the CLI reports fake mode and preferred local route details.
    assert result.exit_code == 0
    assert "Mode" in result.stdout
    assert "fake" in result.stdout
    assert "Preferred local IP" in result.stdout
    assert "127." in result.stdout


def test_doctor_reports_auth_setup_when_token_file_is_missing(tmp_path: Path) -> None:
    # Given: doctor is run with a missing token file.
    token_file = tmp_path / "tokens.json"
    arguments = ["doctor"]

    # When: diagnostics are requested.
    result = run_cli_with_env(arguments, {"XBOXCTL_TOKENS_FILE": str(token_file)})

    # Then: doctor gives the auth path without sending a console command.
    assert result.exit_code == 0
    assert str(token_file) in result.stdout
    assert "missing_file" in result.stdout
    assert "uv run xboxctl auth login" in result.stdout


def test_media_power_press_and_text_confirmed_actions() -> None:
    # Given: confirmed mutating commands for the remaining v1 actions.
    commands = [
        (
            fake_arguments(["press", "a", "--repeat", "2", "--confirm"]),
            "Pressed a 2 times",
        ),
        (
            fake_arguments(["text", "hello there", "--confirm"]),
            "Sent text to Living Room Series X",
        ),
        (
            fake_arguments(["media", "pause", "--confirm"]),
            "Sent pause to Living Room Series X",
        ),
        (
            fake_arguments(["power", "reboot", "--confirm"]),
            "Sent reboot to Living Room Series X",
        ),
    ]

    # When: each command is invoked.
    results = [(arguments, run_cli(arguments)) for arguments, _ in commands]

    # Then: each action reports a deterministic acknowledgement.
    for arguments, result in results:
        expected = next(text for command, text in commands if command == arguments)
        assert result.exit_code == 0
        assert expected in result.stdout


def test_mcp_describe_lists_supported_commands() -> None:
    # Given: the MCP-ready description command.
    arguments = ["mcp", "describe"]

    # When: the manifest is requested.
    result = run_cli(arguments)

    # Then: supported v1 commands are listed.
    assert result.exit_code == 0
    assert '"provider"' not in result.stdout
    assert '"command": "status"' in result.stdout
    assert '"command": "launch"' in result.stdout
    assert '"command": "auth"' in result.stdout
    assert '"requires_confirm": true' in result.stdout


def test_mcp_describe_reports_fake_provider_when_selected() -> None:
    # Given: the fake provider is selected for machine-readable command discovery.
    arguments = ["--provider", "fake", "mcp", "describe"]

    # When: the manifest is requested.
    result = run_cli(arguments)

    # Then: the manifest reflects the selected provider.
    assert result.exit_code == 0
    assert '"provider": "fake"' in result.stdout


def test_observe_screenshot_dry_run_prints_helper_command(tmp_path: Path) -> None:
    # Given: an observe screenshot dry-run request.
    output = tmp_path / "frame.png"
    arguments = [
        "observe",
        "screenshot",
        "--output",
        str(output),
        "--server-id",
        "server-1",
        "--timeout",
        "5",
        "--dry-run",
    ]

    # When: the command is invoked.
    result = run_cli_with_env(arguments, {"XBOXCTL_NODE": "/bin/node"})

    # Then: the helper command is printed without starting Remote Play.
    assert result.exit_code == 0
    assert "/bin/node" in result.stdout
    assert "observe_xhome.mjs" in result.stdout
    assert str(output) in result.stdout
    assert "--server-id server-1" in result.stdout


def test_observe_flow_dry_run_prints_helper_command(tmp_path: Path) -> None:
    # Given: an observe flow dry-run request with compact capture options.
    output_dir = tmp_path / "frames"
    arguments = [
        "observe",
        "flow",
        "--output-dir",
        str(output_dir),
        "--step",
        "capture:before",
        "--step",
        "press:right:2",
        "--step",
        "capture:after",
        "--format",
        "jpeg",
        "--width",
        "960",
        "--quality",
        "72",
        "--settle-ms",
        "0",
        "--dry-run",
    ]

    # When: the command is invoked.
    result = run_cli_with_env(arguments, {"XBOXCTL_NODE": "/bin/node"})

    # Then: the helper command is printed without starting Remote Play.
    assert result.exit_code == 0
    assert "/bin/node" in result.stdout
    assert "observe_xhome.mjs" in result.stdout
    assert str(output_dir) in result.stdout
    assert "--step capture:before" in result.stdout
    assert "--step press:right:2" in result.stdout
    assert "--format jpeg" in result.stdout
    assert "--settle-ms 0" in result.stdout


def test_observe_start_dry_run_prints_helper_command(tmp_path: Path) -> None:
    # Given: an observe start dry-run request.
    session_file = tmp_path / "session.json"
    arguments = [
        "observe",
        "start",
        "--session-file",
        str(session_file),
        "--format",
        "jpeg",
        "--width",
        "960",
        "--quality",
        "72",
        "--dry-run",
    ]

    # When: the command is invoked.
    result = run_cli_with_env(arguments, {"XBOXCTL_NODE": "/bin/node"})

    # Then: the persistent helper command is printed.
    assert result.exit_code == 0
    assert "--serve" in result.stdout
    assert "--session-file" in result.stdout
    assert str(session_file) in result.stdout


def test_unsupported_download_update_commands_are_not_advertised() -> None:
    # Given: v1 deliberately excludes download and update features.
    checked_commands = [["--help"], ["mcp", "describe"]]

    # When: command surfaces are inspected.
    outputs = [run_cli(arguments).stdout.lower() for arguments in checked_commands]

    # Then: unsupported commands are not advertised.
    for output in outputs:
        assert "download" not in output
        assert "update" not in output
        assert "remote install" not in output
        assert "forced" not in output
