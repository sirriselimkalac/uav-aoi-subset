import subprocess
import sys

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
def test_index_no_matches(tmp_path, capsys):
    (tmp_path / "notes.txt").write_text("x")
    assert main(["index", str(tmp_path)]) == 1
    assert "No band files" in capsys.readouterr().err


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
    assert "not a file" in err and "cannot read" in err


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
    assert (dest / "Saha_Fotoğrafları_Part2_0000SET_000_IMG_0000_7.tif").is_file()
    assert (dest / "Kalibrasyon_IMG_0000_1.tif").is_file()
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
    (dest / "Saha_Fotoğrafları_Part2_0000SET_000_IMG_0000_2.tif").write_bytes(b"x")
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


def test_copy_folders_layout(copy_inputs, tmp_path, capsys):
    root, subset = copy_inputs
    dest = tmp_path / "out"
    assert main(["copy", str(root), str(subset), "--dest", str(dest), "--layout", "folders"]) == 0
    assert (dest / "Saha_Fotoğrafları_Part2_0000SET_000" / "IMG_0000_1.tif").is_file()
    assert "Layout:             folders" in capsys.readouterr().out
