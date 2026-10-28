import zipfile

import pytest
from shapely.geometry import MultiPolygon, Point, Polygon
from synthetic import kml_document, polygon_kml, ring_text, square, write_kmz

from uav_aoi_subset.core.aoi import AOIError, load_aoi, parse_kml

SQUARE = square(10.0, 50.0, 0.01)


def _parse(*geometries: str, **kwargs):
    return parse_kml(kml_document(*geometries, **kwargs).encode("utf-8"))


def test_single_polygon():
    aoi = _parse(polygon_kml(SQUARE))
    assert isinstance(aoi.geometry, Polygon)
    assert aoi.polygon_count == 1
    assert aoi.hole_count == 0
    assert aoi.warnings == []
    assert aoi.geometry.equals(Polygon(SQUARE))


@pytest.mark.parametrize(
    "namespace", [None, "http://www.opengis.net/kml/2.2", "http://earth.google.com/kml/2.1"]
)
def test_namespaces(namespace):
    aoi = _parse(polygon_kml(SQUARE), namespace=namespace)
    assert aoi.geometry.equals(Polygon(SQUARE))


def test_coordinates_without_altitude_and_odd_whitespace():
    text = ring_text(SQUARE, alt=None).replace(" ", "\n\t   ")
    geometry = (
        "<Polygon><outerBoundaryIs><LinearRing><coordinates>\n"
        f"   {text}\n   </coordinates></LinearRing></outerBoundaryIs></Polygon>"
    )
    assert _parse(geometry).geometry.equals(Polygon(SQUARE))


def test_polygon_with_hole():
    hole = square(10.004, 50.004, 0.002)
    aoi = _parse(polygon_kml(SQUARE, [hole]))
    assert aoi.hole_count == 1
    assert not aoi.geometry.covers(Point(10.005, 50.005))
    assert aoi.geometry.covers(Point(10.001, 50.001))


def test_multigeometry():
    other = square(10.1, 50.0, 0.01)
    multi = f"<MultiGeometry>{polygon_kml(SQUARE)}{polygon_kml(other)}</MultiGeometry>"
    aoi = _parse(multi)
    assert aoi.polygon_count == 2
    assert isinstance(aoi.geometry, MultiPolygon)


def test_several_placemarks_are_combined():
    overlapping = square(10.005, 50.0, 0.01)
    aoi = _parse(polygon_kml(SQUARE), polygon_kml(overlapping))
    assert aoi.polygon_count == 2
    assert isinstance(aoi.geometry, Polygon)  # union of overlapping squares
    assert aoi.geometry.covers(Point(10.012, 50.005))


def test_lines_and_points_are_ignored():
    line = f"<LineString><coordinates>{ring_text(SQUARE)}</coordinates></LineString>"
    point = "<Point><coordinates>10.5,50.5,0</coordinates></Point>"
    aoi = _parse(polygon_kml(SQUARE), line, point)
    assert aoi.polygon_count == 1
    assert aoi.ignored_geometries == 2
    assert aoi.geometry.equals(Polygon(SQUARE))


def test_no_polygon():
    line = f"<LineString><coordinates>{ring_text(SQUARE)}</coordinates></LineString>"
    with pytest.raises(AOIError, match="no usable Polygon"):
        _parse(line)


def test_degenerate_polygon_is_skipped():
    degenerate = polygon_kml([(10.0, 50.0), (10.1, 50.0)])
    aoi = _parse(polygon_kml(SQUARE), degenerate)
    assert aoi.polygon_count == 1
    assert any("fewer than 3" in w for w in aoi.warnings)


def test_self_intersecting_polygon_is_repaired():
    bowtie = [(10.0, 50.0), (10.01, 50.01), (10.01, 50.0), (10.0, 50.01)]
    aoi = _parse(polygon_kml(bowtie))
    assert aoi.geometry.is_valid
    assert aoi.geometry.area > 0
    assert any("repaired" in w for w in aoi.warnings)


def test_bad_xml():
    with pytest.raises(AOIError, match="not a valid KML"):
        parse_kml(b"<kml><Document>")


def test_bad_coordinate_is_skipped():
    geometry = (
        "<Polygon><outerBoundaryIs><LinearRing><coordinates>10.0 50.0 x"
        "</coordinates></LinearRing></outerBoundaryIs></Polygon>"
    )
    with pytest.raises(AOIError):
        _parse(geometry)


def test_load_kml_with_turkish_name(tmp_path):
    path = tmp_path / "Ağaçlık Alan.kml"
    path.write_text(kml_document(polygon_kml(SQUARE)), encoding="utf-8")
    aoi = load_aoi(path)
    assert aoi.source == path
    assert aoi.geometry.equals(Polygon(SQUARE))


def test_load_kmz_prefers_doc_kml(tmp_path):
    other = square(20.0, 10.0, 0.01)
    path = tmp_path / "area.kmz"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("a.kml", kml_document(polygon_kml(other)))
        zf.writestr("doc.kml", kml_document(polygon_kml(SQUARE)))
    assert load_aoi(path).geometry.equals(Polygon(SQUARE))


def test_load_kmz_with_other_kml_name(tmp_path):
    path = write_kmz(tmp_path / "area.kmz", kml_document(polygon_kml(SQUARE)), "files/x.kml")
    assert load_aoi(path).geometry.equals(Polygon(SQUARE))


def test_kmz_without_kml(tmp_path):
    path = tmp_path / "area.kmz"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("image.png", b"png")
    with pytest.raises(AOIError, match="no .kml"):
        load_aoi(path)


def test_bad_kmz(tmp_path):
    path = tmp_path / "area.kmz"
    path.write_bytes(b"not a zip")
    with pytest.raises(AOIError, match="not a valid KMZ"):
        load_aoi(path)


def test_unsupported_extension(tmp_path):
    path = tmp_path / "area.shp"
    path.write_bytes(b"")
    with pytest.raises(AOIError, match="unsupported"):
        load_aoi(path)


def test_missing_file(tmp_path):
    with pytest.raises(AOIError, match="cannot read"):
        load_aoi(tmp_path / "missing.kml")
