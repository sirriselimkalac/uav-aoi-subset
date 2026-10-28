import datetime as dt
from pathlib import Path

import pytest
from synthetic import ALTUM_LAYOUT, make_altum_tree, write_capture

from uav_aoi_subset.core.exif import GpsFix
from uav_aoi_subset.core.index import (
    INDEX_COLUMNS,
    RecordNameCollisionError,
    build_index,
    default_index_path,
    read_index_csv,
    write_index_csv,
)


class FakeReader:
    """Gives every file a position derived from its path; records what was asked."""

    def __init__(self, unreadable=()):
        self.requested: list[Path] = []
        self.unreadable = set(unreadable)

    def read_gps(self, paths, progress=lambda *a: None):
        self.requested.extend(paths)
        return {
            p: GpsFix(39.0 + i / 1000, 32.0 + i / 1000, 900.0, "2026:07:30 09:00:00")
            for i, p in enumerate(paths)
            if p.name not in self.unreadable
        }


def test_altum_tree_index(tmp_path):
    make_altum_tree(tmp_path)
    reader = FakeReader()
    records = build_index(tmp_path, reader)

    assert len(records) == sum(len(b) for b in ALTUM_LAYOUT.values())
    assert all(r.complete and r.has_position for r in records)
    assert all(p.name.endswith("_1.tif") for p in reader.requested)
    assert len(reader.requested) == len(records)
    assert len({r.record_name for r in records}) == len(records)


def test_incomplete_and_missing_band1(tmp_path):
    write_capture(tmp_path / "000", "IMG_0001", range(1, 8))
    write_capture(tmp_path / "000", "IMG_0002", [1, 2, 3, 5, 6, 7])
    write_capture(tmp_path / "000", "IMG_0003", range(2, 8))
    r1, r2, r3 = build_index(tmp_path, FakeReader())

    assert r1.complete and r1.missing_bands == ()
    assert not r2.complete and r2.missing_bands == (4,) and r2.has_position
    assert not r3.complete and r3.missing_bands == (1,) and not r3.has_position


def test_unreadable_gps_gives_empty_position(tmp_path):
    write_capture(tmp_path, "IMG_0001", range(1, 8))
    (record,) = build_index(tmp_path, FakeReader(unreadable={"IMG_0001_1.tif"}))
    assert record.complete
    assert record.latitude is None and record.longitude is None


def test_bands_parameter(tmp_path):
    write_capture(tmp_path, "IMG_0001", range(1, 6))
    (rededge,) = build_index(tmp_path, FakeReader(), bands=5)
    (altum,) = build_index(tmp_path, FakeReader(), bands=7)
    assert rededge.complete
    assert not altum.complete and altum.missing_bands == (6, 7)
    with pytest.raises(ValueError):
        build_index(tmp_path, FakeReader(), bands=0)


def test_record_name_collision(tmp_path):
    write_capture(tmp_path / "Part 1", "IMG_0001", [1])
    write_capture(tmp_path / "Part_1", "IMG_0001", [1])
    with pytest.raises(RecordNameCollisionError, match="Part 1, Part_1"):
        build_index(tmp_path, FakeReader())


def test_exclude_is_passed_through(tmp_path):
    make_altum_tree(tmp_path / "Saha")
    write_capture(tmp_path / "Kalibrasyon_Fotograflari", "IMG_0000", range(1, 8))
    records = build_index(tmp_path, FakeReader(), exclude=["kalibrasyon*"])
    assert not any("Kalibrasyon" in r.record_name for r in records)


def test_csv_round_trip_with_unicode(tmp_path):
    make_altum_tree(tmp_path)
    write_capture(tmp_path / "Saha Fotoğrafları" / "eksik", "IMG_0009", [2, 3])
    records = build_index(tmp_path, FakeReader())
    out = tmp_path / "index.csv"
    write_index_csv(records, out)

    assert read_index_csv(out) == records
    text = out.read_text(encoding="utf-8-sig")
    header, first = text.splitlines()[:2]
    assert header.split(",") == INDEX_COLUMNS
    assert first.startswith("Saha_Fotoğrafları_Part1_0000SET_000_IMG_0000,1,39.0,32.0,")
    assert out.read_bytes().startswith(b"\xef\xbb\xbf")


def test_read_matlab_style_csv(tmp_path):
    path = tmp_path / "matlab.csv"
    path.write_text(
        "RecordName,Complete,GPSLatitude,GPSLongitude\nA_IMG_0001,1,39.5,32.5\nA_IMG_0002,0,NaN,NaN\n",
        encoding="utf-8",
    )
    r1, r2 = read_index_csv(path)
    assert r1.complete and r1.latitude == 39.5
    assert not r2.complete and not r2.has_position


def test_read_rejects_other_csv(tmp_path):
    path = tmp_path / "other.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing columns"):
        read_index_csv(path)


def test_default_index_path(tmp_path):
    root = tmp_path / "Saha Fotoğrafları"
    root.mkdir()
    path = default_index_path(root, today=dt.date(2026, 7, 30))
    assert path == root / "Saha_Fotoğrafları_image_index_20260730.csv"
