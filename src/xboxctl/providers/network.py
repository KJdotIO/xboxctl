import re
import subprocess
from dataclasses import dataclass
from typing import Final

from xboxctl.typing_compat import override

SMARTGLASS_PORT: Final = 5050
ROUTE_INTERFACE_PATTERN: Final = re.compile(r"^\s*interface:\s*(?P<name>\S+)\s*$")
IFCONFIG_INET_PATTERN: Final = re.compile(
    r"^\s*inet\s+(?P<address>\d+\.\d+\.\d+\.\d+)\s+",
)


@dataclass(frozen=True, slots=True)
class LocalRouteError(Exception):
    remote_ip: str

    @override
    def __str__(self) -> str:
        return (
            "Could not choose a local network address for "
            f"{self.remote_ip}. Check that the console is reachable on this network."
        )


def preferred_local_ip_for_remote(remote_ip: str) -> str:
    route_output = run_network_command(("route", "-n", "get", remote_ip), remote_ip)
    interface_name = parse_route_interface(route_output, remote_ip)
    ifconfig_output = run_network_command(("ifconfig", interface_name), remote_ip)
    return parse_ifconfig_inet(ifconfig_output, interface_name, remote_ip)


def run_network_command(command: tuple[str, ...], remote_ip: str) -> str:
    try:
        result = subprocess.run(  # noqa: S603
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        raise LocalRouteError(remote_ip=remote_ip) from error
    return result.stdout


def parse_route_interface(route_output: str, remote_ip: str) -> str:
    for line in route_output.splitlines():
        match = ROUTE_INTERFACE_PATTERN.match(line)
        if match is not None:
            return match.group("name")
    raise LocalRouteError(remote_ip=remote_ip)


def parse_ifconfig_inet(
    ifconfig_output: str,
    interface_name: str,
    remote_ip: str,
) -> str:
    for line in ifconfig_output.splitlines():
        match = IFCONFIG_INET_PATTERN.match(line)
        if match is not None:
            return match.group("address")
    raise LocalRouteError(remote_ip=f"{remote_ip} via {interface_name}")
