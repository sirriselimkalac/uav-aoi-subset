"""Copy, hard-link or move the band files of a subset into one flat output folder.

Work happens in two steps. :func:`plan_copy` finds every band file, decides its destination
and what to do with it without writing anything (this is also the ``--dry-run`` result).
:func:`execute_copy` then carries the plan out. Both leave their outcome in the task list, so
a dry run and a real run produce the same report.

Relative folders are flattened (``A/B/C`` -> ``A_B_C``) so Pix4Dmapper gets one level of
folders. Files are written under a temporary name and renamed when complete, so an
interrupted run never leaves a truncated file under the final name; a later run skips the
files that are already there with the same size and never overwrites others unless asked.
"""

from __future__ import annotations

import csv
import datetime as dt
import glob
import ntpath
import os
import re
import shutil
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from uav_aoi_subset.core.discovery import (
    DEFAULT_PATTERN,
    OUTPUT_MARKER,
    Capture,
    discover_captures,
    flat_folder_name,
    sanitize_token,
)
from uav_aoi_subset.core.index import (
    CSV_ENCODING,
    DEFAULT_BANDS,
    IndexRecord,
    read_index_csv,
)
from uav_aoi_subset.core.progress import ProgressCallback, no_progress

MODES = ("copy", "hardlink", "move")

# Suffix of files that are still being written; never counted as finished.
PARTIAL_SUFFIX = ".uas-partial"

# Longest path that classic Windows programs (and Pix4Dmapper) can open.
WINDOWS_MAX_PATH = 259

# Required free space: needed bytes x factor + reserve.
SPACE_FACTOR = 1.02
SPACE_RESERVE = 100 * 1024**2

# Task kinds
CAPTURE, EXTRA, INCLUDE = "capture", "extra", "include"

# Task statuses. Pending ones (dry run / not yet executed) start with "would-".
WOULD = {"copy": "would-copy", "hardlink": "would-link", "move": "would-move"}
DONE = {"copy": "copied", "hardlink": "linked", "move": "moved"}
WOULD_OVERWRITE, OVERWRITTEN = "would-overwrite", "overwritten"
SKIPPED = "skipped-existing"
CONFLICT = "conflict"
MISSING_BAND = "missing-band"
ALREADY = "already-at-destination"
NOT_FOUND = "not-found"
AMBIGUOUS = "ambiguous"
FAILED = "failed"
ABORTED = "aborted"
PENDING = {*WOULD.values(), WOULD_OVERWRITE}
TRANSFERRED = {*DONE.values(), OVERWRITTEN}

REPORT_COLUMNS = [
    "Kind",
    "RecordName",
    "Band",
    "Source",
    "Destination",
    "Status",
    "Bytes",
    "Message",
]

MARKER_TEXT = "Created by uav-aoi-subset copy. Folders containing this file are never indexed.\n"


class CopyError(Exception):
    """A problem that stops the copy before (or while) files are written."""


@dataclass
class FileTask:
    """One file (or one capture that could not be found) and what happens to it."""

    kind: str
    record_name: str
    status: str
    band: int | None = None
    source: Path | None = None
    destination: Path | None = None
    size: int = 0
    mode: str = "copy"
    same_device: bool = True
    message: str = ""

    @property
    def writes_data(self) -> bool:
        """True if carrying the task out needs free space at the destination."""
        if self.status not in PENDING:
            return False
        return self.mode == "copy" or (self.mode == "move" and not self.same_device)


@dataclass(frozen=True)
class CopySummary:
    records: int
    extra_records: int
    captures: int
    not_found: list[str]
    ambiguous: list[str]
    incomplete: list[str]
    statuses: Counter
    groups_transferred: int
    groups_skipped: int
    include_files: int
    bytes_transferred: int
    bytes_total: int


@dataclass
class CopyPlan:
    root: Path
    dest: Path
    mode: str
    overwrite: bool
    tasks: list[FileTask]
    records: int
    extra_records: int
    bytes_needed: int
    bytes_free: int
    warnings: list[str] = field(default_factory=list)

    @property
    def enough_space(self) -> bool:
        return self.bytes_free >= required_space(self.bytes_needed)

    def summary(self) -> CopySummary:
        return summarize(self)


def required_space(bytes_needed: int) -> int:
    return 0 if bytes_needed == 0 else int(bytes_needed * SPACE_FACTOR) + SPACE_RESERVE


def long_path(path: Path | str, *, windows: bool | None = None) -> str:
    """Path string for file-system calls; on Windows with the ``\\\\?\\`` long-path prefix.

    The prefix lifts the 260-character limit of the Windows API. Other systems get the path
    unchanged.
    """
    if windows is None:
        windows = os.name == "nt"
    text = os.fspath(path)
    if not windows or text.startswith("\\\\?\\"):
        return text
    if not ntpath.isabs(text):
        text = ntpath.abspath(text)
    text = ntpath.normpath(text)
    if text.startswith("\\\\"):
        return "\\\\?\\UNC\\" + text[2:]
    return "\\\\?\\" + text


def _fs(path: Path | str) -> Path:
    """Path to use for file-system calls (long-path safe on Windows)."""
    return Path(long_path(path))


def default_dest(root: Path, subset_csv: Path) -> Path:
    """``<ROOT parent>/<ROOT name>_subsets/<subset CSV name>``, always outside ROOT."""
    root = Path(root).resolve()
    if root.parent == root:
        raise CopyError(
            f"{root} is the top of a drive, so there is no folder next to it for the output; "
            "choose one with --dest"
        )
    project = sanitize_token(root.name) or "project"
    subset = sanitize_token(Path(subset_csv).stem) or "subset"
    return root.parent / f"{project}_subsets" / subset


def default_report_path(dest: Path, now: dt.datetime | None = None) -> Path:
    """``<dest>_copy_report_YYYYMMDD-HHMMSS.csv`` next to the output folder."""
    now = now or dt.datetime.now()
    dest = Path(dest)
    return dest.with_name(f"{dest.name}_copy_report_{now:%Y%m%d-%H%M%S}.csv")


def assign_flat_folders(rel_folders: Iterable[tuple[str, ...]]) -> dict[tuple[str, ...], str]:
    """Give every relative folder a unique flat output folder name.

    ``A/B/C`` becomes ``A_B_C``. When several folders end up with the same name, compared
    case-insensitively because macOS and Windows file systems are, the later ones in sorted
    order get ``_v02``, ``_v03``... The root folder (no parts) maps to ``""``.
    """
    names: dict[tuple[str, ...], str] = {}
    used: set[str] = set()
    for parts in sorted(set(rel_folders)):
        base = flat_folder_name(parts)
        name, n = base, 2
        while name.casefold() in used:
            name, n = f"{base}_v{n:02d}", n + 1
        used.add(name.casefold())
        names[parts] = name
    return names


def load_extra_captures(values: Iterable[str]) -> list[IndexRecord]:
    """Record names from ``--extra-captures``.

    Each value is an index/subset CSV (has a ``RecordName`` column), a text file with one
    record name per line (``#`` starts a comment), or a record name.
    """
    records: list[IndexRecord] = []
    for value in values:
        path = Path(value)
        if not path.is_file():
            records.append(_name_only(value.strip()))
            continue
        with path.open(encoding=CSV_ENCODING, newline="") as f:
            first = f.readline()
        if "RecordName" in first:
            records.extend(read_index_csv(path))
            continue
        for line in path.read_text(encoding=CSV_ENCODING).splitlines():
            name = line.split("#", 1)[0].strip()
            if name:
                records.append(_name_only(name))
    return records


def _name_only(name: str) -> IndexRecord:
    return IndexRecord(
        record_name=name,
        complete=False,
        latitude=None,
        longitude=None,
        altitude=None,
        capture_time=None,
        bands_found=(),
        missing_bands=(),
        relative_folder="",
        image_base="",
    )


def _nfc(text: str) -> str:
    # macOS may store decomposed (NFD) letters; CSVs written on Windows use NFC.
    return unicodedata.normalize("NFC", text)


def _capture_key(rel_parts: Iterable[str], base: str) -> tuple[tuple[str, ...], str]:
    return tuple(_nfc(p) for p in rel_parts), base.upper()


class _Lookup:
    """Find captures on disk by folder + base, or by record name for MATLAB CSVs."""

    def __init__(self, captures: list[Capture]) -> None:
        self.by_key = {_capture_key(c.rel_parts, c.base): c for c in captures}
        self.by_name: dict[str, list[Capture]] = {}
        for c in captures:
            self.by_name.setdefault(_nfc(c.record_name), []).append(c)

    def find(self, record: IndexRecord) -> tuple[tuple[str, ...] | None, str | None, list[Capture]]:
        """Return (relative folder parts, base, matching captures) for a record.

        Folder parts and base come from the CSV when it has them, else from the match.
        """
        if record.image_base:
            parts = PurePosixPath(record.relative_folder).parts if record.relative_folder else ()
            parts = tuple(_nfc(p) for p in parts)
            match = self.by_key.get(_capture_key(parts, record.image_base))
            return parts, record.image_base, [match] if match else []
        return None, None, self.by_name.get(_nfc(record.record_name.strip()), [])


def _stat(path: Path) -> os.stat_result | None:
    try:
        return _fs(path).stat()
    except FileNotFoundError:
        return None


def _existing_ancestor(path: Path) -> Path:
    path = Path(path).resolve()
    while not path.exists() and path.parent != path:
        path = path.parent
    return path


def _inside(child: Path, parent: Path) -> bool:
    c = os.path.normcase(os.fspath(Path(child).resolve()))
    p = os.path.normcase(os.fspath(Path(parent).resolve()))
    return c == p or c.startswith(p.rstrip(os.sep) + os.sep)


def _check_dest(root: Path, dest: Path) -> list[str]:
    if _inside(root, dest):
        raise CopyError(f"the output folder {dest} contains ROOT {root}; choose another --dest")
    warnings = []
    if _inside(dest, root):
        warnings.append(
            f"the output folder {dest} is inside ROOT; it is marked with {OUTPUT_MARKER} so "
            "'index' skips it, but a folder outside ROOT is safer"
        )
    target = _fs(dest)
    if target.exists():
        if not target.is_dir():
            raise CopyError(f"{dest} exists and is not a folder")
        if not (target / OUTPUT_MARKER).exists() and any(target.iterdir()):
            raise CopyError(
                f"{dest} is not empty and was not created by this tool (no {OUTPUT_MARKER} "
                "file); choose an empty or new --dest"
            )
    return warnings


class _DestListing:
    """Band files already in the output folders, by (BASE, band); listed once per folder."""

    def __init__(self, regex: re.Pattern[str]) -> None:
        self.regex = regex
        self.cache: dict[Path, dict[tuple[str, int], str]] = {}

    def get(self, folder: Path) -> dict[tuple[str, int], str]:
        if folder not in self.cache:
            found: dict[tuple[str, int], str] = {}
            try:
                names = [p.name for p in _fs(folder).iterdir()]
            except OSError:
                names = []
            for name in names:
                m = self.regex.match(name)
                if m:
                    found[(m.group("base").upper(), int(m.group("band")))] = name
            self.cache[folder] = found
        return self.cache[folder]


def _file_task(
    kind: str,
    record_name: str,
    band: int | None,
    source: Path,
    destination: Path,
    mode: str,
    overwrite: bool,
    dest_device: int,
) -> FileTask:
    src = _fs(source).stat()
    task = FileTask(
        kind=kind,
        record_name=record_name,
        status=WOULD[mode],
        band=band,
        source=source,
        destination=destination,
        size=src.st_size,
        mode=mode,
        same_device=src.st_dev == dest_device,
    )
    dst = _stat(destination)
    if dst is None:
        return task
    if dst.st_size == src.st_size:  # also true for an existing hard link to the source
        task.status = SKIPPED
    elif overwrite:
        task.status = WOULD_OVERWRITE
    else:
        task.status = CONFLICT
        task.message = f"destination exists with {dst.st_size} bytes, source has {src.st_size}"
    return task


def plan_copy(
    root: Path,
    records: Iterable[IndexRecord],
    dest: Path,
    *,
    mode: str = "copy",
    bands: int = DEFAULT_BANDS,
    pattern: str = DEFAULT_PATTERN,
    exclude: Iterable[str] = (),
    extra_captures: Iterable[IndexRecord] = (),
    include: Iterable[str] = (),
    overwrite: bool = False,
    progress: ProgressCallback = no_progress,
) -> CopyPlan:
    """Work out every file operation without changing anything on disk.

    ``records`` are the subset rows; ``extra_captures`` are added on top (looked up without
    ``exclude``, since calibration-panel folders are usually excluded from the index).
    ``include`` globs (relative to ``root`` or absolute) select helper files that are copied
    to the output root.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if bands < 1:
        raise ValueError("bands must be at least 1")
    root, dest = Path(root), Path(dest).resolve()
    exclude = tuple(exclude)
    records, extra_captures = list(records), list(extra_captures)
    warnings = _check_dest(root, dest)
    regex = re.compile(pattern, re.IGNORECASE)

    captures = discover_captures(root, pattern=pattern, exclude=exclude, progress=progress)
    lookup = _Lookup(captures)
    if extra_captures and exclude:
        extra_lookup = _Lookup(discover_captures(root, pattern=pattern, progress=progress))
    else:
        extra_lookup = lookup

    # Match every record once: (kind, name, folder parts, image base, matching captures).
    wanted = []
    seen: set[str] = set()
    for kind, rows, finder in ((CAPTURE, records, lookup), (EXTRA, extra_captures, extra_lookup)):
        for record in rows:
            parts, base, matches = finder.find(record)
            if len(matches) == 1:
                c = matches[0]
                parts, base = tuple(_nfc(p) for p in c.rel_parts), c.base
                key = repr(_capture_key(parts, base))
            else:
                key = "name:" + _nfc(record.record_name)
            if key in seen:
                continue
            seen.add(key)
            wanted.append((kind, record.record_name, parts, base, matches))

    flat = assign_flat_folders(parts for _, _, parts, _, _ in wanted if parts is not None)
    dest_device = _existing_ancestor(dest).stat().st_dev
    listing = _DestListing(regex)
    tasks: list[FileTask] = []
    for i, (kind, name, parts, base, matches) in enumerate(wanted):
        progress("plan", i, len(wanted))
        if len(matches) > 1:
            folders = ", ".join(c.relative_folder or "." for c in matches)
            tasks.append(FileTask(kind, name, AMBIGUOUS, message=f"found in: {folders}"))
            continue
        capture = matches[0] if matches else None
        if parts is None:  # MATLAB CSV row, nothing on disk to tell the folder
            tasks.append(FileTask(kind, name, NOT_FOUND))
            continue
        folder = dest / flat[parts] if flat[parts] else dest
        files = capture.band_files if capture else {}
        ext = next(iter(files.values())).suffix if files else ".tif"
        at_dest = listing.get(folder)
        band_tasks = []
        for band in sorted(set(range(1, bands + 1)) | set(files)):
            if band in files:
                source = files[band]
                target = folder / source.name
                band_tasks.append(
                    _file_task(kind, name, band, source, target, mode, overwrite, dest_device)
                )
            elif (base.upper(), band) in at_dest:
                target = folder / at_dest[(base.upper(), band)]
                band_tasks.append(FileTask(kind, name, ALREADY, band, destination=target))
            else:
                target = folder / f"{base}_{band}{ext}"
                band_tasks.append(FileTask(kind, name, MISSING_BAND, band, destination=target))
        if all(t.status == MISSING_BAND for t in band_tasks):
            tasks.append(FileTask(kind, name, NOT_FOUND))
        else:
            tasks.extend(band_tasks)
    progress("plan", len(wanted), len(wanted))

    tasks.extend(_include_tasks(root, dest, include, tasks, mode, overwrite, dest_device, warnings))

    if mode == "hardlink":
        other = [t for t in tasks if t.status in PENDING and not t.same_device]
        if other:
            raise CopyError(
                f"hard links only work on one drive, but {other[0].source} is on a different "
                f"drive than {dest}; use --mode copy, or a --dest on the same drive"
            )

    longest = max((len(os.fspath(t.destination)) for t in tasks if t.destination), default=0)
    if longest > WINDOWS_MAX_PATH:
        warnings.append(
            f"some output paths are {longest} characters long; Pix4Dmapper and other Windows "
            f"programs may not open paths longer than {WINDOWS_MAX_PATH}; choose a shorter --dest"
        )

    needed = sum(t.size for t in tasks if t.writes_data)
    free = shutil.disk_usage(_existing_ancestor(dest)).free
    return CopyPlan(
        root=root,
        dest=dest,
        mode=mode,
        overwrite=overwrite,
        tasks=tasks,
        records=len(records),
        extra_records=len(extra_captures),
        bytes_needed=needed,
        bytes_free=free,
        warnings=warnings,
    )


def _include_tasks(
    root: Path,
    dest: Path,
    patterns: Iterable[str],
    tasks: list[FileTask],
    mode: str,
    overwrite: bool,
    dest_device: int,
    warnings: list[str],
) -> list[FileTask]:
    # Helper files are copied, never moved: they stay where other tools expect them.
    file_mode = "copy" if mode == "move" else mode
    used = {os.fspath(t.destination).casefold() for t in tasks if t.destination}
    seen: set[str] = set()
    out = []
    for pattern in patterns:
        # glob.glob, not Path.glob: patterns may also be absolute.
        matched = sorted(glob.glob(pattern, root_dir=root, recursive=True))  # noqa: PTH207
        files = [root / m for m in matched if (root / m).is_file()]
        files = [f for f in files if not _inside(f, dest)]
        if not files:
            warnings.append(f"--include {pattern!r} matched no files")
        for source in files:
            key = os.path.normcase(os.fspath(source.resolve()))
            if key in seen:
                continue
            seen.add(key)
            target, n = dest / source.name, 2
            while os.fspath(target).casefold() in used:
                target, n = dest / f"{source.stem}_v{n:02d}{source.suffix}", n + 1
            used.add(os.fspath(target).casefold())
            out.append(
                _file_task(INCLUDE, "", None, source, target, file_mode, overwrite, dest_device)
            )
    return out


def _link(source: Path, target: Path) -> None:
    """Create a hard link (a separate function so tests can simulate failures)."""
    target.hardlink_to(source)


def _transfer(task: FileTask) -> None:
    assert task.source is not None and task.destination is not None
    source, destination = _fs(task.source), _fs(task.destination)
    if task.status != WOULD_OVERWRITE and (destination.exists() or destination.is_symlink()):
        raise OSError(f"{task.destination} appeared during the run; not overwritten")
    if task.mode == "move" and task.same_device:
        source.replace(destination)
        return
    temp = destination.with_name(destination.name + PARTIAL_SUFFIX)
    try:
        temp.unlink(missing_ok=True)  # left over from an interrupted run
        if task.mode == "hardlink":
            _link(source, temp)
        else:
            shutil.copy2(source, temp)
            written = temp.stat().st_size
            if written != task.size:
                raise OSError(f"copied {written} of {task.size} bytes")
        temp.replace(destination)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    if task.mode == "move":
        source.unlink()


def execute_copy(plan: CopyPlan, *, progress: ProgressCallback = no_progress) -> None:
    """Carry out the pending tasks of ``plan``, updating each task's status in place.

    Single files that fail are marked ``failed`` and the run continues. A failed hard link
    stops the run (raising :class:`CopyError`) because every other link would fail too.
    """
    if not plan.enough_space:
        raise CopyError(
            f"not enough free space at {plan.dest}: need {plan.bytes_needed} bytes "
            f"(+ reserve), {plan.bytes_free} free"
        )
    pending = [t for t in plan.tasks if t.status in PENDING]
    if not pending:
        return
    _fs(plan.dest).mkdir(parents=True, exist_ok=True)
    marker = _fs(plan.dest) / OUTPUT_MARKER
    if not marker.exists():
        marker.write_text(MARKER_TEXT, encoding="utf-8")

    made: set[Path] = set()
    for i, task in enumerate(pending):
        assert task.destination is not None
        folder = task.destination.parent
        try:
            if folder not in made:
                _fs(folder).mkdir(parents=True, exist_ok=True)
                made.add(folder)
            _transfer(task)
        except OSError as exc:
            task.status, task.message = FAILED, str(exc)
            if task.mode == "hardlink":
                for rest in pending[i + 1 :]:
                    rest.status = ABORTED
                raise CopyError(
                    f"could not create a hard link for {task.source}: {exc}. The drive may not "
                    "support hard links (e.g. exFAT/FAT32); use --mode copy"
                ) from exc
        else:
            task.status = OVERWRITTEN if task.status == WOULD_OVERWRITE else DONE[task.mode]
        progress("copy", i + 1, len(pending))


def summarize(plan: CopyPlan) -> CopySummary:
    statuses = Counter(t.status for t in plan.tasks)
    by_capture: dict[tuple[str, str], list[FileTask]] = {}
    for t in plan.tasks:
        if t.kind != INCLUDE:
            by_capture.setdefault((t.kind, t.record_name), []).append(t)
    not_found = [n for (_, n), ts in by_capture.items() if ts[0].status == NOT_FOUND]
    ambiguous = [n for (_, n), ts in by_capture.items() if ts[0].status == AMBIGUOUS]
    groups = [ts for ts in by_capture.values() if ts[0].status not in {NOT_FOUND, AMBIGUOUS}]
    moving = PENDING | TRANSFERRED
    files = [t for t in plan.tasks if t.source is not None]
    return CopySummary(
        records=plan.records,
        extra_records=plan.extra_records,
        captures=len(groups),
        not_found=not_found,
        ambiguous=ambiguous,
        incomplete=[
            ts[0].record_name for ts in groups if any(t.status == MISSING_BAND for t in ts)
        ],
        statuses=statuses,
        groups_transferred=sum(any(t.status in moving for t in ts) for ts in groups),
        groups_skipped=sum(
            all(t.status in {SKIPPED, ALREADY, MISSING_BAND} for t in ts) for ts in groups
        ),
        include_files=sum(t.kind == INCLUDE for t in plan.tasks),
        bytes_transferred=sum(t.size for t in files if t.status in moving),
        bytes_total=sum(t.size for t in files),
    )


def write_copy_report(tasks: Iterable[FileTask], path: Path) -> None:
    with _fs(path).open("w", encoding=CSV_ENCODING, newline="") as f:
        writer = csv.writer(f)
        writer.writerow(REPORT_COLUMNS)
        for t in tasks:
            writer.writerow(
                [
                    t.kind,
                    t.record_name,
                    "" if t.band is None else t.band,
                    "" if t.source is None else os.fspath(t.source),
                    "" if t.destination is None else os.fspath(t.destination),
                    t.status,
                    t.size if t.source is not None else "",
                    t.message,
                ]
            )
