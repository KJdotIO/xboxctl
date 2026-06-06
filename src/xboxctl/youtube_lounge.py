# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportAny=false
from dataclasses import dataclass

from pyytlounge import YtLoungeApi


@dataclass(frozen=True, slots=True)
class LoungeAuth:
    screen_id: str
    lounge_token: str
    screen_name: str | None = None


@dataclass(frozen=True, slots=True)
class LoungeStatus:
    available: bool


async def pair_lounge(pairing_code: str, device_name: str) -> LoungeAuth:
    async with YtLoungeApi(device_name) as api:
        paired = await api.pair(pairing_code)
        if not paired:
            msg = "YouTube pairing failed."
            raise RuntimeError(msg)
        return LoungeAuth(
            screen_id=api.auth.screen_id,
            lounge_token=api.auth.lounge_id_token,
        )


async def refresh_lounge(auth: LoungeAuth, device_name: str) -> LoungeAuth:
    async with YtLoungeApi(device_name) as api:
        api.auth.screen_id = auth.screen_id
        api.auth.lounge_id_token = auth.lounge_token
        linked = await api.refresh_auth()
        if not linked:
            msg = "YouTube lounge token refresh failed."
            raise RuntimeError(msg)
        return LoungeAuth(
            screen_id=api.auth.screen_id,
            lounge_token=api.auth.lounge_id_token,
            screen_name=auth.screen_name,
        )


async def lounge_status(auth: LoungeAuth, device_name: str) -> LoungeStatus:
    refreshed = await refresh_lounge(auth, device_name)
    async with YtLoungeApi(device_name) as api:
        api.auth.screen_id = refreshed.screen_id
        api.auth.lounge_id_token = refreshed.lounge_token
        available = await api.is_available()
        return LoungeStatus(available=available)


async def lounge_play_video(
    auth: LoungeAuth,
    device_name: str,
    video_id: str,
) -> LoungeAuth:
    return await _with_connected_lounge(auth, device_name, "play_video", video_id)


async def lounge_pause(auth: LoungeAuth, device_name: str) -> LoungeAuth:
    return await _with_connected_lounge(auth, device_name, "pause")


async def lounge_resume(auth: LoungeAuth, device_name: str) -> LoungeAuth:
    return await _with_connected_lounge(auth, device_name, "play")


async def lounge_seek(auth: LoungeAuth, device_name: str, seconds: float) -> LoungeAuth:
    return await _with_connected_lounge(auth, device_name, "seek_to", seconds)


async def lounge_next(auth: LoungeAuth, device_name: str) -> LoungeAuth:
    return await _with_connected_lounge(auth, device_name, "next")


async def lounge_previous(auth: LoungeAuth, device_name: str) -> LoungeAuth:
    return await _with_connected_lounge(auth, device_name, "previous")


async def lounge_disconnect(auth: LoungeAuth, device_name: str) -> LoungeAuth:
    return await _with_connected_lounge(auth, device_name, "disconnect")


async def _with_connected_lounge(
    auth: LoungeAuth,
    device_name: str,
    command: str,
    argument: str | float | None = None,
) -> LoungeAuth:
    async with YtLoungeApi(device_name) as api:
        api.auth.screen_id = auth.screen_id
        api.auth.lounge_id_token = auth.lounge_token
        linked = await api.refresh_auth()
        if not linked:
            msg = "YouTube lounge token refresh failed."
            raise RuntimeError(msg)
        connected = await api.connect()
        if not connected:
            msg = "Could not connect to the paired YouTube app."
            raise RuntimeError(msg)
        if argument is None:
            ok = await getattr(api, command)()
        else:
            ok = await getattr(api, command)(argument)
        if not ok:
            msg = f"YouTube command failed: {command}."
            raise RuntimeError(msg)
        return LoungeAuth(
            screen_id=api.auth.screen_id,
            lounge_token=api.auth.lounge_id_token,
            screen_name=auth.screen_name,
        )
