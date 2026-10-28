"""Command-line interface. Thin wrapper around ``uav_aoi_subset.core``."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from uav_aoi_subset import __version__
from uav_aoi_subset.core.aoi import AOIError, load_aoi
from uav_aoi_subset.core.discovery import DEFAULT_PATTERN
from uav_aoi_subset.core.exif import ExifToolError, ExifToolNotFoundError, ExifToolReader
from uav_aoi_subset.core.filter import buffer_metres, default_subset_path, filter_records
from uav_aoi_subset.core.index import (
    DEFAULT_BANDS,
    IndexRecord,
    RecordNameCollisionError,
    build_index,
    default_index_path,
    read_index_csv,
    write_index_csv,
)

# How many incomplete captures / missing positions to list in the summary.
LIST_LIMIT = 20


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="uav-aoi-subset",
        description=(
            "Split large multispectral UAV image sets (MicaSense Altum-PT / RedEdge) into "
            "subsets that fall inside an area of interest drawn in Google Earth (KML/KMZ)."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p_index = sub.add_parser("index", help="Build a capture index CSV for a flight folder tree.")
    p_index.add_argument("root", type=Path, metavar="ROOT", help="Project root folder.")
    p_index.add_argument(
        "--bands",
        type=int,
        default=DEFAULT_BANDS,
        help=f"Band files per capture (default {DEFAULT_BANDS} for Altum-PT; RedEdge = 5).",
    )
    p_index.add_argument(
        "--pattern",
        default=DEFAULT_PATTERN,
        help="Regex for band file names with groups 'base' and 'band', matched "
        "case-insensitively (default: %(default)s).",
    )
    p_index.add_argument(
        "--exclude",
        nargs="+",
        default=[],
        metavar="DIR_GLOB",
        help="Skip folders whose name or ROOT-relative path (with '/') matches, "
        "case-insensitive. Example: --exclude 'Kalibrasyon_*' 'Pix4d_*'",
    )
    p_index.add_argument(
        "--out",
        type=Path,
        metavar="CSV",
        help="Output CSV path (default: ROOT/<root name>_image_index_YYYYMMDD.csv).",
    )
    p_index.add_argument(
        "--exiftool", type=Path, metavar="PATH", help="ExifTool executable (default: from PATH)."
    )

    p_filter = sub.add_parser("filter", help="Keep index rows that fall inside an AOI.")
    p_filter.add_argument(
        "index_csv", type=Path, metavar="INDEX_CSV", help="Index CSV written by 'index'."
    )
    p_filter.add_argument(
        "--aoi",
        type=Path,
        required=True,
        metavar="AREA",
        help="AOI polygon file (.kml/.kmz). Several polygons are combined; holes are honoured.",
    )
    p_filter.add_argument(
        "--buffer",
        type=float,
        default=0.0,
        metavar="METRES",
        help="Grow the AOI by this many metres (negative shrinks it).",
    )
    p_filter.add_argument(
        "--out",
        type=Path,
        metavar="CSV",
        help="Output CSV path (default: next to the AOI, <AOI name>_image_index_YYYYMMDD.csv).",
    )

    p_copy = sub.add_parser("copy", help="Copy the band files of a subset CSV.")
    p_copy.add_argument("root", type=Path, metavar="ROOT", help="Project root folder.")
    p_copy.add_argument("subset_csv", type=Path, metavar="SUBSET_CSV")
    p_copy.add_argument("--dest", type=Path, metavar="DIR", help="Output folder.")
    p_copy.add_argument("--mode", choices=["copy", "hardlink", "move"], default="copy")
    p_copy.add_argument("--dry-run", action="store_true", help="Report only, change nothing.")
    p_copy.add_argument(
        "--include", nargs="+", default=[], metavar="FILE_GLOB", help="Extra files to copy."
    )
    p_copy.add_argument(
        "--extra-captures",
        nargs="+",
        default=[],
        metavar="CAPTURE",
        help="Extra captures to copy, e.g. calibration-panel shots.",
    )

    p_footprint = sub.add_parser("footprint", help="Write the convex hull of all captures as KML.")
    p_footprint.add_argument("index_csv", type=Path, metavar="INDEX_CSV")
    p_footprint.add_argument("--out", type=Path, metavar="KML", help="Output KML path.")

    return parser


class _ConsoleProgress:
    """One self-overwriting status line on stderr; silent when stderr is not a terminal."""

    LABELS = {"scan": "Scanning folders: {done} files", "exif": "Reading GPS: {done}/{total}"}

    def __init__(self) -> None:
        self.enabled = sys.stderr.isatty()
        self.active = False

    def __call__(self, stage: str, done: int, total: int | None) -> None:
        if not self.enabled:
            return
        text = self.LABELS.get(stage, stage + ": {done}").format(done=done, total=total)
        sys.stderr.write("\r" + text.ljust(60))
        sys.stderr.flush()
        self.active = True

    def finish(self) -> None:
        if self.active:
            sys.stderr.write("\n")
            self.active = False


def _list_some(title: str, lines: list[str]) -> None:
    if not lines:
        return
    print(f"\n{title}:")
    for line in lines[:LIST_LIMIT]:
        print(f"  {line}")
    if len(lines) > LIST_LIMIT:
        print(f"  ... and {len(lines) - LIST_LIMIT} more (see the CSV)")


def _with_missing_bands(record: IndexRecord) -> str:
    # MATLAB index CSVs have no MissingBands column.
    if not record.missing_bands:
        return record.record_name
    return f"{record.record_name}  [{';'.join(map(str, record.missing_bands))}]"


def _run_index(args: argparse.Namespace) -> int:
    root: Path = args.root
    if not root.is_dir():
        print(f"error: not a folder: {root}", file=sys.stderr)
        return 1
    if args.bands < 1:
        print("error: --bands must be at least 1", file=sys.stderr)
        return 1
    try:
        regex = re.compile(args.pattern)
    except re.error as exc:
        print(f"error: invalid --pattern: {exc}", file=sys.stderr)
        return 1
    if not {"base", "band"} <= set(regex.groupindex):
        print("error: --pattern must define the groups 'base' and 'band'", file=sys.stderr)
        return 1

    progress = _ConsoleProgress()
    try:
        reader = ExifToolReader(args.exiftool)
        records = build_index(
            root,
            reader,
            bands=args.bands,
            pattern=args.pattern,
            exclude=args.exclude,
            progress=progress,
        )
    except (ExifToolNotFoundError, ExifToolError, RecordNameCollisionError) as exc:
        progress.finish()
        print(f"error: {exc}", file=sys.stderr)
        return 1
    progress.finish()

    if not records:
        print(f"No band files matching the pattern were found under {root}.", file=sys.stderr)
        return 1

    out = args.out or default_index_path(root)
    write_index_csv(records, out)

    incomplete = [r for r in records if not r.complete]
    no_position = [r for r in records if not r.has_position]
    print(f"Captures found:     {len(records)}")
    print(f"  complete:         {len(records) - len(incomplete)} (all {args.bands} bands)")
    print(f"  incomplete:       {len(incomplete)}")
    print(f"  with GPS:         {len(records) - len(no_position)}")
    _list_some(
        "Incomplete captures (missing bands)",
        [_with_missing_bands(r) for r in incomplete],
    )
    _list_some("Captures without a GPS position", [r.record_name for r in no_position])
    if reader.warnings:
        _list_some("ExifTool warnings", "\n".join(reader.warnings).splitlines())
    print(f"\nIndex written to: {out}")
    return 0


def _run_filter(args: argparse.Namespace) -> int:
    index_csv: Path = args.index_csv
    if not index_csv.is_file():
        print(f"error: not a file: {index_csv}", file=sys.stderr)
        return 1
    out = args.out or default_subset_path(args.aoi)
    if out.resolve() == index_csv.resolve():
        print(f"error: the output would overwrite the input index: {out}", file=sys.stderr)
        return 1
    try:
        records = read_index_csv(index_csv)
        aoi = load_aoi(args.aoi)
        area = buffer_metres(aoi.geometry, args.buffer)
    except (AOIError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    result = filter_records(records, area)
    write_index_csv(result.inside, out)

    incomplete = [r for r in result.inside if not r.complete]
    print(f"AOI:                {args.aoi}")
    print(f"  polygons:         {aoi.polygon_count} ({aoi.hole_count} holes)")
    if aoi.ignored_geometries:
        print(f"  ignored:          {aoi.ignored_geometries} non-polygon geometries")
    if args.buffer:
        print(f"  buffer:           {args.buffer:g} m")
    print(f"Captures in index:  {result.total}")
    print(f"  without GPS:      {len(result.no_position)} (cannot be placed, left out)")
    print(f"  inside the AOI:   {len(result.inside)}")
    print(f"    incomplete:     {len(incomplete)}")
    _list_some("AOI warnings", aoi.warnings)
    _list_some(
        "Incomplete captures inside the AOI (missing bands)",
        [_with_missing_bands(r) for r in incomplete],
    )
    if not result.inside:
        print(
            "\nwarning: no capture lies inside the AOI. Check that the KML covers the flight "
            "area, or try a --buffer.",
            file=sys.stderr,
        )
    print(f"\nSubset written to: {out}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    # Folder names may contain characters the console code page cannot show (Windows).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    if args.command == "index":
        return _run_index(args)
    if args.command == "filter":
        return _run_filter(args)
    print(f"uav-aoi-subset {args.command}: not implemented yet.", file=sys.stderr)
    return 2
