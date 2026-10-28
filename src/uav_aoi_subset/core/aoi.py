"""Load an area of interest (AOI) from a KML or KMZ file as a shapely geometry.

Only ``Polygon`` elements are areas: their outer boundary is the shell and every inner
boundary is a hole. Polygons are found at any depth (Document, Folder, Placemark,
MultiGeometry) and combined with OR. LineStrings, Points and loose LinearRings are ignored
and counted, so the caller can mention them.
"""

from __future__ import annotations

import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET

import shapely
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

# Non-polygon geometries that are skipped (and counted) when looking for areas.
_IGNORED_TAGS = ("LineString", "Point", "Track")


class AOIError(ValueError):
    """The AOI file could not be read or contains no usable polygon."""


@dataclass
class AOI:
    geometry: Polygon | MultiPolygon  # WGS84, x = longitude, y = latitude
    polygon_count: int  # KML Polygon elements used
    hole_count: int
    ignored_geometries: int = 0
    warnings: list[str] = field(default_factory=list)
    source: Path | None = None


def load_aoi(path: Path) -> AOI:
    """Read a ``.kml`` or ``.kmz`` file."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in {".kml", ".kmz"}:
        raise AOIError(f"{path}: unsupported AOI file type (expected .kml or .kmz)")
    try:
        if suffix == ".kmz":
            data, inner = _read_kmz(path)
            label = f"{path} ({inner})"
        else:
            data = path.read_bytes()
            label = str(path)
    except OSError as exc:
        raise AOIError(f"{path}: cannot read file: {exc}") from exc
    aoi = parse_kml(data, label=label)
    aoi.source = path
    return aoi


def _read_kmz(path: Path) -> tuple[bytes, str]:
    """Return the main KML of a KMZ: root ``doc.kml``, else the first root KML, else any."""
    try:
        with zipfile.ZipFile(path) as zf:
            names = sorted(n for n in zf.namelist() if n.lower().endswith(".kml"))
            if not names:
                raise AOIError(f"{path}: the KMZ contains no .kml file")
            root_level = [n for n in names if "/" not in n.strip("/")]
            doc = [n for n in root_level if PurePosixPath(n).name.lower() == "doc.kml"]
            chosen = (doc or root_level or names)[0]
            return zf.read(chosen), chosen
    except zipfile.BadZipFile as exc:
        raise AOIError(f"{path}: not a valid KMZ (zip) file: {exc}") from exc


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _iter_local(element: ET.Element, name: str) -> Iterator[ET.Element]:
    """Like ``element.iter(name)`` but ignoring the namespace (``iter`` has no ``{*}``)."""
    return (el for el in element.iter() if _local(el.tag) == name)


def _parse_coordinates(text: str | None) -> list[tuple[float, float]]:
    """``lon,lat[,alt]`` tuples separated by any whitespace; altitude is dropped."""
    points = []
    for token in (text or "").split():
        parts = token.split(",")
        if len(parts) < 2:
            raise ValueError(f"bad coordinate {token!r}")
        points.append((float(parts[0]), float(parts[1])))
    return points


def _ring(boundary: ET.Element | None) -> list[tuple[float, float]] | None:
    if boundary is None:
        return None
    coords = boundary.find("{*}LinearRing/{*}coordinates")
    if coords is None:
        coords = boundary.find(".//{*}coordinates")
    if coords is None:
        return None
    return _parse_coordinates(coords.text)


def _enough_points(points: list[tuple[float, float]]) -> bool:
    return len(set(points)) >= 3


def _polygon_parts(geom: BaseGeometry) -> list[Polygon]:
    if isinstance(geom, Polygon):
        return [geom] if not geom.is_empty else []
    if hasattr(geom, "geoms"):
        return [p for g in geom.geoms for p in _polygon_parts(g)]
    return []


def parse_kml(data: bytes, label: str = "KML") -> AOI:
    """Build the AOI from KML document bytes. ``label`` names the source in messages."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise AOIError(f"{label}: not a valid KML (XML) file: {exc}") from exc

    warnings: list[str] = []
    polygons: list[Polygon] = []
    used = 0
    holes = 0
    for n, element in enumerate(_iter_local(root, "Polygon"), start=1):
        name = f"polygon #{n}"
        try:
            shell = _ring(element.find("{*}outerBoundaryIs"))
            inner = [_ring(b) for b in element.findall("{*}innerBoundaryIs")]
        except ValueError as exc:
            warnings.append(f"{name} skipped: {exc}")
            continue
        if shell is None or not _enough_points(shell):
            warnings.append(f"{name} skipped: outer boundary has fewer than 3 distinct points")
            continue
        rings = []
        for k, ring in enumerate(inner, start=1):
            if ring is None or not _enough_points(ring):
                warnings.append(f"{name}: hole #{k} skipped (fewer than 3 distinct points)")
            else:
                rings.append(ring)
        polygon = Polygon(shell, rings)
        if not polygon.is_valid:
            warnings.append(
                f"{name} is not a valid polygon ({shapely.is_valid_reason(polygon)}); repaired"
            )
            parts = _polygon_parts(shapely.make_valid(polygon))
        else:
            parts = [polygon]
        if not parts:
            warnings.append(f"{name} skipped: it has no area")
            continue
        polygons.extend(parts)
        used += 1
        holes += len(rings)

    # LinearRings inside a Polygon are part of it; only count the loose ones.
    polygon_rings = {
        id(r) for p in _iter_local(root, "Polygon") for r in _iter_local(p, "LinearRing")
    }
    ignored = sum(
        1
        for el in root.iter()
        if _local(el.tag) in _IGNORED_TAGS
        or (_local(el.tag) == "LinearRing" and id(el) not in polygon_rings)
    )

    if not polygons:
        raise AOIError(
            f"{label}: no usable Polygon found. Draw the area with Google Earth's "
            "'Add Polygon' tool; paths (LineStrings) and placemarks (Points) are not areas."
        )
    geometry = shapely.union_all(polygons)
    if not isinstance(geometry, (Polygon, MultiPolygon)):
        geometry = MultiPolygon(_polygon_parts(geometry))
    return AOI(
        geometry=geometry,
        polygon_count=used,
        hole_count=holes,
        ignored_geometries=ignored,
        warnings=warnings,
    )
