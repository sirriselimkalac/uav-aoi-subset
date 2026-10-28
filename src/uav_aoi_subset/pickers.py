"""File and folder pickers for the command line, used when a required path is missing.

Only front ends import this module; ``core`` knows nothing about tkinter. A picker is only
offered when someone can actually answer it: an interactive terminal (stdin is a TTY), the
main thread, a display, and a working tkinter. Scripts can switch pickers off with
``--no-picker`` or the environment variable ``UAV_AOI_SUBSET_NO_PICKER=1``.
"""

from __future__ import annotations

import contextlib
import os
import sys
import threading
from collections.abc import Sequence
from pathlib import Path

ENV_NO_PICKER = "UAV_AOI_SUBSET_NO_PICKER"

CSV_FILES = (("CSV files", "*.csv"), ("All files", "*"))
AOI_FILES = (("KML/KMZ files", "*.kml *.kmz"), ("All files", "*"))


class PickerCancelled(Exception):
    """The user closed a picker without choosing anything."""


class PickerUnavailable(Exception):
    """Tk could not open a window (no usable display)."""


def _env_disabled() -> bool:
    value = os.environ.get(ENV_NO_PICKER, "").strip().lower()
    return value not in {"", "0", "false", "no"}


def _has_display() -> bool:
    if sys.platform.startswith("linux"):
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return True  # macOS and Windows always have one in an interactive session


def _stdin_is_terminal() -> bool:
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except (AttributeError, ValueError):  # replaced or closed stdin
        return False


def pickers_available(no_picker: bool = False) -> bool:
    """True when a picker can be shown and someone is there to answer it."""
    if no_picker or _env_disabled():
        return False
    if not _stdin_is_terminal():
        return False  # run from a script, a scheduler or with redirected input
    if threading.current_thread() is not threading.main_thread():
        return False  # Tk must run on the main thread
    if not _has_display():
        return False
    try:
        import tkinter  # noqa: F401  # some Python builds ship without it
    except ImportError:
        return False
    return True


def _windows_dpi_aware() -> None:
    """Ask Windows for sharp (not bitmap-scaled) dialogs on high-DPI screens."""
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # per-monitor aware, Windows 8.1+
    except (AttributeError, OSError):
        with contextlib.suppress(AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()


def _hidden_root():
    import tkinter as tk

    _windows_dpi_aware()
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise PickerUnavailable(str(exc)) from exc
    root.withdraw()
    # Keep the dialog in front of the terminal (macOS otherwise opens it behind).
    root.attributes("-topmost", True)
    root.lift()
    root.update()
    return root


def _initial(initialdir: Path | None) -> str | None:
    return str(initialdir) if initialdir is not None and initialdir.is_dir() else None


def ask_folder(title: str, initialdir: Path | None = None) -> Path:
    """Show a folder picker; raise :class:`PickerCancelled` if nothing is chosen."""
    from tkinter import filedialog

    root = _hidden_root()
    try:
        chosen = filedialog.askdirectory(
            parent=root, title=title, initialdir=_initial(initialdir), mustexist=True
        )
    finally:
        root.destroy()
    if not chosen:
        raise PickerCancelled
    return Path(chosen)


def ask_open_file(
    title: str, filetypes: Sequence[tuple[str, str]], initialdir: Path | None = None
) -> Path:
    """Show a file picker; raise :class:`PickerCancelled` if nothing is chosen."""
    from tkinter import filedialog

    root = _hidden_root()
    try:
        chosen = filedialog.askopenfilename(
            parent=root, title=title, filetypes=list(filetypes), initialdir=_initial(initialdir)
        )
    finally:
        root.destroy()
    if not chosen:
        raise PickerCancelled
    return Path(chosen)
