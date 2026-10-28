"""Compare uav-aoi-subset outputs with those of the old MATLAB scripts (validation helper).

    uv run python scripts/compare_outputs.py csv  OURS.csv    MATLAB.csv  [--tol-m 0.05]
    uv run python scripts/compare_outputs.py tree OUR_FOLDER  MATLAB_FOLDER

``csv`` compares two index or subset CSVs: record names, the Complete flag and positions
(difference in metres). ``tree`` compares two copy output folders: relative file paths and
sizes, ignoring this tool's marker file. Exit code 0 means no differences.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from uav_aoi_subset.core.discovery import OUTPUT_MARKER
from uav_aoi_subset.core.index import read_index_csv

SHOW = 20
METRES_PER_DEGREE = 111_320.0


def _show(title: str, items: list[str]) -> None:
    if not items:
        return
    print(f"{title}: {len(items)}")
    for item in items[:SHOW]:
        print(f"  {item}")
    if len(items) > SHOW:
        print(f"  ... and {len(items) - SHOW} more")


def compare_csv(ours: Path, theirs: Path, tol_m: float) -> int:
    a = {r.record_name: r for r in read_index_csv(ours)}
    b = {r.record_name: r for r in read_index_csv(theirs)}
    print(f"Records: {len(a)} (ours) / {len(b)} (MATLAB)")
    only_a = sorted(a.keys() - b.keys())
    only_b = sorted(b.keys() - a.keys())
    common = sorted(a.keys() & b.keys())
    complete = [n for n in common if a[n].complete != b[n].complete]
    position = [n for n in common if a[n].has_position != b[n].has_position]
    worst, far = 0.0, []
    for n in common:
        ra, rb = a[n], b[n]
        if not (ra.has_position and rb.has_position):
            continue
        dy = (ra.latitude - rb.latitude) * METRES_PER_DEGREE
        dx = (ra.longitude - rb.longitude) * METRES_PER_DEGREE * math.cos(math.radians(ra.latitude))
        d = math.hypot(dx, dy)
        worst = max(worst, d)
        if d > tol_m:
            far.append(f"{n}  ({d:.3f} m)")
    _show("Only in ours", only_a)
    _show("Only in MATLAB", only_b)
    _show("Complete flag differs", complete)
    _show("GPS present in one only", position)
    _show(f"Position differs by more than {tol_m} m", far)
    print(f"Largest position difference: {worst:.4f} m")
    differences = only_a or only_b or complete or position or far
    print("RESULT: " + ("DIFFERENT" if differences else "SAME"))
    return 1 if differences else 0


def _files(root: Path) -> dict[str, int]:
    return {
        p.relative_to(root).as_posix(): p.stat().st_size
        for p in root.rglob("*")
        if p.is_file() and p.name != OUTPUT_MARKER
    }


def compare_tree(ours: Path, theirs: Path) -> int:
    a, b = _files(ours), _files(theirs)
    print(f"Files: {len(a)} (ours) / {len(b)} (MATLAB)")
    only_a = sorted(a.keys() - b.keys())
    only_b = sorted(b.keys() - a.keys())
    size = sorted(n for n in a.keys() & b.keys() if a[n] != b[n])
    _show("Only in ours", only_a)
    _show("Only in MATLAB", only_b)
    _show("Size differs", size)
    differences = only_a or only_b or size
    print("RESULT: " + ("DIFFERENT" if differences else "SAME"))
    return 1 if differences else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="what", required=True)
    p_csv = sub.add_parser("csv", help="Compare two index/subset CSVs.")
    p_csv.add_argument("ours", type=Path)
    p_csv.add_argument("matlab", type=Path)
    p_csv.add_argument("--tol-m", type=float, default=0.05, help="Position tolerance (m).")
    p_tree = sub.add_parser("tree", help="Compare two copy output folders.")
    p_tree.add_argument("ours", type=Path)
    p_tree.add_argument("matlab", type=Path)
    args = parser.parse_args(argv)
    for path in (args.ours, args.matlab):
        if not path.exists():
            print(f"error: not found: {path}", file=sys.stderr)
            return 2
    if args.what == "csv":
        return compare_csv(args.ours, args.matlab, args.tol_m)
    return compare_tree(args.ours, args.matlab)


if __name__ == "__main__":
    sys.exit(main())
