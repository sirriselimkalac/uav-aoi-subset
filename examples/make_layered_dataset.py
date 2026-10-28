"""Turn a one-folder dataset into a copy with a field-like folder tree (optional helper).

    uv run python examples/make_layered_dataset.py build  INPUT OUTPUT [--parts 4] [--bands 7]
                  [--pattern RE] [--mode copy|hardlink] [--folder-captures 200]
                  [--add-duplicate [GROUP]]
    uv run python examples/make_layered_dataset.py verify MAPPING_CSV FLAT_CSV LAYERED_CSV

Public example datasets are often published as one folder of band files. Field data is not:
many multispectral cameras open a new numbered set folder at every power-up or flight and
restart the image numbering there, so the same file name appears in several folders.

``build`` splits the captures of INPUT, in image-number order, into ``--parts`` consecutive
groups and writes group 1 to ``0000SET/000/``, group 2 to ``0001SET/000/`` and so on (a new
``001/``, ``002/`` ... folder every ``--folder-captures`` captures). Numbering restarts at 0 in
every group; band suffixes and extensions are kept. Other files of INPUT (for example a
calibration CSV) go to the first group's folder. ``--add-duplicate`` writes one group a second
time into ``old_subset/``, like a forgotten subset folder. A mapping CSV next to OUTPUT records
where every file went. INPUT is never changed.

``verify`` takes two subset CSVs made with the same AOI, one from INPUT and one from OUTPUT,
and reports whether they contain the same physical captures (exit code 0 if they do).
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import re
import shutil
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from uav_aoi_subset.console import ConsoleProgress
from uav_aoi_subset.core.copy import long_path, required_space
from uav_aoi_subset.core.discovery import DEFAULT_PATTERN, record_name
from uav_aoi_subset.core.index import CSV_ENCODING, IndexRecord, read_index_csv

EXIT_OK, EXIT_ERROR, EXIT_USAGE, EXIT_INTERRUPTED = 0, 1, 2, 130
DEFAULT_PARTS = 4
DEFAULT_BANDS = 7
DEFAULT_FOLDER_CAPTURES = 200  # captures per numbered sub-folder, as the camera does
DEFAULT_DUPLICATE_GROUP = 2
DUPLICATE_FOLDER = "old_subset"
PARTIAL_SUFFIX = ".partial"
SHOW = 20

BAND, AUXILIARY, DUPLICATE = "band", "auxiliary", "duplicate"
MAPPING_COLUMNS = (
    "OriginalFile",
    "OriginalImageBase",
    "OriginalRecordName",
    "Group",
    "Kind",
    "NewPath",
    "NewRelativeFolder",
    "NewImageBase",
    "NewRecordName",
)

_TRAILING_NUMBER = re.compile(r"^(?P<prefix>.*?)(?P<number>\d+)$")
# Files uav-aoi-subset writes (index / subset CSVs, copy reports); never part of the dataset.
_TOOL_OUTPUT = re.compile(
    r"(_image_index_\d{8}|_copy_report_\d{8}-\d{6}|_mapping)\.csv$", re.IGNORECASE
)


class LayoutError(Exception):
    """The layout cannot be made; ``next_step`` says what to do about it."""

    def __init__(self, message: str, next_step: str | None = None) -> None:
        super().__init__(message)
        self.next_step = next_step


@dataclass(frozen=True)
class Item:
    """One file to write: where it comes from and where it goes in OUTPUT."""

    source: Path
    new_path: PurePosixPath
    group: int  # 1-based; group 1 is 0000SET
    kind: str
    original_base: str = ""
    new_base: str = ""

    @property
    def new_folder(self) -> str:
        return self.new_path.parent.as_posix()

    @property
    def original_record(self) -> str:
        return record_name((), self.original_base) if self.original_base else ""

    @property
    def new_record(self) -> str:
        return record_name(self.new_path.parent.parts, self.new_base) if self.new_base else ""


@dataclass
class Layout:
    items: list[Item]
    groups: list[list[str]]  # original image bases per group, in order
    incomplete: int
    ignored_folders: list[str]
    tool_outputs: list[str]


def _fs(path: Path | str) -> Path:
    """Path to use for file-system calls (long-path safe on Windows)."""
    return Path(long_path(path))


def _fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} bytes"
    size = n / 1024
    for unit in ("KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _group_sizes(n: int, parts: int) -> list[int]:
    """Split ``n`` into ``parts`` consecutive sizes that differ by at most one."""
    size, rest = divmod(n, parts)
    return [size + 1 if g < rest else size for g in range(parts)]


def plan_layout(
    input_dir: Path,
    *,
    parts: int = DEFAULT_PARTS,
    bands: int = DEFAULT_BANDS,
    pattern: str = DEFAULT_PATTERN,
    folder_captures: int = DEFAULT_FOLDER_CAPTURES,
    duplicate_group: int | None = None,
) -> Layout:
    """Work out every file of the layered copy without writing anything."""
    regex = re.compile(pattern, re.IGNORECASE)
    captures: dict[str, list[tuple[Path, re.Match[str]]]] = {}
    bases: dict[str, str] = {}
    auxiliary: list[Path] = []
    ignored: list[str] = []
    tool_outputs: list[str] = []
    for entry in sorted(_fs(input_dir).iterdir(), key=lambda p: p.name):
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            ignored.append(entry.name)
            continue
        source = Path(input_dir) / entry.name
        match = regex.match(entry.name)
        if match is None:
            if _TOOL_OUTPUT.search(entry.name):
                tool_outputs.append(entry.name)
            else:
                auxiliary.append(source)
            continue
        key = match.group("base").upper()
        bases.setdefault(key, match.group("base"))
        captures.setdefault(key, []).append((source, match))

    if not captures:
        raise LayoutError(
            f"no band files found in {input_dir}",
            "Choose the folder that holds the image files themselves, or set --pattern to "
            "match their names.",
        )
    numbered = {}
    for key, base in bases.items():
        found = _TRAILING_NUMBER.match(base)
        if found is None:
            raise LayoutError(
                f"image name {base!r} does not end in a number, so it cannot be renumbered",
                "Set --pattern so that its 'base' group ends with the image number.",
            )
        numbered[key] = (int(found["number"]), key, found["prefix"], len(found["number"]))
    # One digit width for all new names, at least that of the longest original number.
    width = max(n[3] for n in numbered.values())
    if parts > len(captures):
        raise LayoutError(
            f"--parts {parts} is more than the {len(captures)} captures found",
            f"Use --parts {len(captures)} or less.",
        )

    order = sorted(numbered.values())
    items: list[Item] = []
    groups: list[list[str]] = []
    start = 0
    for g, size in enumerate(_group_sizes(len(order), parts)):
        groups.append([])
        for i, (_, key, prefix, _) in enumerate(order[start : start + size]):
            folder = PurePosixPath(f"{g:04d}SET", f"{i // folder_captures:03d}")
            new_base = f"{prefix}{i:0{width}d}"
            groups[-1].append(bases[key])
            for source, match in sorted(captures[key], key=lambda c: c[0].name):
                name = source.name
                new_name = name[: match.start("base")] + new_base + name[match.end("base") :]
                items.append(Item(source, folder / new_name, g + 1, BAND, bases[key], new_base))
        start += size

    first = PurePosixPath("0000SET", "000")
    items.extend(Item(p, first / p.name, 1, AUXILIARY) for p in auxiliary)

    if duplicate_group is not None:
        if not 1 <= duplicate_group <= parts:
            raise LayoutError(
                f"--add-duplicate {duplicate_group}: there are only groups 1 to {parts}",
                f"Use a group number from 1 to {parts}.",
            )
        for item in [i for i in items if i.kind == BAND and i.group == duplicate_group]:
            folder = PurePosixPath(DUPLICATE_FOLDER, "_".join(item.new_path.parent.parts))
            items.append(
                Item(
                    item.source,
                    folder / item.new_path.name,
                    item.group,
                    DUPLICATE,
                    item.original_base,
                    item.new_base,
                )
            )

    wanted = set(range(1, bands + 1))
    incomplete = sum(
        not wanted <= {int(m.group("band")) for _, m in files} for files in captures.values()
    )
    return Layout(items, groups, incomplete, ignored, tool_outputs)


def mapping_path(output: Path) -> Path:
    """``<OUTPUT>_mapping.csv`` next to OUTPUT, so it never ends up inside the copied tree."""
    output = Path(output)
    return output.with_name(f"{output.name}_mapping.csv")


def write_mapping(items: list[Item], path: Path, input_dir: Path) -> None:
    with Path(path).open("w", encoding=CSV_ENCODING, newline="") as f:
        writer = csv.writer(f)
        writer.writerow(MAPPING_COLUMNS)
        for item in items:
            writer.writerow(
                [
                    item.source.relative_to(input_dir).as_posix(),
                    item.original_base,
                    item.original_record,
                    item.group,
                    item.kind,
                    item.new_path.as_posix(),
                    item.new_folder if item.new_base else "",
                    item.new_base,
                    item.new_record,
                ]
            )


def _error(message: str, next_step: str | None = None) -> int:
    """Print an error and what to do about it; returns the exit code for errors."""
    print(f"error: {message}", file=sys.stderr)
    if next_step:
        print(f"  {next_step}", file=sys.stderr)
    return EXIT_ERROR


def _existing_ancestor(path: Path) -> Path:
    while not path.exists() and path.parent != path:
        path = path.parent
    return path


def _check_paths(input_dir: Path, output: Path) -> int | None:
    if not input_dir.is_dir():
        return _error(f"{input_dir} is not a folder", "Give the folder that holds the band files.")
    if output == input_dir or output.is_relative_to(input_dir):
        return _error(
            "OUTPUT must not be inside INPUT",
            "Choose a folder next to INPUT, for example "
            f"{input_dir.with_name(input_dir.name + '_layered')}.",
        )
    if input_dir.is_relative_to(output):
        return _error("INPUT is inside OUTPUT", "Choose an OUTPUT folder outside INPUT.")
    if output.exists() and not output.is_dir():
        return _error(f"{output} exists and is not a folder", "Choose another OUTPUT.")
    if output.is_dir() and any(_fs(output).iterdir()):
        return _error(
            f"{output} is not empty",
            "Choose a new OUTPUT folder, or delete this one if it is an earlier, unfinished run.",
        )
    if mapping_path(output).exists():
        return _error(
            f"{mapping_path(output)} already exists",
            "Delete it if it belongs to an earlier run, or choose another OUTPUT.",
        )
    return None


def _write(items: list[Item], output: Path, mode: str, progress: ConsoleProgress) -> None:
    """Write every item; a KeyboardInterrupt leaves no partial file behind."""
    partial: Path | None = None
    try:
        for done, item in enumerate(items):
            progress("copy", done, len(items))
            target = output / Path(*item.new_path.parts)
            _fs(target.parent).mkdir(parents=True, exist_ok=True)
            if mode == "hardlink":
                os.link(long_path(item.source), long_path(target))
            else:
                partial = target.with_name(target.name + PARTIAL_SUFFIX)
                shutil.copy2(long_path(item.source), long_path(partial))
                _fs(partial).replace(long_path(target))
                partial = None
        progress("copy", len(items), len(items))
    finally:
        if partial is not None:
            _fs(partial).unlink(missing_ok=True)


def run_build(args: argparse.Namespace) -> int:
    input_dir = Path(args.input).resolve()
    output = Path(args.output).resolve()
    failed = _check_paths(input_dir, output)
    if failed is not None:
        return failed
    try:
        re.compile(args.pattern)
    except re.error as exc:
        return _error(
            f"--pattern is not a valid regular expression: {exc}",
            f"The default is {DEFAULT_PATTERN}",
        )
    if not {"base", "band"} <= set(re.compile(args.pattern).groupindex):
        return _error(
            "--pattern must define the groups (?P<base>...) and (?P<band>...)",
            f"The default is {DEFAULT_PATTERN}",
        )
    for option, value in (
        ("--parts", args.parts),
        ("--bands", args.bands),
        ("--folder-captures", args.folder_captures),
    ):
        if value < 1:
            return _error(f"{option} must be at least 1", f"Run with {option} 1 or more.")

    try:
        layout = plan_layout(
            input_dir,
            parts=args.parts,
            bands=args.bands,
            pattern=args.pattern,
            folder_captures=args.folder_captures,
            duplicate_group=args.add_duplicate,
        )
    except LayoutError as exc:
        return _error(str(exc), exc.next_step)
    except OSError as exc:
        return _error(
            f"cannot read {input_dir}: {exc.strerror or exc}",
            "Check that the folder exists and that you are allowed to read it.",
        )

    items = layout.items
    captures = sum(len(g) for g in layout.groups)
    total_bytes = sum(_fs(i.source).stat().st_size for i in items)
    needed = 0 if args.mode == "hardlink" else total_bytes
    target_drive = _existing_ancestor(output)
    if args.mode == "hardlink" and _fs(input_dir).stat().st_dev != _fs(target_drive).stat().st_dev:
        return _error(
            "hard links only work on one drive, and OUTPUT is on another drive than INPUT",
            "Put OUTPUT on the same drive as INPUT, or use --mode copy.",
        )
    free = shutil.disk_usage(long_path(target_drive)).free

    print(f"Input:            {input_dir}")
    print(f"Output:           {output}")
    print(f"Captures:         {captures:,} ({layout.incomplete:,} incomplete, copied as they are)")
    for g, bases in enumerate(layout.groups):
        print(f"  {g:04d}SET:        {len(bases):,} captures, {bases[0]} to {bases[-1]}")
    auxiliary = [i for i in items if i.kind == AUXILIARY]
    if auxiliary:
        print(f"Other files:      {len(auxiliary):,} (into 0000SET/000)")
    duplicates = [i for i in items if i.kind == DUPLICATE]
    if duplicates:
        print(
            f"Duplicate:        group {args.add_duplicate} again in {DUPLICATE_FOLDER}/ "
            f"({len(duplicates):,} files)"
        )
    for name in layout.ignored_folders:
        print(f"warning: sub-folder ignored (only files directly in INPUT are used): {name}")
    for name in layout.tool_outputs:
        print(f"Not copied (written by uav-aoi-subset): {name}")
    print(f"Files to write:   {len(items):,} ({args.mode})")
    print(f"Space needed:     {_fmt_bytes(needed)} (free: {_fmt_bytes(free)})")
    if needed and free < required_space(needed):
        return _error(
            f"not enough free space: {_fmt_bytes(required_space(needed))} needed "
            f"(including a small reserve), {_fmt_bytes(free)} free",
            "Free some space, choose OUTPUT on another drive, or use --mode hardlink on the "
            "same drive as INPUT.",
        )

    sys.stdout.flush()  # the summary before the progress lines on stderr
    progress = ConsoleProgress()
    try:
        _fs(output).mkdir(parents=True, exist_ok=True)
        _write(items, output, args.mode, progress)
    except KeyboardInterrupt:
        progress.finish()
        print("Interrupted.", file=sys.stderr)
        print(f"  The output is incomplete: delete {output} and run again.", file=sys.stderr)
        return EXIT_INTERRUPTED
    except OSError as exc:
        progress.finish()
        reason = exc.strerror or str(exc)
        if args.mode == "hardlink":
            return _error(
                f"cannot create a hard link: {reason}",
                "The drive may not support hard links; use --mode copy. Then delete "
                f"{output} and run again.",
            )
        return _error(
            f"cannot write {exc.filename or output}: {reason}",
            f"Delete {output}, fix the cause and run again.",
        )
    progress.finish()

    mapping = mapping_path(output)
    try:
        write_mapping(items, mapping, input_dir)
    except OSError as exc:
        return _error(
            f"cannot write {mapping}: {exc.strerror or exc}",
            f"The layered copy is complete; delete {output} and run again to get the mapping.",
        )
    print(f"Written:          {len(items):,} files, {_fmt_bytes(needed)}")
    print(f"Mapping:          {mapping}")
    return EXIT_OK


# --- verify -------------------------------------------------------------------------


@dataclass(frozen=True)
class Mapping:
    by_original_base: dict[str, str]
    by_original_record: dict[str, str]
    by_new_capture: dict[tuple[str, str], str]
    by_new_record: dict[str, str]


def read_mapping(path: Path) -> Mapping:
    with Path(path).open(encoding=CSV_ENCODING, newline="") as f:
        reader = csv.DictReader(f)
        missing = set(MAPPING_COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: not a mapping CSV, missing columns: {sorted(missing)}")
        mapping = Mapping({}, {}, {}, {})
        for row in reader:
            original = row["OriginalImageBase"]
            if not original:
                continue  # other files are not captures
            mapping.by_original_base[original.upper()] = original
            mapping.by_original_record[row["OriginalRecordName"]] = original
            key = (row["NewRelativeFolder"], row["NewImageBase"].upper())
            mapping.by_new_capture[key] = original
            mapping.by_new_record[row["NewRecordName"]] = original
    return mapping


def _flat_original(record: IndexRecord, mapping: Mapping) -> str | None:
    if record.image_base:
        return mapping.by_original_base.get(record.image_base.upper())
    return mapping.by_original_record.get(record.record_name)


def _layered_original(record: IndexRecord, mapping: Mapping) -> str | None:
    if record.image_base:
        key = (record.relative_folder, record.image_base.upper())
        return mapping.by_new_capture.get(key)
    return mapping.by_new_record.get(record.record_name)


def _show(title: str, items: list[str]) -> None:
    if not items:
        return
    print(f"{title}: {len(items)}")
    for item in items[:SHOW]:
        print(f"  {item}")
    if len(items) > SHOW:
        print(f"  ... and {len(items) - SHOW} more")


def _same_position(a: IndexRecord, b: IndexRecord) -> bool:
    if not (a.has_position and b.has_position):
        return a.has_position == b.has_position
    return math.isclose(a.latitude, b.latitude, abs_tol=1e-9) and math.isclose(
        a.longitude, b.longitude, abs_tol=1e-9
    )


def verify(mapping: Mapping, flat: list[IndexRecord], layered: list[IndexRecord]) -> bool:
    """Print the comparison; True if both subsets hold the same physical captures."""
    flat_by_original: dict[str, IndexRecord] = {}
    unknown_flat, unknown_layered = [], []
    for r in flat:
        original = _flat_original(r, mapping)
        if original is None:
            unknown_flat.append(r.record_name)
        else:
            flat_by_original[original] = r
    layered_originals: Counter[str] = Counter()
    position = []
    for r in layered:
        original = _layered_original(r, mapping)
        if original is None:
            unknown_layered.append(r.record_name)
            continue
        layered_originals[original] += 1
        twin = flat_by_original.get(original)
        if twin is not None and not _same_position(twin, r):
            position.append(f"{r.record_name} (= {original})")

    only_flat = sorted(flat_by_original.keys() - layered_originals.keys())
    only_layered = sorted(layered_originals.keys() - flat_by_original.keys())
    copies = sorted(o for o, n in layered_originals.items() if n > 1)
    print(f"Captures: {len(flat_by_original)} (flat) / {len(layered_originals)} (layered)")
    _show("Only in the flat subset", only_flat)
    _show("Only in the layered subset", only_layered)
    _show("Flat records not in the mapping", unknown_flat)
    _show("Layered records not in the mapping", unknown_layered)
    _show("Position differs", position)
    if copies:
        extra = sum(layered_originals[o] - 1 for o in copies)
        _show(f"Captures found more than once in the layered subset ({extra} extra)", copies)
        print("  Copies of the same capture: filter or copy with --skip-duplicates.")
    different = only_flat or only_layered or unknown_flat or unknown_layered or position
    print("RESULT: " + ("DIFFERENT" if different else "SAME"))
    return not different


def run_verify(args: argparse.Namespace) -> int:
    paths = (("MAPPING_CSV", args.mapping), ("FLAT_CSV", args.flat), ("LAYERED_CSV", args.layered))
    for name, path in paths:
        if not Path(path).is_file():
            return _error(
                f"{name} {path} not found",
                "The mapping CSV is written next to the layered folder by 'build'; the subset "
                "CSVs by 'uav-aoi-subset filter'.",
            )
    try:
        mapping = read_mapping(Path(args.mapping))
        flat = read_index_csv(Path(args.flat))
        layered = read_index_csv(Path(args.layered))
    except (ValueError, OSError) as exc:
        return _error(str(exc), "Check the order: MAPPING_CSV FLAT_CSV LAYERED_CSV.")
    return EXIT_OK if verify(mapping, flat, layered) else EXIT_ERROR


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="make_layered_dataset.py",
        description="Make a field-like layered copy of a one-folder dataset of band files, "
        "and check that both give the same subsets.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser(
        "build",
        help="write the layered copy",
        description="Split the captures of INPUT, in image-number order, into consecutive "
        "groups written to 0000SET/000, 0001SET/000 ... with numbering restarting in every "
        "group. INPUT is never changed.",
    )
    build.add_argument("input", metavar="INPUT", help="folder that holds the band files")
    build.add_argument(
        "output", metavar="OUTPUT", help="new folder outside INPUT (must not exist or be empty)"
    )
    build.add_argument(
        "--parts", type=int, default=DEFAULT_PARTS, help="number of set folders (default: 4)"
    )
    build.add_argument(
        "--bands", type=int, default=DEFAULT_BANDS, help="bands per capture (default: 7)"
    )
    build.add_argument(
        "--pattern",
        default=DEFAULT_PATTERN,
        help="band file name regex with groups 'base' and 'band', as in uav-aoi-subset "
        f"(default: {DEFAULT_PATTERN})",
    )
    build.add_argument(
        "--mode",
        choices=("copy", "hardlink"),
        default="copy",
        help="copy (default) needs as much free space as the data. hardlink needs no extra "
        "space and only works on the drive of INPUT, but the new files share their contents "
        "with the originals: editing one changes the other.",
    )
    build.add_argument(
        "--folder-captures",
        type=int,
        default=DEFAULT_FOLDER_CAPTURES,
        metavar="N",
        help="start a new numbered sub-folder (000, 001 ...) every N captures (default: 200)",
    )
    build.add_argument(
        "--add-duplicate",
        type=int,
        nargs="?",
        const=DEFAULT_DUPLICATE_GROUP,
        metavar="GROUP",
        help=f"also write group GROUP (default: {DEFAULT_DUPLICATE_GROUP}) into "
        f"{DUPLICATE_FOLDER}/, like a forgotten earlier subset folder",
    )
    build.set_defaults(run=run_build)

    check = sub.add_parser(
        "verify",
        help="compare a subset of the flat data with one of the layered copy",
        description="Compare two subset CSVs made with the same AOI, one from the flat data and "
        "one from the layered copy, through the mapping CSV. Exit code 0 if they hold the same "
        "physical captures.",
    )
    check.add_argument("mapping", metavar="MAPPING_CSV", help="<OUTPUT>_mapping.csv from build")
    check.add_argument("flat", metavar="FLAT_CSV", help="subset CSV of the flat data")
    check.add_argument("layered", metavar="LAYERED_CSV", help="subset CSV of the layered copy")
    check.set_defaults(run=run_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.run(args)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return EXIT_INTERRUPTED


if __name__ == "__main__":
    sys.exit(main())
