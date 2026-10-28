import pytest
from synthetic import write_capture, write_gps

from uav_aoi_subset.core import exif
from uav_aoi_subset.core.exif import (
    ExifToolNotFoundError,
    ExifToolReader,
    GpsFix,
    find_exiftool,
    parse_exiftool_record,
)


def test_parse_signed_and_unsigned_records():
    unsigned = {
        "GPSLatitude": 39.5,
        "GPSLatitudeRef": "S",
        "GPSLongitude": 32.25,
        "GPSLongitudeRef": "W",
        "GPSAltitude": 12.0,
        "GPSAltitudeRef": 1,
        "DateTimeOriginal": "2026:07:30 09:00:00",
    }
    assert parse_exiftool_record(unsigned) == GpsFix(-39.5, -32.25, -12.0, "2026:07:30 09:00:00")
    signed = {"GPSLatitude": -39.5, "GPSLatitudeRef": "S", "GPSLongitude": 32.25}
    assert parse_exiftool_record(signed) == GpsFix(-39.5, 32.25, None, None)


def test_parse_missing_and_invalid_values():
    assert parse_exiftool_record({}) == GpsFix(None, None, None, None)
    fix = parse_exiftool_record({"GPSLatitude": "48 deg 30' N", "GPSLongitude": 999.0})
    assert fix == GpsFix(None, None, None, None)
    assert not fix.has_position


def test_find_exiftool_missing(monkeypatch):
    monkeypatch.setattr(exif.shutil, "which", lambda name: None)
    with pytest.raises(ExifToolNotFoundError, match="brew install exiftool"):
        find_exiftool()


def test_find_exiftool_explicit_path(tmp_path):
    with pytest.raises(ExifToolNotFoundError, match="not found at"):
        find_exiftool(tmp_path / "nope" / "exiftool.exe")
    fake = tmp_path / "exiftool.exe"
    fake.write_bytes(b"")
    assert find_exiftool(fake) == fake


def test_chunk_size_must_be_positive():
    with pytest.raises(ValueError):
        ExifToolReader(chunk_size=0)


@pytest.mark.requires_exiftool
def test_reads_gps_in_chunks_with_unicode_paths(tmp_path):
    folder = tmp_path / "Saha Fotoğrafları" / "Part1" / "0000SET" / "000"
    coords = [(39.9, 32.8), (-33.86, 151.2), (40.7, -74.0), (-22.9, -43.2), (0.5, 0.5)]
    paths = []
    for i, (lat, lon) in enumerate(coords):
        (path,) = write_capture(folder, f"IMG_{i:04d}", [1])
        write_gps(path, lat, lon, alt=100.0 + i)
        paths.append(path)

    calls = []
    reader = ExifToolReader(chunk_size=2)
    fixes = reader.read_gps(paths, progress=lambda *a: calls.append(a))

    assert set(fixes) == set(paths)
    for path, (lat, lon) in zip(paths, coords, strict=True):
        assert fixes[path].latitude == pytest.approx(lat, abs=1e-6)
        assert fixes[path].longitude == pytest.approx(lon, abs=1e-6)
        assert fixes[path].capture_time == "2026:07:30 09:00:00"
    assert fixes[paths[1]].altitude == pytest.approx(101.0)
    assert calls[0] == ("exif", 0, 5)
    assert calls[-1] == ("exif", 5, 5)
    assert len(calls) == 4  # start + three chunks


@pytest.mark.requires_exiftool
def test_unreadable_and_untagged_files(tmp_path):
    (good,) = write_capture(tmp_path, "IMG_0001", [1])
    write_gps(good, 39.9, 32.8)
    (untagged,) = write_capture(tmp_path, "IMG_0002", [1])
    broken = tmp_path / "IMG_0003_1.tif"
    broken.write_text("not a tiff")
    missing = tmp_path / "IMG_0004_1.tif"

    fixes = ExifToolReader().read_gps([good, untagged, broken, missing])

    assert fixes[good].has_position
    assert untagged in fixes
    assert not fixes[untagged].has_position
    assert missing not in fixes
    assert broken not in fixes or not fixes[broken].has_position


@pytest.mark.requires_exiftool
def test_temp_folder_with_non_ascii_name(tmp_path, monkeypatch):
    # Like a Windows temp folder under C:\Users\<Turkish user name>\AppData\Local\Temp.
    temp = tmp_path / "Kullanıcı Şükrü" / "Temp"
    temp.mkdir(parents=True)
    monkeypatch.setattr(exif.tempfile, "tempdir", str(temp))
    (path,) = write_capture(tmp_path / "Çekim", "IMG_0001", [1])
    write_gps(path, 39.9, 32.8)

    fixes = ExifToolReader().read_gps([path])

    assert fixes[path].latitude == pytest.approx(39.9)
    assert list(temp.iterdir()) == []  # argfile removed
