from pathlib import Path

from xboxctl.observe import (
    ObserveCaptureFormat,
    ObserveFlowRequest,
    ObserveScreenshotRequest,
    observe_command,
    observe_flow_command,
)
from xboxctl.observe_session import (
    ObserveStartSessionRequest,
    observe_start_command,
)


def test_observe_command_uses_node_helper_and_token_file(tmp_path: Path) -> None:
    # Given: an observe screenshot request with an explicit token file.
    output = tmp_path / "frame.png"
    tokens = tmp_path / "tokens.json"
    request = ObserveScreenshotRequest(
        output=output,
        tokens_file=tokens,
        server_id="server-1",
        timeout_seconds=7,
    )

    # When: the helper command is built.
    command = observe_command(request, {"XBOXCTL_NODE": "/bin/node"})

    # Then: the Node helper receives all capture inputs.
    assert command[0] == "/bin/node"
    assert command[2:] == (
        "--tokens",
        str(tokens),
        "--output",
        str(output),
        "--timeout",
        "7",
        "--server-id",
        "server-1",
    )


def test_observe_command_uses_default_token_file_from_environment(
    tmp_path: Path,
) -> None:
    # Given: an observe request without an explicit token file.
    output = tmp_path / "frame.png"
    tokens = tmp_path / "tokens.json"
    request = ObserveScreenshotRequest(output=output)

    # When: the helper command is built with token-file environment.
    command = observe_command(
        request,
        {"XBOXCTL_NODE": "/bin/node", "XBOXCTL_TOKENS_FILE": str(tokens)},
    )

    # Then: the configured token file is passed to the helper.
    assert "--tokens" in command
    assert str(tokens) in command


def test_observe_command_accepts_smaller_jpeg_capture(tmp_path: Path) -> None:
    # Given: an observe request tuned for a compact agent-readable frame.
    output = tmp_path / "frame.jpg"
    tokens = tmp_path / "tokens.json"
    request = ObserveScreenshotRequest(
        output=output,
        tokens_file=tokens,
        capture_format=ObserveCaptureFormat.JPEG,
        width=960,
        quality=72,
        settle_ms=0,
    )

    # When: the helper command is built.
    command = observe_command(request, {"XBOXCTL_NODE": "/bin/node"})

    # Then: capture format and size controls are passed to the helper.
    assert "--format" in command
    assert "jpeg" in command
    assert "--width" in command
    assert "960" in command
    assert "--quality" in command
    assert "72" in command
    assert "--settle-ms" in command
    assert "0" in command


def test_observe_flow_command_passes_steps_and_output_dir(tmp_path: Path) -> None:
    # Given: an observe flow request with two captures and one repeated button press.
    output_dir = tmp_path / "frames"
    tokens = tmp_path / "tokens.json"
    request = ObserveFlowRequest(
        output_dir=output_dir,
        tokens_file=tokens,
        steps=("capture:before", "press:right:3", "capture:after"),
        capture_format=ObserveCaptureFormat.JPEG,
        width=960,
        quality=72,
        settle_ms=0,
    )

    # When: the helper command is built.
    command = observe_flow_command(request, {"XBOXCTL_NODE": "/bin/node"})

    # Then: the helper receives all flow steps and compact capture options.
    assert "--output-dir" in command
    assert str(output_dir) in command
    assert command.count("--step") == 3
    assert "press:right:3" in command
    assert "--format" in command
    assert "jpeg" in command
    assert "--settle-ms" in command
    assert "0" in command


def test_observe_start_command_writes_session_file(tmp_path: Path) -> None:
    # Given: a persistent observe session request.
    session_file = tmp_path / "session.json"
    tokens = tmp_path / "tokens.json"
    request = ObserveStartSessionRequest(
        session_file=session_file,
        tokens_file=tokens,
        capture_format=ObserveCaptureFormat.JPEG,
        width=960,
        quality=72,
        settle_ms=0,
    )

    # When: the helper command is built.
    command = observe_start_command(request, {"XBOXCTL_NODE": "/bin/node"})

    # Then: the Node helper is asked to serve and publish session details.
    assert "--serve" in command
    assert "--session-file" in command
    assert str(session_file) in command
    assert "--format" in command
    assert "jpeg" in command
    assert "--settle-ms" in command
    assert "0" in command
