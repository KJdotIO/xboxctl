from pathlib import Path

from xboxctl.models import (
    Console,
    ConsoleId,
    InstalledApp,
    MediaAction,
    PowerAction,
    PowerState,
    ProductId,
)
from xboxctl.providers.app_resolution import (
    AmbiguousAppError,
    AppNotFoundError,
    find_installed_app,
)
from xboxctl.providers.fake import build_fake_provider
from xboxctl.providers.real import ProviderUnavailableError, PythonXboxProvider
from xboxctl.providers.real_commands import (
    CloudButtonCommand,
    LaunchCommand,
    MediaCommand,
    PowerCommand,
    PressCommand,
    RealCommandError,
    TextCommand,
)
from xboxctl.providers.select import ProviderName, build_provider


def discovered_console() -> Console:
    return Console(
        id=ConsoleId("real-console-id"),
        name="Actual Series X",
        power_state=PowerState.ON,
        active_title="Dashboard",
        storage=(),
        apps=(
            InstalledApp(
                name="YouTube",
                product_id=ProductId("9NDP7KTLK7W3"),
                running=False,
            ),
        ),
    )


def test_fake_provider_lists_sample_console_when_offline() -> None:
    # Given: the deterministic offline provider used for v1 proof.
    provider = build_fake_provider()

    # When: consoles are listed without credentials or network access.
    consoles = provider.list_consoles()

    # Then: a stable sample console is available.
    assert len(consoles) == 1
    assert consoles[0].name == "Living Room Series X"
    assert consoles[0].power_state.value == "on"


def test_python_xbox_provider_lists_discovered_consoles() -> None:
    # Given: the real provider has a read-only discovery function.
    def list_discovery(tokens_file: Path | None = None) -> tuple[Console, ...]:
        _ = tokens_file
        return (discovered_console(),)

    provider = PythonXboxProvider(list_discovery=list_discovery)

    # When: consoles are listed.
    consoles = provider.list_consoles()

    # Then: the discovered console is returned through the provider boundary.
    assert len(consoles) == 1
    assert consoles[0].name == "Actual Series X"


def test_python_xbox_provider_status_uses_read_only_discovery() -> None:
    # Given: the real provider has a read-only status function.
    def status_discovery(tokens_file: Path | None = None) -> Console:
        _ = tokens_file
        return discovered_console()

    provider = PythonXboxProvider(status_discovery=status_discovery)

    # When: status is requested.
    console = provider.status()

    # Then: the read-only status result is returned.
    assert console.active_title == "Dashboard"


def test_python_xbox_provider_launch_uses_cloud_command_runner() -> None:
    # Given: a real provider with discovered apps and a launch runner test double.
    commands: list[LaunchCommand] = []

    def status_discovery(tokens_file: Path | None = None) -> Console:
        _ = tokens_file
        return discovered_console()

    def launch_runner(command: LaunchCommand) -> None:
        commands.append(command)

    provider = PythonXboxProvider(
        status_discovery=status_discovery,
        launch_runner=launch_runner,
    )

    # When: an installed app is launched by name.
    action = provider.launch("youtube")

    # Then: the OneStore product id is sent through the real launch boundary.
    assert action.message == "Launching YouTube on Actual Series X."
    assert commands == [
        LaunchCommand(
            console_id=ConsoleId("real-console-id"),
            product_id=ProductId("9NDP7KTLK7W3"),
        ),
    ]


def test_python_xbox_provider_launch_rejects_unknown_apps() -> None:
    # Given: a real provider with discovered apps and a launch runner test double.
    commands: list[LaunchCommand] = []

    def status_discovery(tokens_file: Path | None = None) -> Console:
        _ = tokens_file
        return discovered_console()

    def launch_runner(command: LaunchCommand) -> None:
        commands.append(command)

    provider = PythonXboxProvider(
        status_discovery=status_discovery,
        launch_runner=launch_runner,
    )

    # When: an unknown app is launched.
    try:
        _ = provider.launch("definitely missing")
    except AppNotFoundError as error:
        message = str(error)
    else:
        message = "provider unexpectedly launched a title"

    # Then: the command is rejected before any launch command is sent.
    assert "No installed app matches" in message
    assert commands == []


def test_find_installed_app_prefers_exact_name_when_substrings_overlap() -> None:
    # Given: several installed apps include the same search term.
    console = Console(
        id=ConsoleId("console-id"),
        name="Actual Series X",
        power_state=PowerState.ON,
        active_title="Dashboard",
        storage=(),
        apps=(
            InstalledApp(
                name="Halo Infinite",
                product_id=ProductId("halo-infinite-id"),
                running=False,
            ),
            InstalledApp(
                name="Halo Waypoint",
                product_id=ProductId("halo-waypoint-id"),
                running=False,
            ),
        ),
    )

    # When: the full app name is used.
    app = find_installed_app(console=console, target="halo infinite")

    # Then: the exact name match wins over substring ambiguity.
    assert app.product_id == "halo-infinite-id"


def test_find_installed_app_rejects_ambiguous_substring_matches() -> None:
    # Given: several installed apps include the same partial search term.
    console = Console(
        id=ConsoleId("console-id"),
        name="Actual Series X",
        power_state=PowerState.ON,
        active_title="Dashboard",
        storage=(),
        apps=(
            InstalledApp(
                name="Halo Infinite",
                product_id=ProductId("halo-infinite-id"),
                running=False,
            ),
            InstalledApp(
                name="Halo Waypoint",
                product_id=ProductId("halo-waypoint-id"),
                running=False,
            ),
        ),
    )

    # When: a partial app name matches more than one app.
    try:
        _ = find_installed_app(console=console, target="halo")
    except AmbiguousAppError as error:
        message = str(error)
    else:
        message = "app resolution unexpectedly picked one title"

    # Then: the caller gets a clear request to be more specific.
    assert "More than one installed app matches" in message
    assert "Halo Infinite" in message
    assert "Halo Waypoint" in message


def test_python_xbox_provider_press_uses_real_command_runner() -> None:
    # Given: cloud button control fails and the local runner is available.
    commands: list[PressCommand] = []

    def status_discovery(tokens_file: Path | None = None) -> Console:
        _ = tokens_file
        return discovered_console()

    def cloud_button_runner(command: CloudButtonCommand) -> None:
        _ = command
        raise RealCommandError(reason="cloud press failed")

    def press_runner(command: PressCommand) -> None:
        commands.append(command)

    provider = PythonXboxProvider(
        status_discovery=status_discovery,
        cloud_button_runner=cloud_button_runner,
        press_runner=press_runner,
    )

    # When: a confirmed controller button is pressed.
    action = provider.press("dpad-right", repeat=2)

    # Then: the normalised command falls back to the LAN SmartGlass boundary.
    assert action.message == "Pressed dpad-right 2 times on Actual Series X."
    assert commands == [PressCommand(button="DPadRight", repeat=2)]


def test_python_xbox_provider_press_prefers_cloud_command_runner() -> None:
    # Given: a real provider with cloud and local button runner test doubles.
    cloud_commands: list[CloudButtonCommand] = []
    local_commands: list[PressCommand] = []

    def status_discovery(tokens_file: Path | None = None) -> Console:
        _ = tokens_file
        return discovered_console()

    def cloud_button_runner(command: CloudButtonCommand) -> None:
        cloud_commands.append(command)

    def press_runner(command: PressCommand) -> None:
        local_commands.append(command)

    provider = PythonXboxProvider(
        status_discovery=status_discovery,
        cloud_button_runner=cloud_button_runner,
        press_runner=press_runner,
    )

    # When: a confirmed controller button is pressed.
    action = provider.press("dpad-right", repeat=2)

    # Then: the cloud command receives the cloud enum and local fallback is unused.
    assert action.message == "Pressed dpad-right 2 times on Actual Series X."
    assert cloud_commands == [
        CloudButtonCommand(
            console_id=ConsoleId("real-console-id"),
            button="Right",
            repeat=2,
        ),
    ]
    assert local_commands == []


def test_python_xbox_provider_media_uses_cloud_command_runner() -> None:
    # Given: a real provider with a media runner test double.
    commands: list[MediaCommand] = []

    def status_discovery(tokens_file: Path | None = None) -> Console:
        _ = tokens_file
        return discovered_console()

    def media_runner(command: MediaCommand) -> None:
        commands.append(command)

    provider = PythonXboxProvider(
        status_discovery=status_discovery,
        media_runner=media_runner,
    )

    # When: a media action is requested.
    action = provider.media(MediaAction.PAUSE)

    # Then: the action is sent with the discovered console id.
    assert action.message == "Sent pause to Actual Series X."
    assert commands == [
        MediaCommand(
            console_id=ConsoleId("real-console-id"),
            action=MediaAction.PAUSE,
        ),
    ]


def test_python_xbox_provider_text_uses_cloud_command_runner() -> None:
    # Given: a real provider with a text runner test double.
    commands: list[TextCommand] = []

    def status_discovery(tokens_file: Path | None = None) -> Console:
        _ = tokens_file
        return discovered_console()

    def text_runner(command: TextCommand) -> None:
        commands.append(command)

    provider = PythonXboxProvider(
        status_discovery=status_discovery,
        text_runner=text_runner,
    )

    # When: text is sent.
    action = provider.send_text("hello")

    # Then: the text command is sent with the discovered console id.
    assert action.message == "Sent text to Actual Series X."
    assert commands == [
        TextCommand(console_id=ConsoleId("real-console-id"), text="hello"),
    ]


def test_python_xbox_provider_power_uses_cloud_command_runner() -> None:
    # Given: a real provider with a power runner test double.
    commands: list[PowerCommand] = []

    def status_discovery(tokens_file: Path | None = None) -> Console:
        _ = tokens_file
        return discovered_console()

    def power_runner(command: PowerCommand) -> None:
        commands.append(command)

    provider = PythonXboxProvider(
        status_discovery=status_discovery,
        power_runner=power_runner,
    )

    # When: a power action is requested.
    action = provider.power(PowerAction.OFF)

    # Then: the action is sent with the discovered console id.
    assert action.message == "Sent off to Actual Series X."
    assert commands == [
        PowerCommand(
            console_id=ConsoleId("real-console-id"),
            action=PowerAction.OFF,
        ),
    ]


def test_python_xbox_provider_press_rejects_unknown_buttons() -> None:
    # Given: a real provider with no runner invoked yet.
    commands: list[PressCommand] = []

    def press_runner(command: PressCommand) -> None:
        commands.append(command)

    provider = PythonXboxProvider(press_runner=press_runner)

    # When: an unsupported button is requested.
    try:
        _ = provider.press("not-a-button", repeat=1)
    except ProviderUnavailableError as error:
        message = str(error)
    else:
        message = "provider unexpectedly accepted a bad button"

    # Then: the command is refused before any console command is sent.
    assert "Unsupported Xbox button" in message
    assert "not-a-button" in message
    assert commands == []


def test_build_provider_returns_fake_provider_when_requested() -> None:
    # Given: the fake provider has been requested at the provider boundary.
    selected_provider = ProviderName.FAKE

    # When: the provider is built.
    provider = build_provider(selected_provider)

    # Then: it returns the stable fake console state.
    assert provider.status().name == "Living Room Series X"


def test_build_provider_returns_real_boundary_when_requested() -> None:
    # Given: the real provider has been requested at the provider boundary.
    selected_provider = ProviderName.REAL

    # When: the provider is built.
    provider = build_provider(selected_provider)

    # Then: it returns the real provider boundary without touching the network.
    assert isinstance(provider, PythonXboxProvider)
