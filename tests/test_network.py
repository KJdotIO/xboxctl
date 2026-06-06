from xboxctl.providers.network import (
    LocalRouteError,
    preferred_local_ip_for_remote,
)


def test_preferred_local_ip_for_remote_uses_kernel_route() -> None:
    # Given: a loopback remote address.
    remote_ip = "127.0.0.1"

    # When: the local source address is resolved through the OS route table.
    local_ip = preferred_local_ip_for_remote(remote_ip)

    # Then: the selected local address is also loopback.
    assert local_ip.startswith("127.")


def test_preferred_local_ip_for_remote_reports_route_errors() -> None:
    # Given: an invalid remote address.
    remote_ip = "not-an-ip-address"

    # When: route resolution is attempted.
    try:
        _ = preferred_local_ip_for_remote(remote_ip)
    except LocalRouteError as error:
        message = str(error)
    else:
        message = "route unexpectedly resolved"

    # Then: the caller gets an xboxctl error, not a raw socket exception.
    assert "Could not choose a local network address" in message
    assert remote_ip in message
