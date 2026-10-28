"""Progress reporting shared by all core functions."""

from collections.abc import Callable

# Called as progress(stage, done, total); total is None when it is not known in advance.
ProgressCallback = Callable[[str, int, int | None], None]


def no_progress(stage: str, done: int, total: int | None) -> None:
    """Default callback: ignore progress."""
