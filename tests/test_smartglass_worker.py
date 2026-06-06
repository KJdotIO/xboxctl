import sys

import pytest

from xboxctl.providers.smartglass_worker import (
    WorkerButtonError,
    main,
    parse_worker_button,
)


def test_parse_worker_button_accepts_supported_enum_name() -> None:
    # Given: a button name produced by the main provider.
    button_name = "DPadRight"

    # When: the worker parses the button.
    parsed = parse_worker_button(button_name)

    # Then: the SmartGlass enum value name is preserved.
    assert parsed.name == button_name


def test_parse_worker_button_rejects_unknown_enum_name() -> None:
    # Given: an invalid button name reaches the worker boundary.
    button_name = "NotARealButton"

    # When: the worker parses the button.
    try:
        _ = parse_worker_button(button_name)
    except WorkerButtonError as error:
        message = str(error)
    else:
        message = "worker unexpectedly parsed the button"

    # Then: the worker reports a clear boundary error.
    assert "Unsupported SmartGlass button" in message
    assert button_name in message


def test_main_reports_worker_button_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: worker CLI arguments containing an invalid SmartGlass button.
    monkeypatch.setattr(
        sys,
        "argv",
        ["smartglass-worker", "press", "--button", "BadButton", "--repeat", "1"],
    )

    # When: the worker entrypoint runs.
    exit_code = main()

    # Then: the worker returns a clean boundary error without a traceback.
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Unsupported SmartGlass button: BadButton." in captured.err
