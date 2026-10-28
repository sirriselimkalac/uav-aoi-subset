"""Find per-band image files under a root folder and group them into captures.

MicaSense cameras write one file per band (``IMG_0000_1.tif`` ... ``IMG_0000_7.tif``) into
the same folder. A *capture* is identified by its folder relative to the root plus the image
base (``IMG_0000``). The base alone is never unique: Altum-PT restarts numbering in every
``####SET`` folder, and users add their own folder levels on top.
"""

from __future__ import annotations

import fnmatch
import os
import re
import stat
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePath, PurePosixPath

from uav_aoi_subset.core.progress import ProgressCallback, no_progress

# Band file name, matched case-insensitively. Must define the groups "base" and "band".
DEFAULT_PATTERN = r"^(?P<base>IMG_\d+)_(?P<band>\d+)\.tiff?$"

# File written into every output folder created by this tool; such folders are never indexed.
OUTPUT_MARKER = ".uav-aoi-subset-output"

# Windows system folders found at the top of a drive; never part of a flight.
SYSTEM_FOLDERS = frozenset({"$recycle.bin", "system volume information"})

_HIDDEN_SYSTEM = 0x2 | 0x4  # FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM
_JUNCTION_TAGS = frozenset({0xA0000003, 0xA000000C})  # IO_REPARSE_TAG_MOUNT_POINT, _SYMLINK

_UNSAFE_CHARS = re.compile(r'[\s<>:"/\\|?*\x00-\x1f]')
_REPEATED_UNDERSCORES = re.compile(r"_{2,}")


def sanitize_token(text: str) -> str:
    """Make one path part safe for record and folder names.

    Whitespace and characters that are unsafe in file names become ``_``, repeated
    underscores collapse to one, and leading/trailing underscores are removed. Non-ASCII
    letters (for example Turkish characters) are kept.
    """
    token = _UNSAFE_CHARS.sub("_", text)
    token = _REPEATED_UNDERSCORES.sub("_", token)
    return token.strip("_")


def flat_folder_name(rel_parts: Iterable[str]) -> str:
    """Join relative folder parts into one flat name: ``A/B C/D`` -> ``A_B_C_D``."""
    return "_".join(t for t in (sanitize_token(p) for p in rel_parts) if t)


def record_name(rel_parts: Iterable[str], base: str) -> str:
    """Unique capture name: flat folder name + ``_`` + image base."""
    folder = flat_folder_name(rel_parts)
    image = sanitize_token(base)
    return f"{folder}_{image}" if folder else image


def project_name(root: PurePath) -> str:
    """Name used in default output names: the ROOT folder name, or the drive for a drive root.

    ``D:\\`` gives ``D``, ``\\\\server\\share`` gives ``server_share`` and ``/`` gives ``drive``.
    """
    name = root.name or root.drive.rstrip(":") or "drive"
    return sanitize_token(name) or "project"


@dataclass
class Capture:
    """All band files of one capture found in a single folder."""

    rel_parts: tuple[str, ...]
    base: str
    band_files: dict[int, Path] = field(default_factory=dict)

    @property
    def record_name(self) -> str:
        return record_name(self.rel_parts, self.base)

    @property
    def relative_folder(self) -> str:
        """Folder relative to the root, with ``/`` separators on every platform."""
        return PurePosixPath(*self.rel_parts).as_posix() if self.rel_parts else ""

    @property
    def bands_found(self) -> tuple[int, ...]:
        return tuple(sorted(self.band_files))

    def missing_bands(self, n_bands: int) -> tuple[int, ...]:
        return tuple(b for b in range(1, n_bands + 1) if b not in self.band_files)

    def is_complete(self, n_bands: int) -> bool:
        return not self.missing_bands(n_bands)


def _is_excluded(name: str, rel_path: str, exclude: Iterable[str]) -> bool:
    # Case-insensitive on every platform, like folder names on Windows.
    name, rel_path = name.casefold(), rel_path.casefold()
    return any(fnmatch.fnmatchcase(name, g) or fnmatch.fnmatchcase(rel_path, g) for g in exclude)


def _is_link(st: os.stat_result) -> bool:
    """Symbolic link, or on Windows a junction / directory symlink (reparse tag)."""
    return stat.S_ISLNK(st.st_mode) or getattr(st, "st_reparse_tag", 0) in _JUNCTION_TAGS


def _is_system(name: str, st: os.stat_result) -> bool:
    """Windows system folder: by name, or both the hidden and system attributes set."""
    attributes = getattr(st, "st_file_attributes", 0)
    return name.casefold() in SYSTEM_FOLDERS or attributes & _HIDDEN_SYSTEM == _HIDDEN_SYSTEM


def discover_captures(
    root: Path,
    *,
    pattern: str = DEFAULT_PATTERN,
    exclude: Iterable[str] = (),
    progress: ProgressCallback = no_progress,
    warnings: list[str] | None = None,
) -> list[Capture]:
    """Walk ``root`` at any depth and group matching band files into captures.

    Skipped folders: hidden ones (name starts with ``.``), Windows system folders
    (:data:`SYSTEM_FOLDERS`, or hidden + system attributes), folders containing
    :data:`OUTPUT_MARKER`, and folders whose name or root-relative path (``/`` separated)
    matches one of the ``exclude`` glob patterns (case-insensitive).

    Linked folders (symbolic links, Windows junctions) are never followed, so link loops
    cannot make the walk endless. Folders that cannot be read and links that were not followed
    are reported in ``warnings`` (appended to, when given); the walk goes on without them.

    Captures are returned sorted by relative folder, then image base.
    """
    root = Path(root)
    regex = re.compile(pattern, re.IGNORECASE)
    exclude = tuple(g.casefold() for g in exclude)
    captures: dict[tuple[tuple[str, ...], str], Capture] = {}
    notes = warnings if warnings is not None else []
    visited: set[tuple[int, int]] = set()
    files_seen = 0

    def relative(path: str | os.PathLike[str]) -> str:
        try:
            return Path(path).relative_to(root).as_posix()
        except ValueError:
            return os.fspath(path)

    def on_error(exc: OSError) -> None:
        reason = exc.strerror or type(exc).__name__
        notes.append(f"cannot read folder {relative(exc.filename or root)}: {reason}")

    def keep(dirpath: str, rel_parts: tuple[str, ...], name: str) -> bool:
        if name.startswith("."):
            return False
        if _is_excluded(name, PurePosixPath(*rel_parts, name).as_posix(), exclude):
            return False
        try:
            st = Path(dirpath, name).lstat()
        except OSError as exc:
            on_error(exc)
            return False
        if _is_system(name, st):
            return False
        if _is_link(st):
            notes.append(f"linked folder not followed: {PurePosixPath(*rel_parts, name)}")
            return False
        return True

    for dirpath, dirnames, filenames in os.walk(root, onerror=on_error):
        try:
            st = Path(dirpath).stat()
        except OSError as exc:
            on_error(exc)
            dirnames[:] = []
            continue
        if st.st_ino and (st.st_dev, st.st_ino) in visited:
            dirnames[:] = []  # reached again, e.g. through a mount point
            continue
        visited.add((st.st_dev, st.st_ino))
        if OUTPUT_MARKER in filenames:
            dirnames[:] = []
            continue
        rel_parts = Path(dirpath).relative_to(root).parts
        dirnames[:] = sorted(d for d in dirnames if keep(dirpath, rel_parts, d))
        for filename in filenames:
            match = regex.match(filename)
            if match is None:
                continue
            base, band = match.group("base"), int(match.group("band"))
            key = (rel_parts, base.upper())
            capture = captures.setdefault(key, Capture(rel_parts=rel_parts, base=base))
            capture.band_files.setdefault(band, Path(dirpath) / filename)
        files_seen += len(filenames)
        progress("scan", files_seen, None)

    return [captures[k] for k in sorted(captures)]
