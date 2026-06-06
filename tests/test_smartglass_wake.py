from pathlib import Path
from subprocess import CompletedProcess
from typing import TypedDict, Unpack

import pytest

from xboxctl.models import ConsoleId, PowerAction
from xboxctl.providers.real_commands import PowerCommand
from xboxctl.providers.real_runners import run_wake_worker


class RunKwargs(TypedDict):
    check: bool
    capture_output: bool
    text: bool
    timeout: int
    env: dict[str, str]


def test_run_wake_worker_invokes_worker_module(
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

    monkeypatch.setattr("xboxctl.providers.real_runners.subprocess.run", fake_run)
    helper_python = tmp_path / "python"
    project_root = tmp_path / "project"

    # When: the wake worker is launched with a directed address.
    run_wake_worker(
        helper_python=helper_python,
        command=PowerCommand(console_id=ConsoleId("live-id"), action=PowerAction.ON),
        project_root=project_root,
        address="192.168.0.116",
        tries=8,
    )

    # Then: the worker module receives the Live ID, address and retry count.
    assert calls == [
        (
            str(helper_python),
            "-m",
            "xboxctl.providers.smartglass_worker",
            "wake",
            "--liveid",
            "live-id",
            "--tries",
            "8",
            "--address",
            "192.168.0.116",
        ),
    ]
