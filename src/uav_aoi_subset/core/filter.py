"""Keep the index records whose position falls inside an AOI geometry.

Works on shapely geometries in WGS84 (x = longitude, y = latitude), not on files, so other
front ends (e.g. a QGIS plugin) can pass their own geometries.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import shapely
from pyproj import CRS, Transformer
from shapely.geometry.base import BaseGeometry

from uav_aoi_subset.core.discovery import sanitize_token
from uav_aoi_subset.core.index import IndexRecord
from uav_aoi_subset.core.progress import ProgressCallback, no_progress

WGS84 = CRS.from_epsg(4326)


@dataclass(frozen=True)
class FilterResult:
    inside: list[IndexRecord]
    no_position: list[IndexRecord]
    total: int


def utm_crs_for(geometry: BaseGeometry) -> CRS:
    """WGS84 / UTM zone of the geometry's centroid (EPSG 326xx north, 327xx south)."""
    centre = geometry.centroid
    zone = min(int((centre.x + 180) // 6) + 1, 60)
    return CRS.from_epsg((32600 if centre.y >= 0 else 32700) + zone)


def buffer_metres(geometry: BaseGeometry, metres: float) -> BaseGeometry:
    """Grow (positive) or shrink (negative) a WGS84 geometry by a distance in metres.

    The buffer is computed in the local UTM zone and the result converted back to WGS84.
    """
    if metres == 0:
        return geometry
    utm = utm_crs_for(geometry)
    to_utm = Transformer.from_crs(WGS84, utm, always_xy=True)
    to_wgs84 = Transformer.from_crs(utm, WGS84, always_xy=True)
    projected = shapely.transform(geometry, lambda xy: np.column_stack(to_utm.transform(*xy.T)))
    buffered = projected.buffer(metres)
    if buffered.is_empty:
        raise ValueError(f"a buffer of {metres:g} m leaves nothing of the area")
    return shapely.transform(buffered, lambda xy: np.column_stack(to_wgs84.transform(*xy.T)))


def filter_records(
    records: Iterable[IndexRecord],
    geometry: BaseGeometry,
    *,
    progress: ProgressCallback = no_progress,
) -> FilterResult:
    """Split records into those inside ``geometry`` (boundary included) and those without GPS.

    Records outside the area are dropped; the input order is kept.
    """
    records = list(records)
    located = [r for r in records if r.has_position]
    no_position = [r for r in records if not r.has_position]
    progress("filter", 0, len(located))
    if located:
        lon = np.array([r.longitude for r in located], dtype=float)
        lat = np.array([r.latitude for r in located], dtype=float)
        shapely.prepare(geometry)
        mask = shapely.intersects_xy(geometry, lon, lat)
        inside = [r for r, hit in zip(located, mask, strict=True) if hit]
    else:
        inside = []
    progress("filter", len(located), len(located))
    return FilterResult(inside=inside, no_position=no_position, total=len(records))


def default_subset_path(aoi_path: Path, today: dt.date | None = None) -> Path:
    """``<AOI folder>/<AOI name>_image_index_YYYYMMDD.csv`` next to the KML/KMZ."""
    aoi_path = Path(aoi_path)
    today = today or dt.date.today()
    name = sanitize_token(aoi_path.stem) or "aoi"
    return aoi_path.with_name(f"{name}_image_index_{today:%Y%m%d}.csv")
