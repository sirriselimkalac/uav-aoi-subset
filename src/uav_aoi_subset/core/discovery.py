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
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from uav_aoi_subset.core.progress import ProgressCallback, no_progress

# Band file name, matched case-insensitively. Must define the groups "base" and "band".
DEFAULT_PATTERN = r"^(?P<base>IMG_\d+)_(?P<band>\d+)\.tiff?$"

# File written into every output folder created by this tool; such folders are never indexed.
OUTPUT_MARKER = ".uav-aoi-subset-output"

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


def discover_captures(
    root: Path,
    *,
    pattern: str = DEFAULT_PATTERN,
    exclude: Iterable[str] = (),
    progress: ProgressCallback = no_progress,
) -> list[Capture]:
    """Walk ``root`` at any depth and group matching band files into captures.

    Skipped folders: hidden ones (name starts with ``.``), folders containing
    :data:`OUTPUT_MARKER`, and folders whose name or root-relative path (``/`` separated)
    matches one of the ``exclude`` glob patterns (case-insensitive).

    Captures are returned sorted by relative folder, then image base.
    """
    root = Path(root)
    regex = re.compile(pattern, re.IGNORECASE)
    exclude = tuple(g.casefold() for g in exclude)
    captures: dict[tuple[tuple[str, ...], str], Capture] = {}
    files_seen = 0

    for dirpath, dirnames, filenames in os.walk(root):
        if OUTPUT_MARKER in filenames:
            dirnames[:] = []
            continue
        rel_parts = Path(dirpath).relative_to(root).parts
        dirnames[:] = sorted(
            d
            for d in dirnames
            if not d.startswith(".")
            and not _is_excluded(d, PurePosixPath(*rel_parts, d).as_posix(), exclude)
        )
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
