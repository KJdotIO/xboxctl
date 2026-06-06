from dataclasses import dataclass

from xboxctl.models import Console, InstalledApp
from xboxctl.typing_compat import override


@dataclass(frozen=True, slots=True)
class AppNotFoundError(Exception):
    target: str

    @override
    def __str__(self) -> str:
        return f"No installed app matches {self.target!r}."


@dataclass(frozen=True, slots=True)
class AmbiguousAppError(Exception):
    target: str
    matches: tuple[str, ...]

    @override
    def __str__(self) -> str:
        return (
            f"More than one installed app matches {self.target!r}: "
            f"{', '.join(self.matches)}. Use a fuller app name or product ID."
        )


def find_installed_app(console: Console, target: str) -> InstalledApp:
    normalised_target = target.casefold().strip()
    for app in console.apps:
        if normalised_target in {app.name.casefold(), app.product_id.casefold()}:
            return app

    matches = tuple(
        app for app in console.apps if normalised_target in app.name.casefold()
    )
    match matches:
        case (app,):
            return app
        case ():
            raise AppNotFoundError(target=target)
        case many:
            raise AmbiguousAppError(
                target=target,
                matches=tuple(app.name for app in many),
            )
