"""Outline of the area covered by the capture positions (the ``footprint`` command).

The hull is computed in the local UTM zone, so the concave ``ratio`` and the area are in
metres, but its corners are the original WGS84 positions of the captures: a footprint written
to KML and used as an AOI keeps every capture inside (the boundary counts as inside).
Positions are capture centres; the imaged ground reaches further, which a ``buffer`` can
approximate.
"""

from __future__ import annotations

import html
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import MultiPoint, MultiPolygon, Polygon

from uav_aoi_subset.core.filter import WGS84, area_hectares, buffer_metres, to_crs, utm_crs_for
from uav_aoi_subset.core.index import IndexRecord
from uav_aoi_subset.core.kml import KmlPlacemark, KmlStyle, oriented

HULLS = ("convex", "concave")
DEFAULT_RATIO = 0.3

# A hull smaller than this (m²) means the positions lie on a line (or on one spot).
MIN_AREA_M2 = 1.0

# Group name for captures directly in the project root.
ROOT_GROUP = "(root)"

# Line colours (KML aabbggrr) for --per-folder, cycled; fills use the same colour at ~30 %.
PALETTE = [
    "ff00ffff",  # yellow
    "ffffff00",  # cyan
    "ffff00ff",  # magenta
    "ff0080ff",  # orange
    "ff00ff00",  # green
    "ff0000ff",  # red
    "ffff8000",  # blue
    "ffffffff",  # white
]
FILL_ALPHA = "4d"


class FootprintError(ValueError):
    """No footprint can be built from the given positions."""


def footprint(
    records: Iterable[IndexRecord],
    *,
    hull: str = "convex",
    ratio: float = DEFAULT_RATIO,
    buffer: float = 0.0,
) -> Polygon | MultiPolygon:
    """Hull of the positions of ``records``; records without a position are ignored.

    ``hull="concave"`` follows the shape of the flight more closely: ``ratio`` runs from
    0 (tightest) to 1 (same as convex). ``buffer`` grows (or shrinks) the result in metres; a
    negative buffer can split it into several polygons.
    """
    if hull not in HULLS:
        raise ValueError(f"hull must be one of {HULLS}")
    if not 0 < ratio <= 1:
        raise ValueError("ratio must be greater than 0 and at most 1")
    points = list(dict.fromkeys((r.longitude, r.latitude) for r in records if r.has_position))
    if len(points) < 3:
        raise FootprintError(
            f"at least 3 different capture positions are needed, found {len(points)}"
        )

    lonlat = np.array(points, dtype=float)
    utm = utm_crs_for(MultiPoint(lonlat))
    to_utm = Transformer.from_crs(WGS84, utm, always_xy=True)
    xy = np.column_stack(to_utm.transform(lonlat[:, 0], lonlat[:, 1]))
    original = {(float(x), float(y)): p for (x, y), p in zip(xy, points, strict=True)}

    cloud = MultiPoint(xy)
    if hull == "convex":
        shape = cloud.convex_hull
    else:
        shape = shapely.concave_hull(cloud, ratio=ratio, allow_holes=False)
    if not isinstance(shape, Polygon) or shape.area < MIN_AREA_M2:
        raise FootprintError(
            "the capture positions lie on one line (or on one spot), so they enclose no area"
        )

    # Hull corners are input points: map them back to the exact original degrees.
    corners = [original.get((x, y)) for x, y in shape.exterior.coords]
    if None not in corners and (polygon := Polygon(corners)).is_valid:
        result: Polygon | MultiPolygon = polygon
    else:
        result = to_crs(shape, utm, WGS84)

    if buffer:
        try:
            result = buffer_metres(result, buffer)
        except ValueError as exc:
            raise FootprintError(str(exc)) from exc
        if not isinstance(result, (Polygon, MultiPolygon)):
            raise FootprintError(f"a buffer of {buffer:g} m leaves no area")
    return oriented(result)


def group_by_folder(
    records: Iterable[IndexRecord], depth: int | None = None
) -> dict[str, list[IndexRecord]]:
    """Group records by their relative folder, cut to the first ``depth`` levels.

    ``depth=None`` uses the full folder. Folder names are not interpreted. Needs an index
    written by this tool: MATLAB CSVs have no ``RelativeFolder`` column.
    """
    if depth is not None and depth < 1:
        raise ValueError("depth must be at least 1")
    groups: dict[str, list[IndexRecord]] = {}
    for r in records:
        if not r.image_base:
            raise FootprintError(
                "grouping by folder needs an index written by uav-aoi-subset 'index' "
                f"(with a RelativeFolder column); {r.record_name} has none"
            )
        parts = PurePosixPath(r.relative_folder).parts if r.relative_folder else ()
        key = "/".join(parts[:depth]) or ROOT_GROUP
        groups.setdefault(key, []).append(r)
    return dict(sorted(groups.items()))


@dataclass(frozen=True)
class FootprintArea:
    name: str
    geometry: Polygon | MultiPolygon
    captures: int  # records with a position inside this group
    hectares: float
    folder: str | None = None


@dataclass
class FootprintResult:
    areas: list[FootprintArea]
    no_position: list[IndexRecord]
    total: int
    hull: str
    ratio: float
    buffer: float
    skipped_groups: list[tuple[str, str]] = field(default_factory=list)  # (folder, reason)

    def combined_hectares(self) -> float:
        """Area covered by all polygons together; overlaps are counted once."""
        return area_hectares(shapely.union_all([a.geometry for a in self.areas]))


def build_footprints(
    records: Iterable[IndexRecord],
    *,
    name: str = "Footprint",
    hull: str = "convex",
    ratio: float = DEFAULT_RATIO,
    buffer: float = 0.0,
    per_folder: bool = False,
    depth: int | None = None,
) -> FootprintResult:
    """One footprint for all records, or one per folder group (``per_folder``).

    Per folder, groups that enclose no area are skipped and listed; if none is left a
    :class:`FootprintError` is raised.
    """
    records = list(records)
    located = [r for r in records if r.has_position]
    result = FootprintResult(
        areas=[],
        no_position=[r for r in records if not r.has_position],
        total=len(records),
        hull=hull,
        ratio=ratio,
        buffer=buffer,
    )
    if not per_folder:
        geometry = footprint(located, hull=hull, ratio=ratio, buffer=buffer)
        result.areas.append(FootprintArea(name, geometry, len(located), area_hectares(geometry)))
        return result

    for folder, group in group_by_folder(records, depth).items():
        group = [r for r in group if r.has_position]
        try:
            geometry = footprint(group, hull=hull, ratio=ratio, buffer=buffer)
        except FootprintError as exc:
            result.skipped_groups.append((folder, str(exc)))
            continue
        result.areas.append(
            FootprintArea(folder, geometry, len(group), area_hectares(geometry), folder)
        )
    if not result.areas:
        raise FootprintError("no folder has enough capture positions for a footprint")
    return result


def _description(area: FootprintArea, result: FootprintResult, source_name: str) -> str:
    hull = result.hull + (f" (ratio {result.ratio:g})" if result.hull == "concave" else "")
    lines = []
    if area.folder is not None:
        lines.append(f"Folder: {area.folder}")
    lines += [f"Captures: {area.captures}", f"Area: {area.hectares:.2f} ha", f"Hull: {hull}"]
    if result.buffer:
        lines.append(f"Buffer: {result.buffer:g} m")
    if source_name:
        lines.append(f"Source: {source_name}")
    return "<br>".join(html.escape(line) for line in lines)


def footprint_placemarks(
    result: FootprintResult, source_name: str = ""
) -> tuple[list[KmlPlacemark], list[KmlStyle]]:
    """KML placemarks and styles for the areas, one colour per area (cycling the palette)."""
    styles = []
    placemarks = []
    for i, area in enumerate(result.areas):
        colour = PALETTE[i % len(PALETTE)]
        style = KmlStyle(f"footprint{i + 1}", colour, 3, FILL_ALPHA + colour[2:])
        styles.append(style)
        description = _description(area, result, source_name)
        placemarks.append(KmlPlacemark(area.name, area.geometry, description, style.id))
    return placemarks, styles


def default_footprint_path(index_csv: Path) -> Path:
    """``<csv folder>/<csv name>.kml`` next to the CSV, like the MATLAB tool."""
    return Path(index_csv).with_suffix(".kml")
