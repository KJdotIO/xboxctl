from pathlib import Path
from subprocess import CompletedProcess
from typing import TypedDict, Unpack

import pytest

from xboxctl.providers.real_commands import (
    PressCommand,
    RealCommandError,
    ensure_helper_venv,
    resolve_helper_python,
    run_press_worker,
)


class RunKwargs(TypedDict):
    check: bool
    capture_output: bool
    text: bool
    timeout: int
    env: dict[str, str]


def test_resolve_helper_python_uses_explicit_executable(tmp_path: Path) -> None:
    # Given: a configured SmartGlass helper Python executable.
    helper_python = tmp_path / "python"
    _ = helper_python.write_text("#!/usr/bin/env python\n", encoding="utf-8")

    # When: the helper Python is resolved.
    resolved = resolve_helper_python({"XBOXCTL_SMARTGLASS_PYTHON": str(helper_python)})

    # Then: the configured executable is used without creating a helper venv.
    assert resolved == helper_python


def test_resolve_helper_python_rejects_missing_executable(tmp_path: Path) -> None:
    # Given: a configured SmartGlass helper Python path that does not exist.
    missing_python = tmp_path / "missing-python"

    # When: the helper Python is resolved.
    try:
        _ = resolve_helper_python(
            {"XBOXCTL_SMARTGLASS_PYTHON": str(missing_python)},
        )
    except RealCommandError as error:
        message = str(error)
    else:
        message = "helper unexpectedly resolved"

    # Then: the caller gets a clear setup error.
    assert "XBOXCTL_SMARTGLASS_PYTHON" in message
    assert "Python executable" in message


def test_run_press_worker_invokes_worker_module(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a SmartGlass helper executable and fake subprocess runner.
    calls: list[tuple[str, ...]] = []

    def fake_run(
        command: tuple[str, ...],
        **kwargs: Unpack[RunKwargs],
    ) -> CompletedProcess[str]:
        _ = kwargs
        calls.append(command)
        return CompletedProcess(args=command, returncode=0)

    monkeypatch.setattr("xboxctl.providers.real_commands.subprocess.run", fake_run)
    helper_python = tmp_path / "python"
    project_root = tmp_path / "project"

    # When: the press worker is launched.
    run_press_worker(
        helper_python=helper_python,
        command=PressCommand(button="DPadRight", repeat=2),
        project_root=project_root,
        tokens_file=tmp_path / "tokens.json",
    )

    # Then: the worker module receives the normalised button and repeat count.
    assert calls == [
        (
            str(helper_python),
            "-m",
            "xboxctl.providers.smartglass_worker",
            "press",
            "--button",
            "DPadRight",
            "--repeat",
            "2",
        ),
    ]


def test_ensure_helper_venv_rebuilds_existing_broken_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a helper venv path with python present but smoke-check failing.
    helper_root = tmp_path / "helper"
    helper_python = helper_root / "bin" / "python"
    helper_python.parent.mkdir(parents=True)
    _ = helper_python.write_text("#!/usr/bin/env python\n", encoding="utf-8")
    setup_commands: list[tuple[str, ...]] = []
    smoke_attempts = 0

    def fake_helper_ready(candidate: Path) -> bool:
        nonlocal smoke_attempts
        assert candidate == helper_python
        smoke_attempts += 1
        return smoke_attempts > 1

    def fake_setup(command: tuple[str, ...]) -> None:
        setup_commands.append(command)

    monkeypatch.setattr(
        "xboxctl.providers.real_commands.helper_is_ready",
        fake_helper_ready,
    )
    monkeypatch.setattr("xboxctl.providers.real_commands.run_setup_command", fake_setup)

    # When: the helper venv is resolved.
    resolved = ensure_helper_venv({"XBOXCTL_SMARTGLASS_VENV": str(helper_root)})

    # Then: setup is rerun before the existing helper is accepted.
    assert resolved == helper_python
    assert smoke_attempts == 2
    assert len(setup_commands) == 3
