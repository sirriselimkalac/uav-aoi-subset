"""Build, write and read the capture index CSV."""

from __future__ import annotations

import csv
import datetime as dt
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from uav_aoi_subset.core.discovery import DEFAULT_PATTERN, discover_captures, sanitize_token
from uav_aoi_subset.core.exif import ExifReader
from uav_aoi_subset.core.progress import ProgressCallback, no_progress

DEFAULT_BANDS = 7

# The first four columns match the MATLAB tool's output, so results can be compared directly.
INDEX_COLUMNS = [
    "RecordName",
    "Complete",
    "GPSLatitude",
    "GPSLongitude",
    "GPSAltitude",
    "CaptureTime",
    "BandsFound",
    "MissingBands",
    "RelativeFolder",
    "ImageBase",
]

# utf-8-sig: Excel on Windows then shows non-ASCII folder names correctly.
CSV_ENCODING = "utf-8-sig"


class RecordNameCollisionError(ValueError):
    """Different folders produced the same record name (e.g. "A B" and "A_B")."""


@dataclass(frozen=True)
class IndexRecord:
    record_name: str
    complete: bool
    latitude: float | None
    longitude: float | None
    altitude: float | None
    capture_time: str | None
    bands_found: tuple[int, ...]
    missing_bands: tuple[int, ...]
    relative_folder: str
    image_base: str

    @property
    def has_position(self) -> bool:
        return self.latitude is not None and self.longitude is not None


def build_index(
    root: Path,
    reader: ExifReader,
    *,
    bands: int = DEFAULT_BANDS,
    pattern: str = DEFAULT_PATTERN,
    exclude: Iterable[str] = (),
    progress: ProgressCallback = no_progress,
    warnings: list[str] | None = None,
) -> list[IndexRecord]:
    """Index every capture under ``root``.

    The position of a capture is read from its band-1 file; captures without a band-1 file
    are still listed (incomplete, no position) so they show up in the report. Folders that
    were not scanned are reported in ``warnings`` (see :func:`discover_captures`).
    """
    if bands < 1:
        raise ValueError("bands must be at least 1")
    captures = discover_captures(
        root, pattern=pattern, exclude=exclude, progress=progress, warnings=warnings
    )

    names = Counter(c.record_name for c in captures)
    clashes = sorted(n for n, count in names.items() if count > 1)
    if clashes:
        folders = sorted({c.relative_folder for c in captures if c.record_name in clashes})
        raise RecordNameCollisionError(
            "These folders produce identical record names after replacing spaces and unsafe "
            "characters with '_'; rename one of them: " + ", ".join(folders)
        )

    band1 = [c.band_files[1] for c in captures if 1 in c.band_files]
    fixes = reader.read_gps(band1, progress=progress)

    records = []
    for c in captures:
        fix = fixes.get(c.band_files.get(1)) if 1 in c.band_files else None
        records.append(
            IndexRecord(
                record_name=c.record_name,
                complete=c.is_complete(bands),
                latitude=fix.latitude if fix else None,
                longitude=fix.longitude if fix else None,
                altitude=fix.altitude if fix else None,
                capture_time=fix.capture_time if fix else None,
                bands_found=c.bands_found,
                missing_bands=c.missing_bands(bands),
                relative_folder=c.relative_folder,
                image_base=c.base,
            )
        )
    return records


def default_index_path(root: Path, today: dt.date | None = None) -> Path:
    """``<root>/<project>_image_index_YYYYMMDD.csv``, project = root folder name."""
    root = Path(root)
    today = today or dt.date.today()
    project = sanitize_token(root.resolve().name) or "project"
    return root / f"{project}_image_index_{today:%Y%m%d}.csv"


def _fmt_float(value: float | None) -> str:
    return "" if value is None else repr(value)


def _fmt_bands(bands: tuple[int, ...]) -> str:
    return ";".join(str(b) for b in bands)


def write_index_csv(records: Iterable[IndexRecord], path: Path) -> None:
    with Path(path).open("w", encoding=CSV_ENCODING, newline="") as f:
        writer = csv.writer(f)
        writer.writerow(INDEX_COLUMNS)
        for r in records:
            writer.writerow(
                [
                    r.record_name,
                    "1" if r.complete else "0",
                    _fmt_float(r.latitude),
                    _fmt_float(r.longitude),
                    _fmt_float(r.altitude),
                    r.capture_time or "",
                    _fmt_bands(r.bands_found),
                    _fmt_bands(r.missing_bands),
                    r.relative_folder,
                    r.image_base,
                ]
            )


def _parse_float(text: str) -> float | None:
    text = text.strip()
    if not text or text.lower() == "nan":
        return None
    return float(text.replace(",", "."))


def _parse_bool(text: str) -> bool:
    return text.strip().lower() in {"1", "true", "yes"}


def _parse_bands(text: str) -> tuple[int, ...]:
    return tuple(int(b) for b in text.split(";") if b.strip())


def read_index_csv(path: Path) -> list[IndexRecord]:
    """Read an index CSV written by :func:`write_index_csv`."""
    with Path(path).open(encoding=CSV_ENCODING, newline="") as f:
        reader = csv.DictReader(f)
        missing = {"RecordName", "Complete", "GPSLatitude", "GPSLongitude"} - set(
            reader.fieldnames or []
        )
        if missing:
            raise ValueError(f"{path}: not an index CSV, missing columns: {sorted(missing)}")
        return [
            IndexRecord(
                record_name=row["RecordName"],
                complete=_parse_bool(row["Complete"]),
                latitude=_parse_float(row["GPSLatitude"]),
                longitude=_parse_float(row["GPSLongitude"]),
                altitude=_parse_float(row.get("GPSAltitude") or ""),
                capture_time=row.get("CaptureTime") or None,
                bands_found=_parse_bands(row.get("BandsFound") or ""),
                missing_bands=_parse_bands(row.get("MissingBands") or ""),
                relative_folder=row.get("RelativeFolder") or "",
                image_base=row.get("ImageBase") or "",
            )
            for row in reader
        ]
