"""Read GPS positions from image files.

:class:`ExifToolReader` runs the external ``exiftool`` program in batches (one process per
chunk of files, file names passed through a UTF-8 argfile) instead of once per file. Other
backends (for example PyExifTool) can be added by implementing :class:`ExifReader`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from uav_aoi_subset.core.progress import ProgressCallback, no_progress

_INSTALL_STEPS = {
    "win32": (
        "  - run the Windows installer from https://exiftool.org/\n"
        "    (or: choco install exiftool), or\n"
        "  - unzip the Windows package from https://exiftool.org/, rename 'exiftool(-k).exe' to\n"
        "    'exiftool.exe' and put its folder on PATH.\n"
        "  Then open a new terminal window and check with: exiftool -ver"
    ),
    "darwin": (
        "  - with Homebrew: brew install exiftool, or\n"
        "  - the macOS package from https://exiftool.org/.\n"
        "  Then check with: exiftool -ver"
    ),
    "linux": (
        "  - Debian/Ubuntu: sudo apt install libimage-exiftool-perl\n"
        "  - Fedora/RHEL:   sudo dnf install perl-Image-ExifTool\n"
        "  - or your distribution's ExifTool package. Then check with: exiftool -ver"
    ),
}


def install_hint(platform: str | None = None) -> str:
    """How to install ExifTool on this operating system (or ``platform``)."""
    platform = sys.platform if platform is None else platform
    key = "linux" if platform.startswith("linux") else platform
    steps = _INSTALL_STEPS.get(key, "  - see https://exiftool.org/install.html")
    return (
        "Install ExifTool and make sure it is on your PATH, or give its location with "
        f"--exiftool PATH:\n{steps}"
    )


DEFAULT_CHUNK_SIZE = 500


class ExifToolNotFoundError(RuntimeError):
    """The exiftool executable could not be found."""


class ExifToolError(RuntimeError):
    """exiftool ran but its output could not be used."""


@dataclass(frozen=True)
class GpsFix:
    """Position of one image. Missing values are ``None``."""

    latitude: float | None
    longitude: float | None
    altitude: float | None = None
    capture_time: str | None = None  # EXIF DateTimeOriginal, "YYYY:MM:DD HH:MM:SS"

    @property
    def has_position(self) -> bool:
        return self.latitude is not None and self.longitude is not None


class ExifReader(Protocol):
    def read_gps(
        self, paths: Sequence[Path], progress: ProgressCallback = no_progress
    ) -> dict[Path, GpsFix]:
        """Return a fix for every readable path. Unreadable paths are left out."""
        ...


def find_exiftool(explicit: str | os.PathLike[str] | None = None) -> Path:
    """Locate exiftool: the explicit path if given, otherwise ``exiftool`` on PATH."""
    if explicit is not None:
        path = Path(explicit)
        if path.is_file():
            return path
        raise ExifToolNotFoundError(f"ExifTool not found at: {path}\n{install_hint()}")
    found = shutil.which("exiftool")  # also finds exiftool.exe on Windows via PATHEXT
    if found is None:
        raise ExifToolNotFoundError(f"ExifTool was not found on PATH.\n{install_hint()}")
    return Path(found)


def exiftool_version(executable: str | os.PathLike[str]) -> str:
    """The version ExifTool reports for itself (``exiftool -ver``)."""
    try:
        proc = subprocess.run(
            [str(executable), "-ver"], capture_output=True, check=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ExifToolError(f"{executable} did not run: {exc}") from exc
    return proc.stdout.decode("utf-8", errors="replace").strip()


def _path_key(path: str | os.PathLike[str]) -> str:
    """Normalise a path for matching exiftool's SourceFile back to our input."""
    # absolute() rather than resolve(): no symlink or network-drive (UNC) rewriting.
    return os.path.normcase(os.path.normpath(Path(path).absolute()))


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _signed(value: float | None, ref: object, negative_refs: tuple[object, ...]) -> float | None:
    if value is None:
        return None
    if isinstance(ref, str):
        ref = ref.strip().upper()[:1]
    return -abs(value) if ref in negative_refs else value


def parse_exiftool_record(record: dict) -> GpsFix:
    """Convert one object of ``exiftool -json -n`` output into a :class:`GpsFix`.

    The sign is taken from the Ref tags when present, so the result is correct whether
    exiftool reports signed or unsigned coordinates.
    """
    lat = _signed(_number(record.get("GPSLatitude")), record.get("GPSLatitudeRef"), ("S",))
    lon = _signed(_number(record.get("GPSLongitude")), record.get("GPSLongitudeRef"), ("W",))
    alt = _signed(_number(record.get("GPSAltitude")), record.get("GPSAltitudeRef"), (1, "1"))
    if lat is not None and not -90 <= lat <= 90:
        lat = None
    if lon is not None and not -180 <= lon <= 180:
        lon = None
    time = record.get("DateTimeOriginal")
    return GpsFix(lat, lon, alt, str(time) if time else None)


class ExifToolReader:
    """:class:`ExifReader` backed by the exiftool command-line program."""

    TAGS = (
        "-GPSLatitude",
        "-GPSLatitudeRef",
        "-GPSLongitude",
        "-GPSLongitudeRef",
        "-GPSAltitude",
        "-GPSAltitudeRef",
        "-DateTimeOriginal",
    )

    def __init__(
        self,
        executable: str | os.PathLike[str] | None = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> None:
        if chunk_size < 1:
            raise ValueError("chunk_size must be at least 1")
        self.executable = find_exiftool(executable)
        self.chunk_size = chunk_size
        self.warnings: list[str] = []

    def read_gps(
        self, paths: Sequence[Path], progress: ProgressCallback = no_progress
    ) -> dict[Path, GpsFix]:
        result: dict[Path, GpsFix] = {}
        total = len(paths)
        progress("exif", 0, total)
        for start in range(0, total, self.chunk_size):
            chunk = paths[start : start + self.chunk_size]
            by_key = {_path_key(p): p for p in chunk}
            for record in self._run(chunk):
                path = by_key.get(_path_key(record.get("SourceFile", "")))
                if path is not None:
                    result[path] = parse_exiftool_record(record)
            progress("exif", min(start + len(chunk), total), total)
        return result

    def _run(self, chunk: Sequence[Path]) -> list[dict]:
        # Absolute paths never start with "-", so exiftool cannot mistake one for an option.
        lines = "\n".join(str(Path(p).absolute()) for p in chunk) + "\n"
        fd, name = tempfile.mkstemp(prefix="uav-aoi-subset-", suffix=".args")
        argfile = Path(name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(lines)
            cmd = [
                str(self.executable),
                "-json",
                "-n",
                "-q",  # no "N image files read" summary; errors are still reported
                "-charset",
                "filename=utf8",
                *self.TAGS,
                "-@",
                # Only the ASCII file name goes on the command line: Windows converts
                # arguments to the ANSI code page, which would break a temp folder path
                # containing e.g. a Turkish user name.
                argfile.name,
            ]
            proc = subprocess.run(cmd, capture_output=True, check=False, cwd=argfile.parent)
        finally:
            argfile.unlink(missing_ok=True)

        # exiftool exits with 1 when some files could not be read but still prints the rest.
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        if stderr:
            self.warnings.append(stderr)
        stdout = proc.stdout.decode("utf-8", errors="replace").strip()
        if not stdout:
            return []
        try:
            records = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ExifToolError(f"Could not parse exiftool output: {exc}") from exc
        if not isinstance(records, list):
            raise ExifToolError("Unexpected exiftool output: expected a JSON list")
        return [r for r in records if isinstance(r, dict)]
