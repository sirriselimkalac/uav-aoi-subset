"""Write polygons as a KML 2.2 document for Google Earth.

The output reads back with :func:`uav_aoi_subset.core.aoi.load_aoi` to the same geometry:
coordinates are written as the shortest decimal that round-trips exactly (``lon,lat,0``),
rings are closed, outer rings counter-clockwise and holes clockwise.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.polygon import orient

KML_NAMESPACE = "http://www.opengis.net/kml/2.2"


@dataclass(frozen=True)
class KmlStyle:
    """Line and fill of a polygon. Colours are KML ``aabbggrr`` hex strings."""

    id: str
    line_color: str = "ff00ffff"  # opaque yellow
    line_width: float = 3
    fill_color: str = "4d00ffff"  # yellow, about 30 % opaque


@dataclass(frozen=True)
class KmlPlacemark:
    name: str
    geometry: Polygon | MultiPolygon  # WGS84, x = longitude, y = latitude
    description: str = ""  # shown as HTML in Google Earth
    style_id: str = ""


def oriented(geometry: Polygon | MultiPolygon) -> Polygon | MultiPolygon:
    """Outer rings counter-clockwise, holes clockwise (the KML / OGC convention)."""
    if isinstance(geometry, Polygon):
        return orient(geometry, 1.0)
    return MultiPolygon([orient(p, 1.0) for p in geometry.geoms])


def format_coordinate(value: float) -> str:
    """Shortest decimal that reads back as exactly ``value``, never in exponent form."""
    return np.format_float_positional(float(value), unique=True, trim="-")


def _sub(parent: ET.Element, tag: str, text: str | None = None) -> ET.Element:
    element = ET.SubElement(parent, tag)
    if text is not None:
        element.text = text
    return element


def _ring(parent: ET.Element, boundary: str, coords: Iterable[tuple[float, ...]]) -> None:
    ring = _sub(_sub(parent, boundary), "LinearRing")
    text = " ".join(f"{format_coordinate(x)},{format_coordinate(y)},0" for x, y, *_ in coords)
    _sub(ring, "coordinates", text)


def _polygon(parent: ET.Element, polygon: Polygon) -> None:
    element = _sub(parent, "Polygon")
    _sub(element, "tessellate", "1")
    # shapely rings are closed: the first point is repeated at the end.
    _ring(element, "outerBoundaryIs", polygon.exterior.coords)
    for hole in polygon.interiors:
        _ring(element, "innerBoundaryIs", hole.coords)


def _style(parent: ET.Element, style: KmlStyle) -> None:
    element = _sub(parent, "Style")
    element.set("id", style.id)
    line = _sub(element, "LineStyle")
    _sub(line, "color", style.line_color)
    _sub(line, "width", f"{style.line_width:g}")
    _sub(_sub(element, "PolyStyle"), "color", style.fill_color)


def kml_bytes(
    placemarks: Iterable[KmlPlacemark],
    *,
    document_name: str,
    styles: Iterable[KmlStyle] = (),
    folder_name: str | None = None,
) -> bytes:
    """The KML document as UTF-8 bytes. With ``folder_name`` the placemarks go in a Folder."""
    root = ET.Element("kml", {"xmlns": KML_NAMESPACE})
    document = _sub(root, "Document")
    _sub(document, "name", document_name)
    for style in styles:
        _style(document, style)
    container = document
    if folder_name is not None:
        container = _sub(document, "Folder")
        _sub(container, "name", folder_name)
    for placemark in placemarks:
        element = _sub(container, "Placemark")
        _sub(element, "name", placemark.name)
        if placemark.description:
            _sub(element, "description", placemark.description)
        if placemark.style_id:
            _sub(element, "styleUrl", f"#{placemark.style_id}")
        geometry = oriented(placemark.geometry)
        if isinstance(geometry, Polygon):
            _polygon(element, geometry)
        else:
            multi = _sub(element, "MultiGeometry")
            for part in geometry.geoms:
                _polygon(multi, part)
    ET.indent(root)
    body = ET.tostring(root, encoding="unicode")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n").encode("utf-8")


def write_kml(
    path: Path,
    placemarks: Iterable[KmlPlacemark],
    *,
    document_name: str,
    styles: Iterable[KmlStyle] = (),
    folder_name: str | None = None,
    overwrite: bool = False,
) -> None:
    """Write the KML file. Raises :class:`FileExistsError` if it exists, unless ``overwrite``."""
    data = kml_bytes(
        placemarks, document_name=document_name, styles=styles, folder_name=folder_name
    )
    with Path(path).open("wb" if overwrite else "xb") as f:
        f.write(data)
