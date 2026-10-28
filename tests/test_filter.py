import datetime as dt
import math
from pathlib import Path

import pytest
from shapely.geometry import MultiPolygon, Polygon
from synthetic import square

from uav_aoi_subset.core.filter import (
    buffer_metres,
    default_subset_path,
    filter_records,
    utm_crs_for,
)
from uav_aoi_subset.core.index import IndexRecord

AREA = Polygon(square(10.0, 50.0, 0.01))
METRES_PER_DEG_LAT = 111_320.0


def record(name: str, lon: float | None, lat: float | None) -> IndexRecord:
    return IndexRecord(
        record_name=name,
        complete=True,
        latitude=lat,
        longitude=lon,
        altitude=None,
        capture_time=None,
        bands_found=(1, 2, 3, 4, 5, 6, 7),
        missing_bands=(),
        relative_folder="A",
        image_base=name,
    )


def east_of(polygon: Polygon, metres: float) -> tuple[float, float]:
    """A point ``metres`` east of the polygon's east edge, at mid-height."""
    min_x, min_y, max_x, max_y = polygon.bounds
    lat = (min_y + max_y) / 2
    return max_x + metres / (METRES_PER_DEG_LAT * math.cos(math.radians(lat))), lat


def names(records):
    return [r.record_name for r in records]


def test_inside_outside_and_no_position():
    records = [
        record("in", 10.005, 50.005),
        record("out", 10.02, 50.005),
        record("nogps", None, None),
        record("in2", 10.001, 50.009),
    ]
    result = filter_records(records, AREA)
    assert names(result.inside) == ["in", "in2"]
    assert names(result.no_position) == ["nogps"]
    assert result.total == 4


def test_boundary_counts_as_inside():
    result = filter_records([record("edge", 10.01, 50.005), record("corner", 10.0, 50.0)], AREA)
    assert names(result.inside) == ["edge", "corner"]


def test_hole_is_excluded():
    holed = Polygon(square(10.0, 50.0, 0.01), [square(10.004, 50.004, 0.002)])
    result = filter_records([record("hole", 10.005, 50.005), record("ring", 10.001, 50.001)], holed)
    assert names(result.inside) == ["ring"]


def test_multipolygon_is_or():
    multi = MultiPolygon([AREA, Polygon(square(11.0, 50.0, 0.01))])
    records = [record("a", 10.005, 50.005), record("b", 11.005, 50.005), record("c", 10.5, 50.0)]
    assert names(filter_records(records, multi).inside) == ["a", "b"]


def test_empty_input():
    result = filter_records([], AREA)
    assert result.inside == [] and result.no_position == [] and result.total == 0


def test_progress_is_reported():
    calls = []
    filter_records([record("a", 10.005, 50.005)], AREA, progress=lambda *a: calls.append(a))
    assert calls[-1] == ("filter", 1, 1)


@pytest.mark.parametrize("lat", [50.0, -33.0])
def test_positive_buffer_includes_nearby_points(lat):
    area = Polygon(square(10.0, lat, 0.01))
    point = record("near", *east_of(area, 100))
    assert filter_records([point], area).inside == []
    assert filter_records([point], buffer_metres(area, 50)).inside == []
    assert names(filter_records([point], buffer_metres(area, 150)).inside) == ["near"]


def test_negative_buffer_shrinks():
    inside_edge = record("edge", *east_of(AREA, -20))
    assert names(filter_records([inside_edge], AREA).inside) == ["edge"]
    assert filter_records([inside_edge], buffer_metres(AREA, -50)).inside == []


def test_buffer_that_removes_everything():
    with pytest.raises(ValueError, match="leaves nothing"):
        buffer_metres(AREA, -5000)


def test_zero_buffer_is_identity():
    assert buffer_metres(AREA, 0) is AREA


def test_buffer_result_is_wgs84():
    grown = buffer_metres(AREA, 10)
    min_x, min_y, max_x, max_y = grown.bounds
    assert 9.99 < min_x < 10.0 and 10.01 < max_x < 10.02
    assert 49.99 < min_y < 50.0 and 50.01 < max_y < 50.02


@pytest.mark.parametrize(
    ("lon", "lat", "epsg"),
    [(10.0, 50.0, 32632), (29.0, 41.0, 32635), (-122.4, 48.5, 32610), (151.2, -33.9, 32756)],
)
def test_utm_zone(lon, lat, epsg):
    assert utm_crs_for(Polygon(square(lon, lat, 0.01))).to_epsg() == epsg


def test_default_subset_path():
    path = default_subset_path(Path("aoi") / "Kuzey Tarla.kmz", today=dt.date(2026, 10, 28))
    assert path == Path("aoi") / "Kuzey_Tarla_image_index_20261028.csv"
