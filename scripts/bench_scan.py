"""Time the folder scan on a large synthetic tree (validation helper).

    uv run python scripts/bench_scan.py [--captures 3000] [--bands 7] [--other 200000]
                                        [--folder-size 1400] [--dir DIR] [--keep]

Builds a tree of empty files in a temporary folder: ``--captures`` x ``--bands`` band files
in camera-like folders of ``--folder-size`` files, plus ``--other`` unrelated files (logs,
processing outputs) in their own folders. Then times the scan step of ``index`` alone
(no ExifTool) and prints files per second. The tree is deleted afterwards unless ``--keep``.
"""

from __future__ import annotations

import argparse
import shutil
import tempfile
import time
from pathlib import Path

from uav_aoi_subset.core.discovery import discover_captures

OTHER_PER_FOLDER = 500
OTHER_NAMES = ("diag_{}.dat", "tile_{}.tif", "report_{}.xml", "IMG_{}_preview.jpg")


def build_tree(root: Path, captures: int, bands: int, other: int, folder_size: int) -> int:
    per_folder = max(1, folder_size // bands)
    for i in range(captures):
        folder = root / "Flights" / f"{i // (per_folder * 10):04d}SET" / f"{i // per_folder:03d}"
        if i % per_folder == 0:
            folder.mkdir(parents=True)
        for band in range(1, bands + 1):
            (folder / f"IMG_{i % 10000:04d}_{band}.tif").touch()
    for i in range(other):
        folder = root / "Processing" / f"part_{i // (OTHER_PER_FOLDER * 20):03d}"
        folder = folder / f"{i // OTHER_PER_FOLDER:05d}"
        if i % OTHER_PER_FOLDER == 0:
            folder.mkdir(parents=True)
        (folder / OTHER_NAMES[i % len(OTHER_NAMES)].format(i)).touch()
    return captures * bands + other


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--captures", type=int, default=3000)
    parser.add_argument("--bands", type=int, default=7)
    parser.add_argument("--other", type=int, default=200_000, help="unrelated files")
    parser.add_argument("--folder-size", type=int, default=1400, help="band files per folder")
    parser.add_argument("--dir", type=Path, help="where to build the tree (default: temp)")
    parser.add_argument("--keep", action="store_true", help="do not delete the tree")
    args = parser.parse_args()

    base = Path(tempfile.mkdtemp(prefix="uas-bench-", dir=args.dir))
    try:
        start = time.perf_counter()
        files = build_tree(base, args.captures, args.bands, args.other, args.folder_size)
        print(f"Tree:      {files:,} files in {time.perf_counter() - start:.1f} s ({base})")

        warnings: list[str] = []
        start = time.perf_counter()
        found = discover_captures(base, warnings=warnings)
        seconds = time.perf_counter() - start
        print(f"Scan:      {seconds:.2f} s, {files / seconds:,.0f} files/s")
        print(f"Captures:  {len(found):,} (expected {args.captures:,})")
        if warnings:
            print(f"Warnings:  {len(warnings)}")
        return 0 if len(found) == args.captures else 1
    finally:
        if not args.keep:
            shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
