"""Command-line interface. Thin wrapper around ``uav_aoi_subset.core``."""

from __future__ import annotations

import argparse
import platform
import re
import sys
import traceback
from collections.abc import Sequence
from pathlib import Path

from uav_aoi_subset import __version__, pickers
from uav_aoi_subset.console import ConsoleProgress
from uav_aoi_subset.core.aoi import AOIError, load_aoi
from uav_aoi_subset.core.copy import (
    FOLDERS,
    LAYOUTS,
    MODES,
    CopyError,
    CopyPlan,
    default_dest,
    default_report_path,
    execute_copy,
    load_extra_captures,
    plan_copy,
    required_space,
    write_copy_report,
)
from uav_aoi_subset.core.discovery import DEFAULT_PATTERN
from uav_aoi_subset.core.duplicates import can_detect, drop_duplicates, find_duplicates
from uav_aoi_subset.core.exif import (
    ExifToolError,
    ExifToolNotFoundError,
    ExifToolReader,
    exiftool_version,
    find_exiftool,
)
from uav_aoi_subset.core.filter import buffer_metres, default_subset_path, filter_records
from uav_aoi_subset.core.footprint import (
    DEFAULT_RATIO,
    HULLS,
    FootprintError,
    FootprintResult,
    build_footprints,
    default_footprint_path,
    footprint_placemarks,
)
from uav_aoi_subset.core.index import (
    DEFAULT_BANDS,
    IndexRecord,
    RecordNameCollisionError,
    build_index,
    default_index_path,
    read_index_csv,
    write_index_csv,
)
from uav_aoi_subset.core.kml import write_kml

# How many incomplete captures / missing positions to list in the summary.
LIST_LIMIT = 20

SKIP_DUPLICATES_HELP = (
    "Copies of the same capture in several folders (same image, capture time and position, "
    "e.g. an old subset folder inside ROOT): keep only the first, by folder name, and list the "
    "others. Without this option all copies are kept and a warning lists them."
)

ISSUES_URL = "https://github.com/sirriselimkalac/uav-aoi-subset/issues"

EXIT_OK, EXIT_ERROR, EXIT_USAGE, EXIT_INTERRUPTED = 0, 1, 2, 130
EXIT_CODES_HELP = """\
exit codes:
  0    success
  1    error (the message says what to do next) or a picker was cancelled
  2    usage error: a required argument is missing or an option is invalid
  130  interrupted with Ctrl+C

Run '%(prog)s COMMAND --help' for the options of a command. Leave out a required path to
choose it in a file/folder picker (when run interactively)."""


def version_text() -> str:
    """Package, Python and ExifTool versions: what a bug report needs."""
    lines = [
        f"uav-aoi-subset {__version__}",
        f"Python {platform.python_version()} ({platform.platform(terse=True)})",
    ]
    try:
        exiftool = find_exiftool()
        lines.append(f"ExifTool {exiftool_version(exiftool)} at {exiftool}")
    except ExifToolNotFoundError:
        lines.append("ExifTool: not found on PATH (needed by 'index'; see the README)")
    except ExifToolError as exc:
        lines.append(f"ExifTool: {exc}")
    return "\n".join(lines)


class _VersionAction(argparse.Action):
    """Like argparse's version action, but runs ExifTool only when --version is given."""

    def __init__(self, option_strings, dest=argparse.SUPPRESS, help=None):
        super().__init__(option_strings, dest=dest, default=argparse.SUPPRESS, nargs=0, help=help)

    def __call__(self, parser, namespace, values, option_string=None):
        print(version_text())
        parser.exit()


def _error(message: str, next_step: str | None = None) -> int:
    """Print an error and what to do about it; returns the exit code for errors."""
    print(f"error: {message}", file=sys.stderr)
    if next_step:
        print(f"  {next_step}", file=sys.stderr)
    return EXIT_ERROR


def _cannot_write(path: Path, exc: OSError, option: str = "--out") -> int:
    if isinstance(exc, PermissionError):
        return _error(
            f"cannot write {path}: permission denied",
            "Close the file if another program (e.g. a spreadsheet) has it open, or choose a "
            f"location you can write to with {option}.",
        )
    return _error(
        f"cannot write {path}: {exc.strerror or exc}",
        f"Check that the folder exists and the drive is not full, or use {option}.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="uav-aoi-subset",
        description=(
            "Split large drone image sets (e.g. multispectral cameras that write one file per "
            "band) into subsets that fall inside an area of interest drawn as a KML/KMZ "
            "polygon."
        ),
        epilog=EXIT_CODES_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action=_VersionAction,
        help="Show the program, Python and ExifTool versions (include them in bug reports).",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    parser.subcommands = sub.choices  # for errors that need the subcommand's usage line

    # Options every command accepts.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--no-picker",
        action="store_true",
        help="Never open a file/folder picker for a missing path; fail with a usage error "
        f"instead (same as setting {pickers.ENV_NO_PICKER}=1).",
    )
    common.add_argument(
        "--debug",
        action="store_true",
        help="Show the full traceback when an unexpected error occurs.",
    )

    p_index = sub.add_parser(
        "index", parents=[common], help="Build a capture index CSV for a flight folder tree."
    )
    p_index.add_argument(
        "root",
        type=Path,
        nargs="?",
        metavar="ROOT",
        help="Project root folder (if left out, a folder picker opens).",
    )
    p_index.add_argument(
        "--bands",
        type=int,
        default=DEFAULT_BANDS,
        help=f"Band files per capture (default {DEFAULT_BANDS}; use your camera's band count).",
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
        "case-insensitive. Example: --exclude 'Calibration*' 'processing_*'",
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

    p_filter = sub.add_parser(
        "filter", parents=[common], help="Keep index rows that fall inside an AOI."
    )
    p_filter.add_argument(
        "index_csv",
        type=Path,
        nargs="?",
        metavar="INDEX_CSV",
        help="Index CSV written by 'index' (if left out, a file picker opens).",
    )
    p_filter.add_argument(
        "--aoi",
        type=Path,
        metavar="AREA",
        help="AOI polygon file (.kml/.kmz), required. Several polygons are combined; holes "
        "are honoured. If left out, a file picker opens in the folder of INDEX_CSV.",
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
    p_filter.add_argument("--skip-duplicates", action="store_true", help=SKIP_DUPLICATES_HELP)

    p_copy = sub.add_parser(
        "copy",
        parents=[common],
        help="Copy the band files of a subset CSV into a new output folder.",
        description="Copy (or hard-link, or move) the band files of the captures in "
        "SUBSET_CSV into a new folder, with one sub-folder per source folder, named after "
        "its folder chain (A/B/C/IMG_0000_1.tif -> A_B_C/IMG_0000_1.tif); file names are "
        "not changed. Every run writes to a new "
        "<ROOT name>_subset_NN folder next to ROOT unless --dest is given. Files already at "
        "the destination with the same size are skipped, so an interrupted run can be "
        "resumed with --dest <its folder>; files with a different size are never overwritten "
        "without --overwrite.",
    )
    p_copy.add_argument(
        "root",
        type=Path,
        nargs="?",
        metavar="ROOT",
        help="Project root folder, as given to 'index' (if left out, a folder picker opens).",
    )
    p_copy.add_argument(
        "subset_csv",
        type=Path,
        nargs="?",
        metavar="SUBSET_CSV",
        help="CSV written by 'filter' (if left out, a file picker opens in ROOT).",
    )
    p_copy.add_argument(
        "--dest",
        type=Path,
        metavar="DIR",
        help="Output folder (default: a new <ROOT parent>/<ROOT name>_subset_NN with the next "
        "free number). To resume an interrupted run, give its folder here.",
    )
    p_copy.add_argument(
        "--mode",
        choices=MODES,
        default="copy",
        help="copy (default); hardlink (same drive only, uses no extra space); move (removes "
        "the files from ROOT, needs --confirm-move).",
    )
    p_copy.add_argument(
        "--layout",
        choices=LAYOUTS,
        default=FOLDERS,
        help="folders (default): one folder per source folder, file names unchanged "
        "(A_B_C/IMG_0000_1.tif); flat: all files in one folder and RENAMED to "
        "A_B_C_IMG_0000_1.tif - make sure your software supports renamed files.",
    )
    p_copy.add_argument(
        "--confirm-move", action="store_true", help="Confirm that --mode move may remove files."
    )
    p_copy.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace destination files whose size differs from the source.",
    )
    p_copy.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without writing anything (add --report to save the list).",
    )
    p_copy.add_argument(
        "--report",
        type=Path,
        metavar="CSV",
        help="Per-file report (default: <output folder>_copy_report_YYYYMMDD-HHMMSS.csv next "
        "to the output folder; not written on --dry-run unless given).",
    )
    p_copy.add_argument(
        "--bands",
        type=int,
        default=DEFAULT_BANDS,
        help=f"Band files per capture (default {DEFAULT_BANDS}; as for 'index').",
    )
    p_copy.add_argument(
        "--pattern", default=DEFAULT_PATTERN, help="Band file name regex, as for 'index'."
    )
    p_copy.add_argument(
        "--exclude",
        nargs="+",
        default=[],
        metavar="DIR_GLOB",
        help="Folders to skip while looking for captures, as for 'index' (speeds up big trees).",
    )
    p_copy.add_argument(
        "--include",
        nargs="+",
        default=[],
        metavar="FILE_GLOB",
        help="Helper files to copy into the output root, relative to ROOT or absolute; '**' "
        "matches any folder depth. Example: --include '**/*reflectance*.csv'",
    )
    p_copy.add_argument(
        "--extra-captures",
        nargs="+",
        default=[],
        metavar="NAME_OR_FILE",
        help="Captures to add although they are outside the AOI, e.g. calibration-panel shots: "
        "record names, text files with one name per line, or an index CSV. Found even in "
        "--exclude'd folders.",
    )
    p_copy.add_argument("--skip-duplicates", action="store_true", help=SKIP_DUPLICATES_HELP)

    p_footprint = sub.add_parser(
        "footprint",
        parents=[common],
        help="Write the outline of all capture positions as a KML polygon.",
        description="Write the hull of the capture positions in INDEX_CSV as a KML polygon for "
        "Google Earth. The positions are capture centres: the imaged ground reaches further, "
        "which --buffer can approximate. The KML can be used as an AOI for 'filter'.",
    )
    p_footprint.add_argument(
        "index_csv",
        type=Path,
        nargs="?",
        metavar="INDEX_CSV",
        help="Index or subset CSV (CSVs with only the first four index columns work too, "
        "except with --per-folder). "
        "If left out, a file picker opens.",
    )
    p_footprint.add_argument(
        "--out",
        type=Path,
        metavar="KML",
        help="Output KML path (default: next to the CSV, <CSV name>.kml).",
    )
    p_footprint.add_argument(
        "--hull",
        choices=HULLS,
        default="convex",
        help="convex (default) or concave: follows L-shaped or scattered flights more closely.",
    )
    p_footprint.add_argument(
        "--ratio",
        type=float,
        metavar="R",
        help=f"Concave hull tightness, 0 < R <= 1: smaller is tighter, 1 equals convex "
        f"(default {DEFAULT_RATIO:g}).",
    )
    p_footprint.add_argument(
        "--buffer",
        type=float,
        default=0.0,
        metavar="METRES",
        help="Grow the outline by this many metres (negative shrinks it).",
    )
    p_footprint.add_argument(
        "--per-folder",
        type=int,
        nargs="?",
        const=0,
        metavar="DEPTH",
        help="One polygon per capture folder instead of one for everything. With DEPTH, "
        "folders are combined at that many levels below ROOT (e.g. 2 for Part1/0000SET).",
    )
    p_footprint.add_argument(
        "--overwrite", action="store_true", help="Replace the output KML if it exists."
    )

    return parser


def _list_some(title: str, lines: list[str]) -> None:
    if not lines:
        return
    print(f"\n{title}:")
    for line in lines[:LIST_LIMIT]:
        print(f"  {line}")
    if len(lines) > LIST_LIMIT:
        print(f"  ... and {len(lines) - LIST_LIMIT} more (see the CSV)")


def _duplicate_line(group: list[IndexRecord]) -> str:
    folders = ", ".join(r.relative_folder or "." for r in group)
    return f"{group[0].image_base} ({group[0].capture_time}) in: {folders}"


def _list_duplicates(groups: list[list[IndexRecord]], hint: str) -> None:
    _list_some(
        "Captures found in more than one folder (same image, capture time and position)",
        [_duplicate_line(g) for g in groups],
    )
    if groups:
        print(f"  {hint}")


def _copies(groups: list[list[IndexRecord]]) -> int:
    return sum(len(g) - 1 for g in groups)


def _with_missing_bands(record: IndexRecord) -> str:
    # MATLAB index CSVs have no MissingBands column.
    if not record.missing_bands:
        return record.record_name
    return f"{record.record_name}  [{';'.join(map(str, record.missing_bands))}]"


def _pattern_ok(pattern: str) -> bool:
    example = f"The default is: --pattern '{DEFAULT_PATTERN}'"
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        _error(f"invalid --pattern: {exc}", f"Check the regular expression. {example}")
        return False
    if not {"base", "band"} <= set(regex.groupindex):
        _error(
            "--pattern must define the groups 'base' and 'band'",
            f"Name them with (?P<base>...) and (?P<band>...). {example}",
        )
        return False
    return True


def _not_a_folder(path: Path, name: str) -> int:
    return _error(
        f"not a folder: {path}",
        f"Check the path (in quotes if it contains spaces), or leave {name} out to choose "
        "it in a folder picker.",
    )


def _not_a_file(path: Path, name: str) -> int:
    return _error(
        f"not a file: {path}",
        f"Check the path (in quotes if it contains spaces), or leave {name} out to choose "
        "it in a file picker.",
    )


def _bands_ok(bands: int) -> bool:
    if bands < 1:
        _error("--bands must be at least 1", "Give the number of band files per capture.")
        return False
    return True


def _read_records(path: Path) -> list[IndexRecord] | None:
    try:
        return read_index_csv(path)
    except (ValueError, OSError) as exc:
        _error(
            f"cannot read {path}: {exc}",
            "Give a CSV written by 'index' or 'filter' (close it in other programs first).",
        )
        return None


def _run_index(args: argparse.Namespace) -> int:
    root: Path = args.root
    if not root.is_dir():
        return _not_a_folder(root, "ROOT")
    if not _bands_ok(args.bands) or not _pattern_ok(args.pattern):
        return 1

    progress = ConsoleProgress()
    not_scanned: list[str] = []
    try:
        reader = ExifToolReader(args.exiftool)
        records = build_index(
            root,
            reader,
            bands=args.bands,
            pattern=args.pattern,
            exclude=args.exclude,
            progress=progress,
            warnings=not_scanned,
        )
    except ExifToolNotFoundError as exc:
        return _error(str(exc))  # the message already says how to install it
    except ExifToolError as exc:
        return _error(
            str(exc), "Check that 'exiftool -ver' works; re-run with --debug for details."
        )
    except RecordNameCollisionError as exc:
        return _error(str(exc))  # names the folders to rename
    finally:
        progress.finish()

    if not records:
        _list_some("Folders not scanned", not_scanned)
        return _error(
            f"no band files matching the pattern were found under {root}",
            "Check ROOT, --pattern and --bands, and that --exclude does not skip the image "
            "folders.",
        )

    out = args.out or default_index_path(root)
    try:
        write_index_csv(records, out)
    except OSError as exc:
        return _cannot_write(out, exc)

    incomplete = [r for r in records if not r.complete]
    no_position = [r for r in records if not r.has_position]
    print(f"Captures found:     {len(records)}")
    print(f"  complete:         {len(records) - len(incomplete)} (all {args.bands} bands)")
    print(f"  incomplete:       {len(incomplete)}")
    print(f"  with GPS:         {len(records) - len(no_position)}")
    duplicates = find_duplicates(records)
    if duplicates:
        print(f"  extra copies:     {_copies(duplicates)} (same capture in another folder)")
    _list_some(
        "Incomplete captures (missing bands)",
        [_with_missing_bands(r) for r in incomplete],
    )
    _list_some("Captures without a GPS position", [r.record_name for r in no_position])
    _list_duplicates(
        duplicates,
        "Leave the copies out with --exclude <their folder>, or with --skip-duplicates in "
        "'filter' or 'copy'.",
    )
    _list_some("Folders not scanned", not_scanned)
    if reader.warnings:
        _list_some("ExifTool warnings", "\n".join(reader.warnings).splitlines())
    print(f"\nIndex written to: {out}")
    return 0


def _run_filter(args: argparse.Namespace) -> int:
    index_csv: Path = args.index_csv
    if not index_csv.is_file():
        return _not_a_file(index_csv, "INDEX_CSV")
    if not args.aoi.is_file():
        return _not_a_file(args.aoi, "--aoi")
    out = args.out or default_subset_path(args.aoi)
    if out.resolve() == index_csv.resolve():
        return _error(
            f"the output would overwrite the input index: {out}", "Give another path with --out."
        )
    records = _read_records(index_csv)
    if records is None:
        return 1
    try:
        aoi = load_aoi(args.aoi)
    except AOIError as exc:
        return _error(
            str(exc),
            "Save the area as a polygon (not a path or a placemark) in a .kml or .kmz file.",
        )
    try:
        area = buffer_metres(aoi.geometry, args.buffer)
    except ValueError as exc:
        return _error(str(exc), "Use a smaller negative --buffer, or none.")

    result = filter_records(records, area)
    duplicates = find_duplicates(result.inside)
    inside = drop_duplicates(result.inside)[0] if args.skip_duplicates else result.inside
    try:
        write_index_csv(inside, out)
    except OSError as exc:
        return _cannot_write(out, exc)

    incomplete = [r for r in inside if not r.complete]
    print(f"AOI:                {args.aoi}")
    print(f"  polygons:         {aoi.polygon_count} ({aoi.hole_count} holes)")
    if aoi.ignored_geometries:
        print(f"  ignored:          {aoi.ignored_geometries} non-polygon geometries")
    if args.buffer:
        print(f"  buffer:           {args.buffer:g} m")
    print(f"Captures in index:  {result.total}")
    print(f"  without GPS:      {len(result.no_position)} (cannot be placed, left out)")
    print(f"  inside the AOI:   {len(result.inside)}")
    if duplicates:
        what = "left out" if args.skip_duplicates else "kept"
        print(f"    extra copies:   {_copies(duplicates)} ({what})")
    print(f"    incomplete:     {len(incomplete)}")
    _list_some("AOI warnings", aoi.warnings)
    _list_some(
        "Incomplete captures inside the AOI (missing bands)",
        [_with_missing_bands(r) for r in incomplete],
    )
    _list_duplicates(
        duplicates,
        "Only the first folder of each is in the subset."
        if args.skip_duplicates
        else "All copies are in the subset; add --skip-duplicates to keep only the first.",
    )
    if args.skip_duplicates and not can_detect(records):
        print(
            "\nwarning: this CSV has no capture times (ImageBase/CaptureTime columns), so "
            "copies cannot be recognised; --skip-duplicates had no effect.",
            file=sys.stderr,
        )
    if not result.inside:
        print(
            "\nwarning: no capture lies inside the AOI. Check that the KML covers the flight "
            "area, or try a --buffer.",
            file=sys.stderr,
        )
    print(f"\nSubset written to: {out}")
    return 0


def _fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} bytes"
    size = n / 1024
    for unit in ("KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _print_copy_summary(plan: CopyPlan, dry_run: bool) -> None:
    s = plan.summary()
    st = s.statuses
    if dry_run:
        verb = {"copy": "to copy", "hardlink": "to link", "move": "to move"}[plan.mode]
    else:
        verb = {"copy": "copied", "hardlink": "linked", "move": "moved"}[plan.mode]
    pending = st["would-copy"] + st["would-link"] + st["would-move"] + st["would-overwrite"]
    done = st["copied"] + st["linked"] + st["moved"] + st["overwritten"]
    print(
        f"Subset records:     {s.records}"
        + (f" (+ {s.extra_records} extra)" if s.extra_records else "")
    )
    print(f"  captures found:   {s.captures}")
    print(f"  not found:        {len(s.not_found)}")
    if s.ambiguous:
        print(f"  ambiguous:        {len(s.ambiguous)}")
    if s.duplicates:
        print(f"  extra copies:     {len(s.duplicates)} (left out, see below)")
    print(f"  incomplete:       {len(s.incomplete)} (the bands that exist are included)")
    print(f"Captures {verb}:".ljust(20) + f"{s.groups_transferred}")
    print(f"  already complete: {s.groups_skipped}")
    print(
        f"Files {verb}:".ljust(20)
        + f"{pending if dry_run else done} ({_fmt_bytes(s.bytes_transferred)})"
    )
    skipped = st["skipped-existing"] + st["already-at-destination"]
    print(f"  skipped:          {skipped} (already at the destination)")
    if st["would-overwrite"] or st["overwritten"]:
        print(f"  overwritten:      {st['would-overwrite'] + st['overwritten']}")
    print(f"  conflicts:        {st['conflict']} (different size at the destination, left alone)")
    if not dry_run:
        print(f"  failed:           {st['failed'] + st['aborted']}")
    if s.include_files:
        print(f"Include files:      {s.include_files}")
    print(
        f"Space needed:       {_fmt_bytes(plan.bytes_needed)} + reserve = "
        f"{_fmt_bytes(required_space(plan.bytes_needed))} (free: {_fmt_bytes(plan.bytes_free)})"
    )
    _list_some("Captures not found under ROOT", s.not_found)
    _list_some(
        "Record names found in more than one folder (not copied; use a CSV with "
        "RelativeFolder/ImageBase)",
        s.ambiguous,
    )
    _list_some("Extra copies left out (--skip-duplicates)", s.duplicates)
    if plan.duplicates and not s.duplicates:
        _list_duplicates(
            plan.duplicates,
            "All copies are included; add --skip-duplicates to copy only the first.",
        )
    _list_some("Incomplete captures", s.incomplete)
    _list_some(
        "Conflicts",
        [f"{t.destination}: {t.message}" for t in plan.tasks if t.status == "conflict"],
    )
    _list_some("Failed", [f"{t.source}: {t.message}" for t in plan.tasks if t.status == "failed"])


def _run_copy(args: argparse.Namespace) -> int:
    root: Path = args.root
    if not root.is_dir():
        return _not_a_folder(root, "ROOT")
    if not args.subset_csv.is_file():
        return _not_a_file(args.subset_csv, "SUBSET_CSV")
    if not _bands_ok(args.bands) or not _pattern_ok(args.pattern):
        return 1
    if args.mode == "move" and not args.confirm_move:
        return _error(
            "--mode move removes the band files from ROOT",
            "Add --confirm-move if that is what you want, or use --mode copy / hardlink.",
        )

    records = _read_records(args.subset_csv)
    if records is None:
        return 1
    progress = ConsoleProgress()
    try:
        extras = load_extra_captures(args.extra_captures)
        dest = args.dest or default_dest(root)
        plan = plan_copy(
            root,
            records,
            dest,
            mode=args.mode,
            layout=args.layout,
            bands=args.bands,
            pattern=args.pattern,
            exclude=args.exclude,
            extra_captures=extras,
            include=args.include,
            overwrite=args.overwrite,
            skip_duplicates=args.skip_duplicates,
            subset_name=args.subset_csv.name,
            progress=progress,
        )
    except CopyError as exc:
        return _error(str(exc))  # copy errors already name the option to change
    except PermissionError as exc:
        return _cannot_write(Path(exc.filename or args.dest or root), exc, "--dest")
    except (ValueError, OSError) as exc:
        return _error(str(exc), "Check ROOT, SUBSET_CSV, --dest and --extra-captures.")
    finally:
        progress.finish()

    print(f"Output folder:      {plan.dest}")
    if args.dest is None and not args.dry_run:
        print("  (new folder; if this run is interrupted, resume it with --dest and this path)")
    print(f"Layout:             {args.layout}")
    print(
        f"Mode:               {plan.mode}"
        + ("  (dry run, nothing is written)" if args.dry_run else "")
    )
    for warning in plan.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if args.skip_duplicates and not can_detect(records):
        print(
            "warning: SUBSET_CSV has no capture times (ImageBase/CaptureTime columns), so copies "
            "cannot be recognised; --skip-duplicates has no effect",
            file=sys.stderr,
        )

    if not plan.enough_space:
        _print_copy_summary(plan, dry_run=True)
        print(file=sys.stderr)
        return _error(
            f"not enough free space at {plan.dest}: "
            f"{_fmt_bytes(required_space(plan.bytes_needed))} needed, "
            f"{_fmt_bytes(plan.bytes_free)} free",
            "Free some space, choose a --dest on another drive, or use --mode hardlink "
            "(same drive only, needs no extra space).",
        )

    failed = None
    if not args.dry_run:
        try:
            execute_copy(plan, progress=progress)
        except CopyError as exc:
            failed = exc
        except KeyboardInterrupt:
            progress.finish()
            _write_report_quietly(plan, args.report or default_report_path(plan.dest))
            print(
                "\nUnfinished files were removed. To resume, run the same command "
                f'with --dest "{plan.dest}"',
                file=sys.stderr,
            )
            raise
        finally:
            progress.finish()

    _print_copy_summary(plan, dry_run=args.dry_run)
    report = args.report or (None if args.dry_run else default_report_path(plan.dest))
    if report is not None:
        try:
            write_copy_report(plan.tasks, report)
            print(f"\nReport written to: {report}")
        except OSError as exc:
            return _cannot_write(report, exc, "--report")
    if failed is not None:
        print(file=sys.stderr)
        return _error(str(failed))
    st = plan.summary().statuses
    return 1 if st["conflict"] or st["failed"] else 0


def _write_report_quietly(plan: CopyPlan, report: Path) -> None:
    """Best effort after an interruption: the report shows what was done so far."""
    try:
        write_copy_report(plan.tasks, report)
        print(f"\nReport of the files done so far: {report}", file=sys.stderr)
    except OSError:
        pass


def _footprint_args_ok(args: argparse.Namespace, out: Path) -> bool:
    if not args.index_csv.is_file():
        _not_a_file(args.index_csv, "INDEX_CSV")
        return False
    if args.ratio is not None and args.hull != "concave":
        _error("--ratio only applies to --hull concave", "Add --hull concave or drop --ratio.")
        return False
    if args.ratio is not None and not 0 < args.ratio <= 1:
        _error(
            "--ratio must be greater than 0 and at most 1",
            f"Try the default {DEFAULT_RATIO:g}; smaller values follow the captures more tightly.",
        )
        return False
    if args.per_folder is not None and args.per_folder < 0:
        _error(
            "--per-folder DEPTH must be at least 1",
            "Leave DEPTH out for one polygon per capture folder.",
        )
        return False
    if out.suffix.lower() != ".kml":
        _error(f"the output must be a .kml file: {out}", "Give a path ending in .kml to --out.")
        return False
    if out.exists() and not args.overwrite:
        _error(f"{out} exists", "Add --overwrite to replace it, or choose another --out.")
        return False
    return True


def _print_footprint_summary(result: FootprintResult, per_folder: bool) -> None:
    used = result.total - len(result.no_position)
    print(f"Captures in CSV:    {result.total}")
    print(f"  without GPS:      {len(result.no_position)} (left out)")
    print(f"  used:             {used}")
    hull = result.hull + (f" (ratio {result.ratio:g})" if result.hull == "concave" else "")
    print(f"Hull:               {hull}")
    if result.buffer:
        print(f"Buffer:             {result.buffer:g} m")
    if per_folder:
        skipped = f" ({len(result.skipped_groups)} skipped)" if result.skipped_groups else ""
        print(f"Polygons:           {len(result.areas)}{skipped}")
        print(f"Combined area:      {result.combined_hectares():.2f} ha")
        _list_some(
            "Polygons (folder: captures, area)",
            [f"{a.name}: {a.captures}, {a.hectares:.2f} ha" for a in result.areas],
        )
        _list_some("Folders skipped", [f"{f}: {why}" for f, why in result.skipped_groups])
    else:
        print(f"Area:               {result.areas[0].hectares:.2f} ha")
    _list_some("Captures without a GPS position", [r.record_name for r in result.no_position])


def _run_footprint(args: argparse.Namespace) -> int:
    index_csv: Path = args.index_csv
    out: Path = args.out or default_footprint_path(index_csv)
    if not _footprint_args_ok(args, out):
        return 1
    per_folder = args.per_folder is not None
    records = _read_records(index_csv)
    if records is None:
        return 1
    try:
        result = build_footprints(
            records,
            name=index_csv.stem,
            hull=args.hull,
            ratio=DEFAULT_RATIO if args.ratio is None else args.ratio,
            buffer=args.buffer,
            per_folder=per_folder,
            depth=args.per_folder or None,
        )
        placemarks, styles = footprint_placemarks(result, index_csv.name)
        write_kml(
            out,
            placemarks,
            document_name=index_csv.stem,
            styles=styles,
            folder_name="Folders" if per_folder else None,
            overwrite=args.overwrite,
        )
    except FileExistsError:
        return _error(f"{out} exists", "Add --overwrite to replace it, or choose another --out.")
    except (FootprintError, ValueError) as exc:
        return _error(
            str(exc),
            "Check that the CSV has capture positions (run 'index' with ExifTool available).",
        )
    except OSError as exc:
        return _cannot_write(out, exc)

    _print_footprint_summary(result, per_folder)
    print(f"\nFootprint written to: {out}")
    return 0


# Paths each command needs, in the order the pickers ask for them:
# (attribute, metavar or option, "folder"/"file", picker title, file types).
REQUIRED_PATHS = {
    "index": [("root", "ROOT", "folder", "Select the project root folder", None)],
    "filter": [
        ("index_csv", "INDEX_CSV", "file", "Select the index CSV", pickers.CSV_FILES),
        ("aoi", "--aoi", "file", "Select the AOI polygon (KML/KMZ)", pickers.AOI_FILES),
    ],
    "copy": [
        ("root", "ROOT", "folder", "Select the project root folder", None),
        ("subset_csv", "SUBSET_CSV", "file", "Select the subset CSV", pickers.CSV_FILES),
    ],
    "footprint": [
        ("index_csv", "INDEX_CSV", "file", "Select the index or subset CSV", pickers.CSV_FILES)
    ],
}

# Command-line tokens that need no quoting in any common shell.
_SAFE_TOKEN = re.compile(r"[A-Za-z0-9_.,:/=+@%-]+")


def _quote(token: str, always: bool = False) -> str:
    if not always and _SAFE_TOKEN.fullmatch(token):
        return token
    return '"' + token + '"'


def equivalent_command(
    tokens: Sequence[str],
    picked: Sequence[tuple[str, Path]],
    typed: Sequence[Path] = (),
) -> str:
    """The command line that repeats this run without pickers.

    ``tokens`` is what the user typed (starting with the command), ``typed`` the positional
    paths among them and ``picked`` the (metavar or option, path) pairs chosen in pickers.
    Picked positionals go right after the last typed one: argparse would not assign a second
    positional that is separated from the first by options.
    """
    out = [_quote(t) for t in tokens]
    positionals = [(name, path) for name, path in picked if not name.startswith("-")]
    options = [(name, path) for name, path in picked if name.startswith("-")]
    if positionals:
        at = 1  # right after the command
        for i, token in enumerate(tokens[1:], start=1):
            if not token.startswith("-") and Path(token) in typed:
                at = i + 1
        out[at:at] = [_quote(str(path), always=True) for _, path in positionals]
    for name, path in options:
        out += [name, _quote(str(path), always=True)]
    return " ".join(["uav-aoi-subset", *out])


def _fill_missing_paths(
    parser: argparse.ArgumentParser, args: argparse.Namespace, tokens: Sequence[str]
) -> int | None:
    """Ask for missing required paths in pickers. Returns an exit code to stop with."""
    needed = REQUIRED_PATHS.get(args.command, [])
    missing = [item for item in needed if getattr(args, item[0]) is None]
    if not missing:
        return None
    subparser = parser.subcommands[args.command]
    names = ", ".join(item[1] for item in missing)
    if not pickers.pickers_available(args.no_picker):
        subparser.error(f"the following arguments are required: {names}")

    picked: list[tuple[str, Path]] = []
    # The next picker opens where the previous path is (MATLAB did the same).
    given = [getattr(args, item[0]) for item in needed if getattr(args, item[0]) is not None]
    start = given[-1] if given else None
    for attr, name, kind, title, filetypes in missing:
        initialdir = None if start is None else (start if start.is_dir() else start.parent)
        try:
            if kind == "folder":
                path = pickers.ask_folder(title, initialdir)
            else:
                path = pickers.ask_open_file(title, filetypes, initialdir)
        except pickers.PickerCancelled:
            print(f"Cancelled: no {kind} selected; nothing was done.", file=sys.stderr)
            return 1
        except pickers.PickerUnavailable as exc:
            subparser.error(
                f"the following arguments are required: {names} (no file picker could be "
                f"opened: {exc}; give the paths on the command line)"
            )
        setattr(args, attr, path)
        picked.append((name, path))
        start = path
    typed = [p for p in given if p is not getattr(args, "aoi", None)]
    print(f"Equivalent command: {equivalent_command(tokens, picked, typed)}\n")
    return None


def main(argv: Sequence[str] | None = None) -> int:
    # Folder names may contain characters the console code page cannot show (Windows).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = build_parser()
    tokens = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(tokens)
    if args.command is None:
        parser.print_help()
        return 2
    try:
        stop = _fill_missing_paths(parser, args, tokens)
        if stop is not None:
            return stop
        return COMMANDS[args.command](args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return EXIT_INTERRUPTED
    except Exception as exc:
        if args.debug:
            traceback.print_exc()
        print(f"error: unexpected {type(exc).__name__}: {exc}", file=sys.stderr)
        if not args.debug:
            print("  Re-run with --debug to see the details.", file=sys.stderr)
        print(
            f"  Please report it at {ISSUES_URL} with the command, its output and the "
            "output of 'uav-aoi-subset --version'.",
            file=sys.stderr,
        )
        return EXIT_ERROR


COMMANDS = {
    "index": _run_index,
    "filter": _run_filter,
    "copy": _run_copy,
    "footprint": _run_footprint,
}
