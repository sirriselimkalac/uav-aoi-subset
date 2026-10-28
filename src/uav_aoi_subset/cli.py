"""Command-line interface. Thin wrapper around ``uav_aoi_subset.core``."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from uav_aoi_subset import __version__

DEFAULT_BANDS = 7


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
    p_index.add_argument("--pattern", help="Regex for band file names.")
    p_index.add_argument("--out", type=Path, metavar="CSV", help="Output CSV path.")

    p_filter = sub.add_parser("filter", help="Keep index rows that fall inside an AOI.")
    p_filter.add_argument("index_csv", type=Path, metavar="INDEX_CSV")
    p_filter.add_argument(
        "--aoi", type=Path, required=True, metavar="AREA", help="AOI polygon file (.kml/.kmz)."
    )
    p_filter.add_argument("--buffer", type=float, metavar="METRES", help="Buffer the AOI.")
    p_filter.add_argument("--out", type=Path, metavar="CSV", help="Output CSV path.")

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


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    print(f"uav-aoi-subset {args.command}: not implemented yet.", file=sys.stderr)
    return 2
