import math
from pathlib import Path

import numpy as np
import pytest
import shapely
from pyproj import Geod
from shapely.geometry import Polygon

from uav_aoi_subset.core.aoi import load_aoi
from uav_aoi_subset.core.filter import WGS84, filter_records, to_crs, utm_crs_for
from uav_aoi_subset.core.footprint import (
    PALETTE,
    ROOT_GROUP,
    FootprintError,
    build_footprints,
    default_footprint_path,
    footprint,
    footprint_placemarks,
    group_by_folder,
)
from uav_aoi_subset.core.index import IndexRecord
from uav_aoi_subset.core.kml import write_kml

STEP = 0.0001  # degrees, about 7 m east-west and 11 m north-south at 50° N
GEOD = Geod(ellps="WGS84")


def record(
    name: str, lon: float | None, lat: float | None, folder: str = "A", base: str = "IMG_0000"
) -> IndexRecord:
    return IndexRecord(
        record_name=name,
        complete=True,
        latitude=lat,
        longitude=lon,
        altitude=None,
        capture_time=None,
        bands_found=(1, 2, 3, 4, 5, 6, 7),
        missing_bands=(),
        relative_folder=folder,
        image_base=base,
    )


def grid(
    nx: int, ny: int, lon0: float = 10.0, lat0: float = 50.0, folder: str = "A", skip=None
) -> list[IndexRecord]:
    """Capture positions on a regular grid; ``skip(i, j)`` leaves points out."""
    return [
        record(f"{folder}_{i}_{j}", lon0 + i * STEP, lat0 + j * STEP, folder)
        for i in range(nx)
        for j in range(ny)
        if not (skip and skip(i, j))
    ]


def l_shape() -> list[IndexRecord]:
    # 11 x 11 grid without its north-east 7 x 7 block.
    return grid(11, 11, skip=lambda i, j: i >= 4 and j >= 4)


def geodesic_ha(geometry) -> float:
    return abs(GEOD.geometry_area_perimeter(geometry)[0]) / 10_000


def positions(records):
    return {(r.longitude, r.latitude) for r in records if r.has_position}


def test_convex_grid():
    records = grid(11, 11)
    polygon = footprint(records)
    assert isinstance(polygon, Polygon) and polygon.exterior.is_ccw
    corners = set(polygon.exterior.coords)
    # Corners are the original positions, not re-projected approximations.
    assert corners <= positions(records)
    assert {(10.0, 50.0), (10.0 + 10 * STEP, 50.0 + 10 * STEP)} <= corners
    expected = 10 * STEP * 111_320 * 10 * STEP * 111_320 * math.cos(math.radians(50.0005))
    assert geodesic_ha(polygon) == pytest.approx(expected / 10_000, rel=0.01)


def test_concave_follows_an_l_shaped_flight():
    records = l_shape()
    convex = footprint(records)
    concave = footprint(records, hull="concave")
    assert concave.area < 0.8 * convex.area
    assert concave.exterior.is_ccw and concave.is_valid
    lon, lat = np.array(sorted(positions(records))).T
    assert shapely.intersects_xy(concave, lon, lat).all()
    # ratio 1 is the convex hull.
    assert footprint(records, hull="concave", ratio=1).area == pytest.approx(convex.area)


def test_buffer_in_metres():
    polygon = footprint(grid(11, 11))
    buffered = footprint(grid(11, 11), buffer=10)
    utm = utm_crs_for(polygon)
    base, grown = to_crs(polygon, WGS84, utm), to_crs(buffered, WGS84, utm)
    expected = base.area + base.length * 10 + math.pi * 10**2
    assert grown.area == pytest.approx(expected, rel=0.01)
    assert buffered.exterior.is_ccw


def test_buffer_too_negative():
    with pytest.raises(FootprintError, match="leaves nothing"):
        footprint(grid(11, 11), buffer=-1000)


def test_records_without_position_are_ignored():
    records = grid(5, 5)
    with_missing = [*records, record("nogps", None, None), record("nolat", 10.5, None)]
    assert footprint(with_missing).equals_exact(footprint(records), tolerance=0)


@pytest.mark.parametrize(
    ("points", "message"),
    [
        ([(10.0, 50.0), (10.001, 50.0)], "found 2"),
        ([(10.0, 50.0), (10.001, 50.0), (10.0, 50.0), (10.001, 50.0)], "found 2"),
        ([(10.0 + k * STEP, 50.0 + 2 * k * STEP) for k in range(6)], "one line"),
        ([], "found 0"),
    ],
)
def test_not_enough_area(points, message):
    records = [record(f"r{k}", lon, lat) for k, (lon, lat) in enumerate(points)]
    with pytest.raises(FootprintError, match=message):
        footprint(records)


def test_argument_validation():
    with pytest.raises(ValueError, match="hull"):
        footprint(grid(3, 3), hull="alpha")
    with pytest.raises(ValueError, match="ratio"):
        footprint(grid(3, 3), hull="concave", ratio=0)


def test_group_by_folder():
    records = [
        record("a", 10.0, 50.0, "Part1/0000SET/000"),
        record("b", 10.0, 50.0, "Part1/0000SET/001"),
        record("c", 10.0, 50.0, "Part1/0001SET/000"),
        record("d", 10.0, 50.0, ""),
    ]

    def names(groups):
        return {k: [r.record_name for r in v] for k, v in groups.items()}

    assert names(group_by_folder(records)) == {
        ROOT_GROUP: ["d"],
        "Part1/0000SET/000": ["a"],
        "Part1/0000SET/001": ["b"],
        "Part1/0001SET/000": ["c"],
    }
    assert names(group_by_folder(records, 2)) == {
        ROOT_GROUP: ["d"],
        "Part1/0000SET": ["a", "b"],
        "Part1/0001SET": ["c"],
    }
    assert list(group_by_folder(records, 1)) == [ROOT_GROUP, "Part1"]
    with pytest.raises(ValueError, match="depth"):
        group_by_folder(records, 0)


def test_group_by_folder_needs_relative_folders():
    matlab = record("Part1_0000SET_000_IMG_0000", 10.0, 50.0, folder="", base="")
    with pytest.raises(FootprintError, match="RelativeFolder"):
        group_by_folder([matlab])


def test_build_footprints_per_folder():
    records = [
        *grid(5, 5, folder="Part1/0000SET/000"),
        *grid(5, 5, lon0=10.01, folder="Part1/0001SET/000"),
        record("lonely1", 10.02, 50.0, "Part2/0000SET/000"),
        record("lonely2", 10.03, 50.0, "Part2/0000SET/000"),
        record("nogps", None, None, "Part1/0000SET/000"),
    ]
    result = build_footprints(records, per_folder=True, depth=2)
    assert [a.name for a in result.areas] == ["Part1/0000SET", "Part1/0001SET"]
    assert [a.captures for a in result.areas] == [25, 25]
    assert [f for f, _ in result.skipped_groups] == ["Part2/0000SET"]
    assert result.total == 53 and len(result.no_position) == 1
    assert all(a.hectares > 0 for a in result.areas)
    assert result.combined_hectares() == pytest.approx(sum(a.hectares for a in result.areas))
    overlapping = build_footprints(grid(5, 5, folder="X") + grid(5, 5, folder="Y"), per_folder=True)
    assert overlapping.combined_hectares() == pytest.approx(overlapping.areas[0].hectares)

    placemarks, styles = footprint_placemarks(result, "camp_image_index.csv")
    assert [s.line_color for s in styles] == PALETTE[:2]
    assert styles[0].fill_color == "4d" + PALETTE[0][2:]
    text = placemarks[0].description
    assert "Folder: Part1/0000SET" in text and "Captures: 25" in text
    assert " ha" in text and "Source: camp_image_index.csv" in text


def test_build_footprints_all_groups_too_small():
    records = [record("a", 10.0, 50.0, "X"), record("b", 10.1, 50.0, "Y")]
    with pytest.raises(FootprintError, match="no folder"):
        build_footprints(records, per_folder=True)


def test_description_of_a_whole_footprint():
    result = build_footprints(l_shape(), name="camp", hull="concave", ratio=0.2, buffer=5)
    (area,) = result.areas
    assert area.name == "camp" and area.folder is None and area.captures == 72
    (placemark,), _ = footprint_placemarks(result, "a&b.csv")
    assert "Hull: concave (ratio 0.2)" in placemark.description
    assert "Buffer: 5 m" in placemark.description
    assert "a&amp;b.csv" in placemark.description  # HTML-escaped for Google Earth


@pytest.mark.parametrize("hull", ["convex", "concave"])
def test_footprint_kml_as_aoi_keeps_every_capture(tmp_path, hull):
    records = l_shape()
    result = build_footprints(records, hull=hull)
    placemarks, styles = footprint_placemarks(result)
    path = tmp_path / "footprint.kml"
    write_kml(path, placemarks, document_name="camp", styles=styles)
    aoi = load_aoi(path)
    assert aoi.geometry.normalize().equals_exact(result.areas[0].geometry.normalize(), 0)
    assert len(filter_records(records, aoi.geometry).inside) == len(records)


def test_default_footprint_path():
    path = Path("x") / "camp_image_index_20261028.csv"
    assert default_footprint_path(path) == Path("x") / "camp_image_index_20261028.kml"
