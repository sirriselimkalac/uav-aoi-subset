import subprocess
import sys

import pytest
from synthetic import make_altum_tree, write_capture, write_gps

from uav_aoi_subset import __version__
from uav_aoi_subset.cli import main
from uav_aoi_subset.core.index import read_index_csv

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
