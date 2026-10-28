from xml.etree import ElementTree as ET

import pytest
from shapely.geometry import MultiPolygon, Polygon
from synthetic import square

from uav_aoi_subset.core.aoi import load_aoi
from uav_aoi_subset.core.kml import (
    KML_NAMESPACE,
    KmlPlacemark,
    KmlStyle,
    format_coordinate,
    kml_bytes,
    write_kml,
)

NS = {"k": KML_NAMESPACE}
SHELL = square(10.0, 50.0, 0.01)
HOLE = square(10.004, 50.004, 0.002)


def parse(data: bytes) -> ET.Element:
    return ET.fromstring(data)


def ring_points(element: ET.Element, path: str) -> list[tuple[float, float]]:
    text = element.find(path, NS).text
    return [tuple(map(float, t.split(",")[:2])) for t in text.split()]


def test_document_basics():
    data = kml_bytes(
        [KmlPlacemark("Saha Fotoğrafları & <test>", Polygon(SHELL), "a<br>b", "s1")],
        document_name="Kuzey Tarla",
        styles=[KmlStyle("s1")],
    )
    assert data.startswith(b'<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="')
    assert "Saha Fotoğrafları".encode() in data  # UTF-8, not character references
    root = parse(data)
    assert root.tag == f"{{{KML_NAMESPACE}}}kml"
    assert root.find("k:Document/k:name", NS).text == "Kuzey Tarla"
    placemark = root.find("k:Document/k:Placemark", NS)
    assert placemark.find("k:name", NS).text == "Saha Fotoğrafları & <test>"
    assert placemark.find("k:description", NS).text == "a<br>b"
    assert placemark.find("k:styleUrl", NS).text == "#s1"
    style = root.find("k:Document/k:Style", NS)
    assert style.get("id") == "s1"
    assert style.find("k:LineStyle/k:color", NS).text == "ff00ffff"
    assert style.find("k:PolyStyle/k:color", NS).text == "4d00ffff"
    coords = placemark.find(".//k:coordinates", NS).text.split()
    assert all(c.endswith(",0") for c in coords)


def test_rings_closed_outer_ccw_holes_cw():
    clockwise = Polygon(list(reversed(SHELL)), [HOLE])  # wrong way round on purpose
    root = parse(kml_bytes([KmlPlacemark("x", clockwise)], document_name="d"))
    polygon = root.find(".//k:Polygon", NS)
    outer = ring_points(polygon, "k:outerBoundaryIs/k:LinearRing/k:coordinates")
    inner = ring_points(polygon, "k:innerBoundaryIs/k:LinearRing/k:coordinates")
    assert outer[0] == outer[-1] and inner[0] == inner[-1]
    assert Polygon(outer).exterior.is_ccw
    assert not Polygon(inner).exterior.is_ccw


def test_multipolygon_and_folder():
    multi = MultiPolygon([Polygon(SHELL), Polygon(square(11.0, 50.0, 0.01))])
    data = kml_bytes([KmlPlacemark("m", multi)], document_name="d", folder_name="Flights")
    root = parse(data)
    folder = root.find("k:Document/k:Folder", NS)
    assert folder.find("k:name", NS).text == "Flights"
    assert len(folder.findall("k:Placemark/k:MultiGeometry/k:Polygon", NS)) == 2


@pytest.mark.parametrize(
    ("value", "text"),
    [(10.0, "10"), (-0.5, "-0.5"), (1e-5, "0.00001"), (12.345678912345678, "12.345678912345678")],
)
def test_format_coordinate(value, text):
    assert format_coordinate(value) == text
    assert float(text) == value


def test_round_trip_with_load_aoi_is_exact(tmp_path):
    # Awkward decimals on purpose: they must come back bit for bit.
    shell = [(10.123456789012345, 50.1), (10.2, 50.10000000000001), (10.15, 50.2 / 3 * 3)]
    original = Polygon(shell, [[(10.14, 50.12), (10.16, 50.12), (10.15, 50.13)]])
    path = tmp_path / "Saha Fotoğrafları.kml"
    write_kml(path, [KmlPlacemark("a", original)], document_name="d")
    aoi = load_aoi(path)
    assert aoi.polygon_count == 1 and aoi.hole_count == 1 and not aoi.warnings
    assert aoi.geometry.normalize().equals_exact(original.normalize(), tolerance=0)


def test_several_placemarks_read_back_as_several_polygons(tmp_path):
    path = tmp_path / "multi.kml"
    placemarks = [
        KmlPlacemark("a", Polygon(SHELL)),
        KmlPlacemark("b", Polygon(square(11.0, 50.0, 0.01))),
    ]
    write_kml(path, placemarks, document_name="d", folder_name="f")
    aoi = load_aoi(path)
    assert aoi.polygon_count == 2
    assert isinstance(aoi.geometry, MultiPolygon)


def test_write_never_overwrites_silently(tmp_path):
    path = tmp_path / "x.kml"
    path.write_text("keep")
    placemark = KmlPlacemark("a", Polygon(SHELL))
    with pytest.raises(FileExistsError):
        write_kml(path, [placemark], document_name="d")
    assert path.read_text() == "keep"
    write_kml(path, [placemark], document_name="d", overwrite=True)
    assert load_aoi(path).polygon_count == 1
