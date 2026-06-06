try:
    from typing import override
except ImportError:
    from typing_extensions import override  # noqa: UP035

__all__ = ["override"]
