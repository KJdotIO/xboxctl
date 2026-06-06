# pyright: reportAny=false
import os
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Protocol

from xboxctl.auth import default_tokens_file
from xboxctl.models import ConsoleId, MediaAction, PowerAction, ProductId
from xboxctl.typing_compat import override

SMARTGLASS_PYTHON_ENV: Final = "XBOXCTL_SMARTGLASS_PYTHON"
SMARTGLASS_VENV_ENV: Final = "XBOXCTL_SMARTGLASS_VENV"
SMARTGLASS_TIMEOUT_SECONDS: Final = 30
SMARTGLASS_SMOKE_TIMEOUT_SECONDS: Final = 10
SMARTGLASS_PACKAGES: Final[tuple[str, ...]] = (
    "construct==2.10.56",
    "cryptography==48.0.0",
    "pydantic==1.7.1",
    "requests",
    "typing-extensions>=4.15.0",
)


@dataclass(frozen=True, slots=True)
class PressCommand:
    button: str
    repeat: int


@dataclass(frozen=True, slots=True)
class CloudButtonCommand:
    console_id: ConsoleId
    button: str
    repeat: int


@dataclass(frozen=True, slots=True)
class LaunchCommand:
    console_id: ConsoleId
    product_id: ProductId


@dataclass(frozen=True, slots=True)
class MediaCommand:
    console_id: ConsoleId
    action: MediaAction


@dataclass(frozen=True, slots=True)
class TextCommand:
    console_id: ConsoleId
    text: str


@dataclass(frozen=True, slots=True)
class PowerCommand:
    console_id: ConsoleId
    action: PowerAction


class PressRunner(Protocol):
    def __call__(self, command: PressCommand) -> None: ...


class CloudButtonRunner(Protocol):
    def __call__(self, command: CloudButtonCommand) -> None: ...


class LaunchRunner(Protocol):
    def __call__(self, command: LaunchCommand) -> None: ...


class MediaRunner(Protocol):
    def __call__(self, command: MediaCommand) -> None: ...


class TextRunner(Protocol):
    def __call__(self, command: TextCommand) -> None: ...


class PowerRunner(Protocol):
    def __call__(self, command: PowerCommand) -> None: ...


@dataclass(frozen=True, slots=True)
class RealCommandError(Exception):
    reason: str

    @override
    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class SmartGlassPressRunner:
    environ: Mapping[str, str] = field(default_factory=lambda: os.environ)
    project_root: Path = Path(__file__).resolve().parents[3]
    tokens_file: Path | None = None

    def __call__(self, command: PressCommand) -> None:
        helper_python = resolve_helper_python(self.environ)
        if helper_python is None:
            helper_python = ensure_helper_venv(self.environ)
        run_press_worker(
            helper_python=helper_python,
            command=command,
            project_root=self.project_root,
            tokens_file=self.tokens_file,
        )


def resolve_helper_python(environ: Mapping[str, str]) -> Path | None:
    configured = environ.get(SMARTGLASS_PYTHON_ENV)
    if configured is None:
        return None
    helper_python = Path(configured).expanduser()
    if helper_python.is_file():
        return helper_python
    raise RealCommandError(
        reason=f"{SMARTGLASS_PYTHON_ENV} does not point to a Python executable.",
    )


def ensure_helper_venv(environ: Mapping[str, str]) -> Path:
    venv_path = helper_venv_path(environ)
    helper_python = venv_path / "bin" / "python"
    if helper_python.is_file() and helper_is_ready(helper_python):
        return helper_python

    run_setup_command(("uv", "venv", "--python", "3.11", str(venv_path)))
    run_setup_command(
        (
            "uv",
            "pip",
            "install",
            "--python",
            str(helper_python),
            "xbox-smartglass-core==1.3.0",
            "--no-deps",
        ),
    )
    run_setup_command(
        (
            "uv",
            "pip",
            "install",
            "--python",
            str(helper_python),
            *SMARTGLASS_PACKAGES,
        ),
    )
    if not helper_is_ready(helper_python):
        raise RealCommandError(reason="SmartGlass helper environment is not usable.")
    return helper_python


def helper_is_ready(helper_python: Path) -> bool:
    smoke_command = (
        str(helper_python),
        "-c",
        (
            "from xbox.sg.console import Console; "
            "from xbox.sg.enum import GamePadButton; "
            "from typing_extensions import override; "
            "print(Console.__name__, GamePadButton.DPadRight.name)"
        ),
    )
    try:
        _ = subprocess.run(  # noqa: S603
            smoke_command,
            check=True,
            capture_output=True,
            text=True,
            timeout=SMARTGLASS_SMOKE_TIMEOUT_SECONDS,
        )
    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ):
        return False
    return True


def helper_venv_path(environ: Mapping[str, str]) -> Path:
    configured = environ.get(SMARTGLASS_VENV_ENV)
    if configured is not None:
        return Path(configured).expanduser()
    return default_tokens_file().parent / "smartglass-py311"


def run_setup_command(command: tuple[str, ...]) -> None:
    try:
        _ = subprocess.run(  # noqa: S603
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        raise RealCommandError(reason=setup_error_message(error)) from error


def setup_error_message(
    error: FileNotFoundError | subprocess.CalledProcessError,
) -> str:
    if isinstance(error, FileNotFoundError):
        return "Could not find uv to create the SmartGlass helper environment."
    detail = error.stderr.strip() or error.stdout.strip()
    return f"Could not prepare the SmartGlass helper environment. {detail}"


def run_press_worker(
    helper_python: Path,
    command: PressCommand,
    project_root: Path,
    tokens_file: Path | None,
) -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(project_root / "src")
    if tokens_file is not None:
        environment["XBOXCTL_TOKENS_FILE"] = str(tokens_file)
    worker_command = (
        str(helper_python),
        "-m",
        "xboxctl.providers.smartglass_worker",
        "press",
        "--button",
        command.button,
        "--repeat",
        str(command.repeat),
    )
    try:
        _ = subprocess.run(  # noqa: S603
            worker_command,
            check=True,
            capture_output=True,
            text=True,
            timeout=SMARTGLASS_TIMEOUT_SECONDS,
            env=environment,
        )
    except subprocess.TimeoutExpired as error:
        raise RealCommandError(
            reason="Timed out while sending the Xbox button press.",
        ) from error
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or error.stdout.strip()
        raise RealCommandError(reason=detail or "Xbox button press failed.") from error
    except FileNotFoundError as error:
        raise RealCommandError(
            reason="Could not run the SmartGlass helper Python executable.",
        ) from error


def current_python_path() -> Path:
    return Path(sys.executable)
