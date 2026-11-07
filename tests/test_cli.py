import subprocess
import sys
from dataclasses import replace

import pytest
from synthetic import (
    kml_document,
    make_altum_tree,
    polygon_kml,
    ring_text,
    square,
    write_capture,
    write_gps,
    write_kmz,
)

from uav_aoi_subset import __version__
from uav_aoi_subset.cli import main
from uav_aoi_subset.core.discovery import OUTPUT_MARKER, discover_captures
from uav_aoi_subset.core.filter import default_subset_path
from uav_aoi_subset.core.index import IndexRecord, read_index_csv, write_index_csv

COMMANDS = ["index", "filter", "copy", "footprint"]


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_no_command_prints_help(capsys):
    assert main([]) == 2
    out = capsys.readouterr().out
    for command in COMMANDS:
        assert command in out


@pytest.mark.parametrize("command", COMMANDS)
def test_subcommand_help(command, capsys):
    with pytest.raises(SystemExit) as exc:
        main([command, "--help"])
    assert exc.value.code == 0
    assert command in capsys.readouterr().out


def test_module_entry_point():
    result = subprocess.run(
        [sys.executable, "-m", "uav_aoi_subset", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert __version__ in result.stdout


@pytest.mark.requires_exiftool
def test_exiftool_runs():
    result = subprocess.run(["exiftool", "-ver"], capture_output=True, text=True, check=True)
    assert result.stdout.strip()


def test_index_missing_exiftool(tmp_path, monkeypatch, capsys):
    from uav_aoi_subset.core import exif

    monkeypatch.setattr(exif.shutil, "which", lambda name: None)
    write_capture(tmp_path, "IMG_0001", [1])
    assert main(["index", str(tmp_path)]) == 1
    assert "ExifTool was not found" in capsys.readouterr().err


def test_index_rejects_bad_arguments(tmp_path, capsys):
    assert main(["index", str(tmp_path / "missing")]) == 1
    assert main(["index", str(tmp_path), "--bands", "0"]) == 1
    assert main(["index", str(tmp_path), "--pattern", "("]) == 1
    assert main(["index", str(tmp_path), "--pattern", r"IMG_\d+"]) == 1
    err = capsys.readouterr().err
    assert "not a folder" in err
    assert "--bands" in err
    assert "invalid --pattern" in err
    assert "'base' and 'band'" in err


@pytest.mark.requires_exiftool
def test_index_end_to_end(tmp_path, capsys):
    root = tmp_path / "Kampanya"
    make_altum_tree(root)  # creates root/"Saha Fotoğrafları"/Part1/...
    write_capture(root / "Saha Fotoğrafları" / "Part2" / "0000SET" / "001", "IMG_0200", [2, 3])
    write_capture(root / "Kalibrasyon_Fotograflari", "IMG_0000", range(1, 8))
    write_gps(
        root / "Saha Fotoğrafları" / "Part1" / "0000SET" / "000" / "IMG_0000_1.tif", 39.9, 32.8
    )

    assert main(["index", str(root), "--exclude", "kalibrasyon_*"]) == 0
    out = capsys.readouterr().out
    assert "Captures found:     9" in out
    assert "incomplete:       1" in out
    assert "with GPS:         1" in out
    assert "Saha_Fotoğrafları_Part2_0000SET_001_IMG_0200  [1;4;5;6;7]" in out

    (csv_path,) = root.glob("Kampanya_image_index_*.csv")
    records = read_index_csv(csv_path)
    assert len(records) == 9
    first = records[0]
    assert first.record_name == "Saha_Fotoğrafları_Part1_0000SET_000_IMG_0000"
    assert first.latitude == pytest.approx(39.9)

    custom = tmp_path / "custom.csv"
    assert main(["index", str(root), "--out", str(custom), "--bands", "2"]) == 0
    assert len(read_index_csv(custom)) == 10  # calibration capture included this time


@pytest.mark.requires_exiftool
@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need extra rights on Windows")
def test_index_lists_folders_not_scanned(tmp_path, capsys):
    write_capture(tmp_path / "a", "IMG_0001", [1])
    (tmp_path / "a" / "loop").symlink_to(tmp_path / "a", target_is_directory=True)
    assert main(["index", str(tmp_path), "--bands", "1"]) == 0
    out = capsys.readouterr().out
    assert "Folders not scanned:" in out
    assert "linked folder not followed: a/loop" in out


@pytest.mark.requires_exiftool
def test_index_reports_duplicate_captures(tmp_path, capsys):
    for folder in ("Part1/000", "old_subset/Part1_000"):
        (band1,) = write_capture(tmp_path / folder, "IMG_0001", [1])
        write_gps(band1, 39.9, 32.8)  # same position and capture time
    write_capture(tmp_path / "Part1/000", "IMG_0002", [1])  # no GPS: never a duplicate
    assert main(["index", str(tmp_path), "--bands", "1"]) == 0
    out = capsys.readouterr().out
    assert "extra copies:     1 (same capture in another folder)" in out
    assert "IMG_0001 (2026:07:30 09:00:00) in: old_subset/Part1_000, Part1/000" in out
    assert "--skip-duplicates" in out


@pytest.mark.requires_exiftool
def test_index_no_matches(tmp_path, capsys):
    (tmp_path / "notes.txt").write_text("x")
    assert main(["index", str(tmp_path)]) == 1
    assert "no band files" in capsys.readouterr().err


def _record(name: str, lon: float | None, lat: float | None, complete: bool = True):
    return IndexRecord(
        record_name=name,
        complete=complete,
        latitude=lat,
        longitude=lon,
        altitude=100.0 if lat is not None else None,
        capture_time=None,
        bands_found=(1, 2, 3, 4, 5, 6, 7) if complete else (1, 2, 3),
        missing_bands=() if complete else (4, 5, 6, 7),
        relative_folder="Part1/0000SET/000",
        image_base=name.rsplit("_IMG_", 1)[-1],
    )


FILTER_RECORDS = [
    _record("P_IMG_0000", 10.005, 50.005),
    _record("P_IMG_0001", 10.020, 50.005),
    _record("P_IMG_0002", 10.008, 50.002, complete=False),
    _record("P_IMG_0003", None, None, complete=False),
    _record("P_IMG_0004", 10.0101, 50.005),  # ~7 m east of the AOI edge
]


@pytest.fixture
def filter_inputs(tmp_path):
    index_csv = tmp_path / "project" / "project_image_index_20261028.csv"
    index_csv.parent.mkdir()
    write_index_csv(FILTER_RECORDS, index_csv)
    aoi = tmp_path / "aoi" / "Kuzey Tarla.kml"
    aoi.parent.mkdir()
    aoi.write_text(kml_document(polygon_kml(square(10.0, 50.0, 0.01))), encoding="utf-8")
    return index_csv, aoi


def test_filter_end_to_end(filter_inputs, capsys):
    index_csv, aoi = filter_inputs
    assert main(["filter", str(index_csv), "--aoi", str(aoi)]) == 0
    out = default_subset_path(aoi)
    assert out.parent == aoi.parent
    assert out.name.startswith("Kuzey_Tarla_image_index_")
    assert [r.record_name for r in read_index_csv(out)] == ["P_IMG_0000", "P_IMG_0002"]
    assert read_index_csv(out)[1] == FILTER_RECORDS[2]  # all columns survive
    text = capsys.readouterr().out
    assert "inside the AOI:   2" in text
    assert "without GPS:      1" in text
    assert "P_IMG_0002" in text  # listed as incomplete


def test_filter_kmz_with_buffer_and_out(filter_inputs, tmp_path, capsys):
    index_csv, aoi = filter_inputs
    kmz = write_kmz(tmp_path / "aoi" / "area.kmz", aoi.read_text(encoding="utf-8"))
    out = tmp_path / "subset.csv"
    args = ["filter", str(index_csv), "--aoi", str(kmz), "--buffer", "20", "--out", str(out)]
    assert main(args) == 0
    assert [r.record_name for r in read_index_csv(out)] == [
        "P_IMG_0000",
        "P_IMG_0002",
        "P_IMG_0004",
    ]
    assert "buffer:           20 m" in capsys.readouterr().out


def test_filter_nothing_inside_writes_header(filter_inputs, capsys):
    index_csv, aoi = filter_inputs
    aoi.write_text(kml_document(polygon_kml(square(30.0, 10.0, 0.01))), encoding="utf-8")
    assert main(["filter", str(index_csv), "--aoi", str(aoi)]) == 0
    assert read_index_csv(default_subset_path(aoi)) == []
    assert "no capture lies inside" in capsys.readouterr().err


def test_filter_no_polygon(filter_inputs, capsys):
    index_csv, aoi = filter_inputs
    line = f"<LineString><coordinates>{ring_text(square(10.0, 50.0, 0.01))}</coordinates>"
    aoi.write_text(kml_document(line + "</LineString>"), encoding="utf-8")
    assert main(["filter", str(index_csv), "--aoi", str(aoi)]) == 1
    assert "no usable Polygon" in capsys.readouterr().err


def test_filter_missing_files(filter_inputs, tmp_path, capsys):
    index_csv, aoi = filter_inputs
    assert main(["filter", str(tmp_path / "nope.csv"), "--aoi", str(aoi)]) == 1
    assert main(["filter", str(index_csv), "--aoi", str(tmp_path / "nope.kml")]) == 1
    err = capsys.readouterr().err
    assert err.count("error: not a file") == 2


def test_filter_refuses_to_overwrite_input(filter_inputs, capsys):
    index_csv, aoi = filter_inputs
    assert main(["filter", str(index_csv), "--aoi", str(aoi), "--out", str(index_csv)]) == 1
    assert "overwrite" in capsys.readouterr().err


def test_filter_buffer_too_negative(filter_inputs, capsys):
    index_csv, aoi = filter_inputs
    assert main(["filter", str(index_csv), "--aoi", str(aoi), "--buffer", "-5000"]) == 1
    assert "leaves nothing" in capsys.readouterr().err


def test_filter_reads_matlab_csv(filter_inputs, tmp_path):
    _, aoi = filter_inputs
    matlab = tmp_path / "matlab.csv"
    matlab.write_text(
        "RecordName,Complete,GPSLatitude,GPSLongitude\n"
        "A_IMG_0001,1,50.005,10.005\nA_IMG_0002,1,NaN,NaN\n",
        encoding="utf-8",
    )
    out = tmp_path / "subset.csv"
    assert main(["filter", str(matlab), "--aoi", str(aoi), "--out", str(out)]) == 0
    assert [r.record_name for r in read_index_csv(out)] == ["A_IMG_0001"]


@pytest.fixture
def copy_inputs(tmp_path):
    """Campaign tree plus a subset CSV for its Part2 capture, as 'filter' would write it."""
    root = tmp_path / "Kampanya"
    make_altum_tree(root)
    (root / "Kalibrasyon").mkdir()
    write_capture(root / "Kalibrasyon", "IMG_0000", range(1, 8))
    (root / "Kalibrasyon" / "panel_reflectance.csv").write_text("nm,r\n550,0.5\n")
    captures = [c for c in discover_captures(root) if "Part2" in c.relative_folder]
    records = [
        IndexRecord(
            record_name=c.record_name,
            complete=True,
            latitude=50.0,
            longitude=10.0,
            altitude=None,
            capture_time=None,
            bands_found=c.bands_found,
            missing_bands=(),
            relative_folder=c.relative_folder,
            image_base=c.base,
        )
        for c in captures
    ]
    subset = tmp_path / "aoi" / "Kuzey_image_index_20261028.csv"
    subset.parent.mkdir()
    write_index_csv(records, subset)
    return root, subset


def test_copy_end_to_end(copy_inputs, tmp_path, capsys):
    root, subset = copy_inputs
    args = [
        "copy",
        str(root),
        str(subset),
        "--include",
        "**/panel_*.csv",
        "--extra-captures",
        "Kalibrasyon_IMG_0000",
    ]
    assert main(args) == 0
    dest = tmp_path / "Kampanya_subset_01"
    assert (dest / "Saha_Fotoğrafları_Part2_0000SET_000" / "IMG_0000_7.tif").is_file()
    assert (dest / "Kalibrasyon" / "IMG_0000_1.tif").is_file()
    assert (dest / "panel_reflectance.csv").is_file()
    out = capsys.readouterr().out
    assert "Subset records:     1 (+ 1 extra)" in out
    assert "Files copied:       15" in out  # 14 band files + 1 include
    assert "Include files:      1" in out
    (report,) = dest.parent.glob("Kampanya_subset_01_copy_report_*.csv")
    assert "copied" in report.read_text(encoding="utf-8-sig")
    assert "Kuzey_image_index_20261028.csv" in (dest / OUTPUT_MARKER).read_text(encoding="utf-8")

    # A second run writes a new folder ...
    assert main(args) == 0
    assert "Kampanya_subset_02" in capsys.readouterr().out
    assert (tmp_path / "Kampanya_subset_02" / "panel_reflectance.csv").is_file()

    # ... and resuming into the first one has nothing left to do.
    assert main([*args, "--dest", str(dest)]) == 0
    out = capsys.readouterr().out
    assert "Files copied:       0" in out
    assert "skipped:          15" in out


def test_copy_dry_run_writes_nothing(copy_inputs, tmp_path, capsys):
    root, subset = copy_inputs
    before = sorted(p for p in tmp_path.rglob("*"))
    assert main(["copy", str(root), str(subset), "--dry-run"]) == 0
    assert sorted(p for p in tmp_path.rglob("*")) == before
    out = capsys.readouterr().out
    assert "dry run" in out and "Files to copy:      7" in out

    report = tmp_path / "dry.csv"
    assert main(["copy", str(root), str(subset), "--dry-run", "--report", str(report)]) == 0
    assert "would-copy" in report.read_text(encoding="utf-8-sig")


def test_copy_move_needs_confirmation(copy_inputs, capsys):
    root, subset = copy_inputs
    assert main(["copy", str(root), str(subset), "--mode", "move"]) == 1
    assert "--confirm-move" in capsys.readouterr().err
    assert len(discover_captures(root)) == 9  # nothing moved

    assert main(["copy", str(root), str(subset), "--mode", "move", "--confirm-move"]) == 0
    assert len(discover_captures(root)) == 8


def test_copy_conflict_exit_code(copy_inputs, tmp_path, capsys):
    root, subset = copy_inputs
    dest = tmp_path / "out"
    assert main(["copy", str(root), str(subset), "--dest", str(dest)]) == 0
    (dest / "Saha_Fotoğrafları_Part2_0000SET_000" / "IMG_0000_2.tif").write_bytes(b"x")
    assert main(["copy", str(root), str(subset), "--dest", str(dest)]) == 1
    assert "conflicts:        1" in capsys.readouterr().out
    assert main(["copy", str(root), str(subset), "--dest", str(dest), "--overwrite"]) == 0


def test_copy_rejects_bad_arguments(copy_inputs, tmp_path, capsys):
    root, subset = copy_inputs
    assert main(["copy", str(tmp_path / "nope"), str(subset)]) == 1
    assert main(["copy", str(root), str(tmp_path / "nope.csv")]) == 1
    assert main(["copy", str(root), str(subset), "--bands", "0"]) == 1
    assert main(["copy", str(root), str(subset), "--pattern", "("]) == 1
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "x.txt").write_text("x")
    assert main(["copy", str(root), str(subset), "--dest", str(foreign)]) == 1
    err = capsys.readouterr().err
    assert "not a folder" in err and "not a file" in err and "--bands" in err
    assert "invalid --pattern" in err and "not empty" in err


def test_copy_not_enough_space(copy_inputs, tmp_path, monkeypatch, capsys):
    from collections import namedtuple

    from uav_aoi_subset.core import copy as copy_mod

    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(copy_mod.shutil, "disk_usage", lambda p: Usage(1, 1, 0))
    root, subset = copy_inputs
    assert main(["copy", str(root), str(subset), "--dest", str(tmp_path / "out")]) == 1
    assert "not enough free space" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_copy_default_layout_is_folders(copy_inputs, tmp_path, capsys):
    root, subset = copy_inputs
    dest = tmp_path / "out"
    assert main(["copy", str(root), str(subset), "--dest", str(dest)]) == 0
    assert (dest / "Saha_Fotoğrafları_Part2_0000SET_000" / "IMG_0000_1.tif").is_file()
    assert "Layout:             folders" in capsys.readouterr().out


def test_copy_flat_layout_renames(copy_inputs, tmp_path, capsys):
    root, subset = copy_inputs
    dest = tmp_path / "out"
    assert main(["copy", str(root), str(subset), "--dest", str(dest), "--layout", "flat"]) == 0
    assert (dest / "Saha_Fotoğrafları_Part2_0000SET_000_IMG_0000_1.tif").is_file()
    assert "Layout:             flat" in capsys.readouterr().out


def test_copy_help_warns_about_flat(capsys):
    with pytest.raises(SystemExit):
        main(["copy", "--help"])
    out = " ".join(capsys.readouterr().out.split())
    assert "folders (default)" in out
    assert "make sure your software supports renamed files" in out


# --- footprint ----------------------------------------------------------------------------


def _grid_records(folder: str, lon0: float, n: int = 4) -> list[IndexRecord]:
    step = 0.0002
    return [
        IndexRecord(
            record_name=f"{folder.replace('/', '_')}_IMG_{i * n + j:04d}",
            complete=True,
            latitude=50.0 + j * step,
            longitude=lon0 + i * step,
            altitude=None,
            capture_time=None,
            bands_found=(1, 2, 3, 4, 5, 6, 7),
            missing_bands=(),
            relative_folder=folder,
            image_base=f"IMG_{i * n + j:04d}",
        )
        for i in range(n)
        for j in range(n)
    ]


@pytest.fixture
def footprint_csv(tmp_path):
    records = [
        *_grid_records("Saha Fotoğrafları/Part1/0000SET/000", 10.0),
        *_grid_records("Saha Fotoğrafları/Part1/0000SET/001", 10.001),
        *_grid_records("Saha Fotoğrafları/Part1/0001SET/000", 10.003),
        _record("P_IMG_0099", None, None),
    ]
    path = tmp_path / "Kampanya_image_index_20261028.csv"
    write_index_csv(records, path)
    return path, records


def test_footprint_end_to_end(footprint_csv, capsys):
    csv_path, records = footprint_csv
    assert main(["footprint", str(csv_path)]) == 0
    kml = csv_path.with_suffix(".kml")
    out = capsys.readouterr().out
    assert "Captures in CSV:    49" in out
    assert "without GPS:      1" in out and "P_IMG_0099" in out
    assert "Hull:               convex" in out and " ha" in out
    assert f"Footprint written to: {kml}" in out

    # The footprint works as an AOI for 'filter' and keeps every located capture.
    subset = csv_path.parent / "subset.csv"
    assert main(["filter", str(csv_path), "--aoi", str(kml), "--out", str(subset)]) == 0
    assert len(read_index_csv(subset)) == 48


def test_footprint_never_overwrites_silently(footprint_csv, capsys):
    csv_path, _ = footprint_csv
    kml = csv_path.with_suffix(".kml")
    kml.write_text("keep", encoding="utf-8")
    assert main(["footprint", str(csv_path)]) == 1
    assert "--overwrite" in capsys.readouterr().err
    assert kml.read_text(encoding="utf-8") == "keep"
    assert main(["footprint", str(csv_path), "--overwrite"]) == 0
    assert kml.read_text(encoding="utf-8").startswith("<?xml")


def test_footprint_refuses_to_write_over_the_csv(footprint_csv, capsys):
    csv_path, _ = footprint_csv
    before = csv_path.read_bytes()
    assert main(["footprint", str(csv_path), "--out", str(csv_path), "--overwrite"]) == 1
    assert ".kml" in capsys.readouterr().err
    assert csv_path.read_bytes() == before


def test_footprint_options(footprint_csv, tmp_path, capsys):
    csv_path, _ = footprint_csv
    out = tmp_path / "flights.kml"
    args = ["footprint", str(csv_path), "--out", str(out), "--hull", "concave", "--ratio", "0.5"]
    assert main([*args, "--buffer", "15", "--per-folder", "3"]) == 0
    text = capsys.readouterr().out
    assert "Hull:               concave (ratio 0.5)" in text
    assert "Buffer:             15 m" in text
    assert "Polygons:           2" in text
    assert "Saha Fotoğrafları/Part1/0000SET: 32" in text
    kml = out.read_text(encoding="utf-8")
    assert kml.count("<Placemark>") == 2 and "<Folder>" in kml

    assert main(["footprint", str(csv_path), "--out", str(out), "--per-folder", "--overwrite"]) == 0
    assert "Polygons:           3" in capsys.readouterr().out


def test_footprint_reads_matlab_csv(tmp_path, capsys):
    matlab = tmp_path / "matlab.csv"
    matlab.write_text(
        "RecordName,Complete,GPSLatitude,GPSLongitude\n"
        "A_IMG_0001,1,50.0,10.0\nA_IMG_0002,1,50.0,10.001\n"
        "A_IMG_0003,1,50.001,10.0\nA_IMG_0004,1,NaN,NaN\n",
        encoding="utf-8",
    )
    assert main(["footprint", str(matlab)]) == 0
    assert (tmp_path / "matlab.kml").is_file()
    assert "without GPS:      1" in capsys.readouterr().out

    assert main(["footprint", str(matlab), "--per-folder", "--out", str(tmp_path / "f.kml")]) == 1
    assert "RelativeFolder" in capsys.readouterr().err


def test_footprint_rejects_bad_arguments(footprint_csv, tmp_path, capsys):
    csv_path, _ = footprint_csv
    assert main(["footprint", str(tmp_path / "nope.csv")]) == 1
    assert main(["footprint", str(csv_path), "--ratio", "0.5"]) == 1
    assert main(["footprint", str(csv_path), "--hull", "concave", "--ratio", "0"]) == 1
    assert main(["footprint", str(csv_path), "--per-folder", "-1"]) == 1
    err = capsys.readouterr().err
    assert "not a file" in err and "only applies" in err and "at most 1" in err
    assert "DEPTH" in err
    assert not csv_path.with_suffix(".kml").exists()


def test_footprint_too_few_positions(tmp_path, capsys):
    path = tmp_path / "two.csv"
    write_index_csv([_record("P_IMG_0000", 10.0, 50.0), _record("P_IMG_0001", 10.1, 50.0)], path)
    assert main(["footprint", str(path)]) == 1
    assert "at least 3" in capsys.readouterr().err
    assert not path.with_suffix(".kml").exists()


# --- errors, interruption, --debug, --version ----------------------------------------


def test_version_shows_python_and_exiftool(monkeypatch, capsys):
    from uav_aoi_subset import cli

    monkeypatch.setattr(cli, "find_exiftool", lambda: "/opt/bin/exiftool")
    monkeypatch.setattr(cli, "exiftool_version", lambda path: "13.10")
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == f"uav-aoi-subset {__version__}"
    assert lines[1].startswith("Python 3.")
    assert lines[2] == "ExifTool 13.10 at /opt/bin/exiftool"


def test_version_without_exiftool(monkeypatch, capsys):
    from uav_aoi_subset.core import exif

    monkeypatch.setattr(exif.shutil, "which", lambda name: None)
    with pytest.raises(SystemExit):
        main(["--version"])
    assert "ExifTool: not found on PATH" in capsys.readouterr().out


def test_help_documents_exit_codes(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    for code in ("0 ", "1 ", "2 ", "130"):
        assert f"  {code}" in out


def test_ctrl_c_exits_130_without_traceback(tmp_path, monkeypatch, capsys):
    from uav_aoi_subset import cli

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "ExifToolReader", lambda path: None)
    monkeypatch.setattr(cli, "build_index", interrupted)
    assert main(["index", str(tmp_path)]) == 130
    err = capsys.readouterr().err
    assert "Interrupted." in err
    assert "Traceback" not in err


def test_ctrl_c_during_copy_tells_how_to_resume(copy_inputs, tmp_path, monkeypatch, capsys):
    from uav_aoi_subset import cli

    def interrupted(plan, progress):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "execute_copy", interrupted)
    root, subset = copy_inputs
    assert main(["copy", str(root), str(subset)]) == 130
    err = capsys.readouterr().err
    dest = tmp_path / "Kampanya_subset_01"
    assert f'--dest "{dest}"' in err
    assert "Interrupted." in err
    assert list(tmp_path.glob("Kampanya_subset_01_copy_report_*.csv"))


def test_permission_error_on_output(filter_inputs, monkeypatch, capsys):
    from uav_aoi_subset import cli

    def locked(records, path):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(cli, "write_index_csv", locked)
    index_csv, aoi = filter_inputs
    assert main(["filter", str(index_csv), "--aoi", str(aoi)]) == 1
    err = capsys.readouterr().err
    assert "permission denied" in err
    assert "--out" in err
    assert "Traceback" not in err


@pytest.mark.parametrize("debug", [False, True])
def test_unexpected_error(filter_inputs, monkeypatch, capsys, debug):
    from uav_aoi_subset import cli

    def broken(records, area):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "filter_records", broken)
    index_csv, aoi = filter_inputs
    args = ["filter", str(index_csv), "--aoi", str(aoi)] + (["--debug"] if debug else [])
    assert main(args) == 1
    err = capsys.readouterr().err
    assert "error: unexpected RuntimeError: boom" in err
    assert ("Traceback" in err) is debug
    assert ("Re-run with --debug" in err) is not debug
    assert "issues" in err


def test_every_error_says_what_to_do_next(tmp_path, capsys):
    (tmp_path / "x.csv").write_text("a,b\n1,2\n")
    cases = [
        ["index", str(tmp_path / "missing")],
        ["index", str(tmp_path), "--bands", "0"],
        ["index", str(tmp_path), "--pattern", "("],
        ["filter", str(tmp_path / "x.csv"), "--aoi", str(tmp_path / "x.csv")],
        ["footprint", str(tmp_path / "x.csv")],
        ["footprint", str(tmp_path / "x.csv"), "--ratio", "0.5"],
    ]
    for argv in cases:
        assert main(argv) == 1, argv
        err = capsys.readouterr().err
        lines = err.splitlines()
        assert lines[0].startswith("error: "), argv
        assert len(lines) >= 2 and lines[1].startswith("  "), argv


def test_filter_skip_duplicates(filter_inputs, tmp_path, capsys):
    index_csv, aoi = filter_inputs
    timed = [replace(r, capture_time="2026:07:30 09:00:00") for r in FILTER_RECORDS]
    copy = replace(timed[0], record_name="old_P_IMG_0000", relative_folder="old")
    write_index_csv([*timed, copy], index_csv)

    out = tmp_path / "all.csv"
    assert main(["filter", str(index_csv), "--aoi", str(aoi), "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "extra copies:   1 (kept)" in text
    assert "0000 (2026:07:30 09:00:00) in: old, Part1/0000SET/000" in text  # base "0000"
    assert len(read_index_csv(out)) == 3

    args = ["filter", str(index_csv), "--aoi", str(aoi), "--out", str(out), "--skip-duplicates"]
    assert main(args) == 0
    assert "extra copies:   1 (left out)" in capsys.readouterr().out
    # The first folder in case-insensitive order is kept.
    assert [r.record_name for r in read_index_csv(out)] == ["P_IMG_0002", "old_P_IMG_0000"]


def test_filter_skip_duplicates_without_capture_times(filter_inputs, tmp_path, capsys):
    index_csv, aoi = filter_inputs
    out = tmp_path / "x.csv"
    assert (
        main(["filter", str(index_csv), "--aoi", str(aoi), "--out", str(out), "--skip-duplicates"])
        == 0
    )
    assert "copies cannot be recognised" in capsys.readouterr().err


def test_copy_skip_duplicates(tmp_path, capsys):
    root = tmp_path / "Kampanya"
    for folder in ("Part1/000", "old/Part1_000"):
        write_capture(root / folder, "IMG_0001", range(1, 8))
    records = [
        IndexRecord(
            record_name=c.record_name,
            complete=True,
            latitude=50.0,
            longitude=10.0,
            altitude=None,
            capture_time="2026:07:30 09:00:00",
            bands_found=c.bands_found,
            missing_bands=(),
            relative_folder=c.relative_folder,
            image_base=c.base,
        )
        for c in discover_captures(root)
    ]
    subset = tmp_path / "subset.csv"
    write_index_csv(records, subset)

    assert main(["copy", str(root), str(subset), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Files to copy:      14" in out
    assert "IMG_0001 (2026:07:30 09:00:00) in: old/Part1_000, Part1/000" in out

    assert main(["copy", str(root), str(subset), "--dry-run", "--skip-duplicates"]) == 0
    out = capsys.readouterr().out
    assert "Files to copy:      7" in out
    assert "extra copies:     1 (left out, see below)" in out
    assert "Part1_000_IMG_0001: copy of old_Part1_000_IMG_0001" in out
