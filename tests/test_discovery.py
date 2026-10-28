import pytest
from synthetic import ALTUM_LAYOUT, make_altum_tree, write_capture

from uav_aoi_subset.core.discovery import (
    OUTPUT_MARKER,
    discover_captures,
    flat_folder_name,
    record_name,
    sanitize_token,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Part1", "Part1"),
        ("Saha Fotoğrafları", "Saha_Fotoğrafları"),
        ("  a  b  ", "a_b"),
        ('a<b>c:d"e|f?g*h', "a_b_c_d_e_f_g_h"),
        ("a/b\\c", "a_b_c"),
        ("a\tb\nc", "a_b_c"),
        ("__a___b__", "a_b"),
        ("___", ""),
    ],
)
def test_sanitize_token(raw, expected):
    assert sanitize_token(raw) == expected


def test_flat_folder_name_and_record_name():
    parts = ("Saha Fotoğrafları", "Part1", "0000SET", "000")
    assert flat_folder_name(parts) == "Saha_Fotoğrafları_Part1_0000SET_000"
    assert record_name(parts, "IMG_0000") == "Saha_Fotoğrafları_Part1_0000SET_000_IMG_0000"
    assert record_name((), "IMG_0000") == "IMG_0000"
    assert flat_folder_name(("a", "  ", "b")) == "a_b"


def test_altum_tree_gives_unique_record_names(tmp_path):
    make_altum_tree(tmp_path)
    captures = discover_captures(tmp_path)

    assert len(captures) == sum(len(b) for b in ALTUM_LAYOUT.values())
    names = [c.record_name for c in captures]
    assert len(set(names)) == len(names)
    # IMG_0000 exists in three different SET folders.
    assert sum(c.base == "IMG_0000" for c in captures) == 3
    assert "Saha_Fotoğrafları_Part1_0001SET_000_IMG_0000" in names
    assert "Saha_Fotoğrafları_Part2_0000SET_000_IMG_0000" in names
    assert all(c.is_complete(7) for c in captures)
    assert all(c.bands_found == (1, 2, 3, 4, 5, 6, 7) for c in captures)


def test_capture_paths_and_relative_folder(tmp_path):
    make_altum_tree(tmp_path)
    capture = next(c for c in discover_captures(tmp_path) if c.base == "IMG_0003")
    assert capture.relative_folder == "Saha Fotoğrafları/Part1/0000SET/001"
    assert capture.band_files[1] == tmp_path / capture.relative_folder / "IMG_0003_1.tif"


def test_incomplete_and_band1_missing(tmp_path):
    write_capture(tmp_path / "f", "IMG_0001", [1, 2, 3, 5, 6, 7])
    write_capture(tmp_path / "f", "IMG_0002", [2, 3, 4, 5, 6, 7])
    c1, c2 = discover_captures(tmp_path)
    assert not c1.is_complete(7)
    assert c1.missing_bands(7) == (4,)
    assert c2.missing_bands(7) == (1,)
    assert 1 not in c2.band_files


def test_band_count_parameter(tmp_path):
    write_capture(tmp_path, "IMG_0001", range(1, 6))
    (capture,) = discover_captures(tmp_path)
    assert capture.is_complete(5)
    assert not capture.is_complete(7)


def test_pattern_matching(tmp_path):
    write_capture(tmp_path, "IMG_12345", [1], ext=".TIF")  # any digit count, any case
    write_capture(tmp_path, "IMG_0002", [1], ext=".tiff")
    (tmp_path / "IMG_0003_1_undistorted.tif").write_bytes(b"x")
    (tmp_path / "IMG_0004_1.jpg").write_bytes(b"x")
    (tmp_path / "notes.txt").write_bytes(b"x")
    bases = sorted(c.base for c in discover_captures(tmp_path))
    assert bases == ["IMG_0002", "IMG_12345"]


def test_custom_pattern(tmp_path):
    (tmp_path / "DJI_0001_B3.TIF").write_bytes(b"x")
    pattern = r"^(?P<base>DJI_\d+)_B(?P<band>\d)\.tif$"
    (capture,) = discover_captures(tmp_path, pattern=pattern)
    assert capture.base == "DJI_0001"
    assert capture.bands_found == (3,)


def test_skips_hidden_marker_and_excluded_folders(tmp_path):
    write_capture(tmp_path / "Saha" / "000", "IMG_0001", [1])
    write_capture(tmp_path / ".hidden", "IMG_0002", [1])
    out = tmp_path / "subset_out" / "deep"
    write_capture(out, "IMG_0003", [1])
    (tmp_path / "subset_out" / OUTPUT_MARKER).write_text("")
    write_capture(tmp_path / "Kalibrasyon_Fotograflari_20260730" / "000", "IMG_0004", [1])
    write_capture(tmp_path / "Pix4d_Project" / "images", "IMG_0005", [1])
    write_capture(tmp_path / "Saha" / "skipme", "IMG_0006", [1])

    captures = discover_captures(tmp_path, exclude=["Kalibrasyon_*", "pix4d_*", "Saha/skipme"])
    assert [c.base for c in captures] == ["IMG_0001"]


def test_files_in_root_folder(tmp_path):
    write_capture(tmp_path, "IMG_0001", [1])
    (capture,) = discover_captures(tmp_path)
    assert capture.rel_parts == ()
    assert capture.record_name == "IMG_0001"
    assert capture.relative_folder == ""


def test_progress_is_reported(tmp_path):
    make_altum_tree(tmp_path)
    calls = []
    discover_captures(tmp_path, progress=lambda *a: calls.append(a))
    assert calls
    assert all(stage == "scan" and total is None for stage, _, total in calls)
