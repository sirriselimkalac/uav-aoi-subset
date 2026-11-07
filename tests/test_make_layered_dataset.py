import csv
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
from synthetic import kml_document, polygon_kml, write_capture, write_gps

from uav_aoi_subset.core.aoi import load_aoi
from uav_aoi_subset.core.copy import plan_copy
from uav_aoi_subset.core.discovery import discover_captures, record_name
from uav_aoi_subset.core.duplicates import find_duplicates
from uav_aoi_subset.core.exif import ExifToolReader
from uav_aoi_subset.core.filter import filter_records
from uav_aoi_subset.core.index import (
    CSV_ENCODING,
    IndexRecord,
    build_index,
    write_index_csv,
)

SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "make_layered_dataset.py"

_spec = importlib.util.spec_from_file_location("make_layered_dataset", SCRIPT)
mld = importlib.util.module_from_spec(_spec)
sys.modules["make_layered_dataset"] = mld
_spec.loader.exec_module(mld)


def run(*args):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.returncode, result.stdout, result.stderr


def flat_dataset(folder: Path, captures: int = 10, bands: int = 7, first: int = 0) -> Path:
    """One folder of band files plus a calibration CSV, like a published example dataset."""
    for n in range(first, first + captures):
        write_capture(folder, f"IMG_{n:04d}", range(1, bands + 1))
    (folder / "panel_reflectance.csv").write_text("wavelength,reflectance\n", encoding="utf-8")
    return folder


def snapshot(folder: Path) -> dict[str, tuple[int, int]]:
    return {
        p.relative_to(folder).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
        for p in folder.rglob("*")
    }


def tree(folder: Path) -> list[str]:
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())


def mapping_rows(output: Path) -> list[dict[str, str]]:
    with mld.mapping_path(output).open(encoding=CSV_ENCODING, newline="") as f:
        return list(csv.DictReader(f))


# --- build ------------------------------------------------------------------------------


def test_group_sizes_differ_by_at_most_one():
    assert mld._group_sizes(10, 4) == [3, 3, 2, 2]
    assert mld._group_sizes(480, 4) == [120] * 4
    assert mld._group_sizes(3, 3) == [1, 1, 1]


def test_build_splits_in_number_order_and_restarts_numbering(tmp_path):
    data = flat_dataset(tmp_path / "flat")
    before = snapshot(data)
    out = tmp_path / "layered"
    code, stdout, stderr = run("build", data, out)
    assert code == 0, stdout + stderr

    files = tree(out)
    assert len(files) == 10 * 7 + 1
    sets = {f.split("/")[0] for f in files}
    assert sets == {"0000SET", "0001SET", "0002SET", "0003SET"}
    for name, count in (("0000SET", 3), ("0001SET", 3), ("0002SET", 2), ("0003SET", 2)):
        bases = {f.split("/")[2].rsplit("_", 1)[0] for f in files if f.startswith(name)}
        bases.discard("panel")  # the calibration CSV
        assert bases == {f"IMG_{i:04d}" for i in range(count)}, name
    assert "0000SET/000/panel_reflectance.csv" in files
    assert "0003SET/000/IMG_0001_7.tif" in files
    assert snapshot(data) == before  # INPUT never changes

    rows = mapping_rows(out)
    last = next(r for r in rows if r["OriginalFile"] == "IMG_0009_5.tif")
    assert last == {
        "OriginalFile": "IMG_0009_5.tif",
        "OriginalImageBase": "IMG_0009",
        "OriginalRecordName": "IMG_0009",
        "Group": "4",
        "Kind": "band",
        "NewPath": "0003SET/000/IMG_0001_5.tif",
        "NewRelativeFolder": "0003SET/000",
        "NewImageBase": "IMG_0001",
        "NewRecordName": "0003SET_000_IMG_0001",
    }
    panel = next(r for r in rows if r["Kind"] == "auxiliary")
    assert panel["NewPath"] == "0000SET/000/panel_reflectance.csv"
    assert panel["NewRecordName"] == ""
    assert "Space needed:" in stdout and "Mapping:" in stdout


def test_layered_copy_is_indexed_with_unique_capture_keys(tmp_path):
    data = flat_dataset(tmp_path / "flat")
    out = tmp_path / "layered"
    assert run("build", data, out)[0] == 0
    captures = discover_captures(out)
    assert len(captures) == 10
    assert all(c.is_complete(7) for c in captures)
    assert len({c.record_name for c in captures}) == 10
    # The same image name exists in every set folder.
    assert sum(c.base == "IMG_0000" for c in captures) == 4


def test_folder_captures_starts_new_sub_folders(tmp_path):
    data = flat_dataset(tmp_path / "flat", captures=6)
    out = tmp_path / "layered"
    assert run("build", data, out, "--parts", "1", "--folder-captures", "4")[0] == 0
    files = tree(out)
    assert "0000SET/000/IMG_0003_1.tif" in files
    assert "0000SET/001/IMG_0004_1.tif" in files  # numbering goes on across sub-folders
    assert "0000SET/001/IMG_0005_7.tif" in files


def test_sorted_by_number_not_by_name(tmp_path):
    data = tmp_path / "flat"
    for n in (9, 10, 100):
        write_capture(data, f"IMG_{n}", [1])
    layout = mld.plan_layout(data, parts=1, bands=1)
    assert layout.groups == [["IMG_9", "IMG_10", "IMG_100"]]
    names = [i.new_path.as_posix() for i in layout.items]
    assert names == [f"0000SET/000/IMG_{n:03d}_1.tif" for n in range(3)]


def test_custom_pattern_bands_and_turkish_paths(tmp_path):
    data = tmp_path / "Örnek veri – düz"
    for n in range(1, 5):
        write_capture(data, f"DSC{n:03d}", range(1, 6), ext=".TIF")
    write_capture(data, "DSC005", [1, 2], ext=".TIF")  # incomplete
    out = tmp_path / "Katmanlı çıktı"
    pattern = r"^(?P<base>DSC\d+)-(?P<band>\d)\.tif$"
    for p in data.iterdir():  # DSC001_1.TIF -> DSC001-1.TIF
        p.rename(p.with_name(p.name.replace("_", "-")))
    code, stdout, stderr = run(
        "build", data, out, "--parts", "2", "--bands", "5", "--pattern", pattern
    )
    assert code == 0, stdout + stderr
    assert "1 incomplete" in stdout
    files = tree(out)
    assert "0000SET/000/DSC000-1.TIF" in files
    assert "0001SET/000/DSC001-2.TIF" in files  # the incomplete capture, moved as it is
    assert "0001SET/000/DSC001-3.TIF" not in files
    assert len(files) == 4 * 5 + 2
    assert mld.mapping_path(out).name == "Katmanlı çıktı_mapping.csv"


def test_add_duplicate_writes_one_group_again(tmp_path):
    data = flat_dataset(tmp_path / "flat")
    out = tmp_path / "layered"
    code, stdout, stderr = run("build", data, out, "--add-duplicate")
    assert code == 0, stdout + stderr
    files = tree(out)
    copies = [f for f in files if f.startswith("old_subset/")]
    assert len(copies) == 3 * 7  # group 2 = 0001SET, 3 captures
    assert "old_subset/0001SET_000/IMG_0002_7.tif" in copies
    original = (out / "0001SET/000/IMG_0002_7.tif").read_bytes()
    assert (out / "old_subset/0001SET_000/IMG_0002_7.tif").read_bytes() == original
    kinds = {r["Kind"] for r in mapping_rows(out)}
    assert kinds == {"band", "auxiliary", "duplicate"}


def test_add_duplicate_group_out_of_range(tmp_path):
    data = flat_dataset(tmp_path / "flat")
    code, _, stderr = run("build", data, tmp_path / "out", "--add-duplicate", "5")
    assert code == 1
    assert "only groups 1 to 4" in stderr
    assert not (tmp_path / "out").exists()


def test_hardlink_shares_the_files(tmp_path):
    data = flat_dataset(tmp_path / "flat", captures=4)
    out = tmp_path / "layered"
    code, stdout, stderr = run("build", data, out, "--mode", "hardlink")
    if code != 0 and "hard link" in stderr:
        pytest.skip("file system without hard links")
    assert code == 0, stdout + stderr
    assert "Space needed:     0 bytes" in stdout
    assert (out / "0000SET/000/IMG_0000_1.tif").stat().st_nlink == 2
    assert (data / "IMG_0000_1.tif").stat().st_nlink == 2


@pytest.mark.parametrize(
    ("setup", "args", "message"),
    [
        ("full", ["--parts", "11"], "more than the 10 captures"),
        ("full", ["--parts", "0"], "--parts must be at least 1"),
        ("full", ["--pattern", r"^(?P<base>IMG_\d+)\.tif$"], "groups (?P<base>...) and"),
        ("empty", [], "no band files found"),
        ("nonumber", ["--pattern", r"^(?P<base>[A-Z]+)_(?P<band>\d)\.tif$"], "does not end"),
    ],
)
def test_refusals_write_nothing(tmp_path, setup, args, message):
    data = tmp_path / "flat"
    if setup == "full":
        flat_dataset(data)
    elif setup == "empty":
        data.mkdir()
    else:
        write_capture(data, "ABC", [1])
    out = tmp_path / "out"
    code, _, stderr = run("build", data, out, *args)
    assert code == 1
    assert message in stderr
    assert stderr.startswith("error: ")
    assert len(stderr.strip().splitlines()) >= 2  # with the next step
    assert not out.exists()


def test_refuses_non_empty_output_and_output_inside_input(tmp_path):
    data = flat_dataset(tmp_path / "flat")
    out = tmp_path / "out"
    out.mkdir()
    (out / "something.txt").write_text("x")
    code, _, stderr = run("build", data, out)
    assert code == 1 and "is not empty" in stderr

    code, _, stderr = run("build", data, data / "inside")
    assert code == 1 and "must not be inside INPUT" in stderr
    assert not (data / "inside").exists()

    code, _, stderr = run("build", data, tmp_path)
    assert code == 1 and "INPUT is inside OUTPUT" in stderr


def test_empty_output_folder_is_used(tmp_path):
    data = flat_dataset(tmp_path / "flat", captures=4)
    out = tmp_path / "out"
    out.mkdir()
    assert run("build", data, out)[0] == 0
    assert len(tree(out)) == 4 * 7 + 1


def test_existing_mapping_is_not_overwritten(tmp_path):
    data = flat_dataset(tmp_path / "flat", captures=4)
    out = tmp_path / "out"
    mld.mapping_path(out).write_text("keep me")
    code, _, stderr = run("build", data, out)
    assert code == 1 and "already exists" in stderr
    assert mld.mapping_path(out).read_text() == "keep me"


def test_sub_folders_of_input_are_ignored_with_a_warning(tmp_path):
    data = flat_dataset(tmp_path / "flat", captures=4)
    write_capture(data / "extra", "IMG_0100", range(1, 8))
    code, stdout, _ = run("build", data, tmp_path / "out")
    assert code == 0
    assert "sub-folder ignored" in stdout and "extra" in stdout
    assert len(discover_captures(tmp_path / "out")) == 4


def test_outputs_of_the_tool_are_not_copied(tmp_path):
    data = flat_dataset(tmp_path / "flat", captures=4)
    for name in (
        "flat_image_index_20261028.csv",
        "x_copy_report_20261028-101500.csv",
        "old_mapping.csv",
    ):
        (data / name).write_text("x", encoding="utf-8")
    code, stdout, _ = run("build", data, tmp_path / "out")
    assert code == 0
    assert stdout.count("Not copied (written by uav-aoi-subset)") == 3
    assert [f for f in tree(tmp_path / "out") if f.endswith(".csv")] == [
        "0000SET/000/panel_reflectance.csv"
    ]


def test_ctrl_c_leaves_no_partial_file(tmp_path, monkeypatch, capsys):
    data = flat_dataset(tmp_path / "flat", captures=4)
    out = tmp_path / "out"
    real_copy = mld.shutil.copy2
    calls = []

    def interrupt(src, dst):
        calls.append(dst)
        if len(calls) == 5:
            real_copy(src, dst)  # the partial file exists when Ctrl+C arrives
            raise KeyboardInterrupt
        return real_copy(src, dst)

    monkeypatch.setattr(mld.shutil, "copy2", interrupt)
    assert mld.main(["build", str(data), str(out)]) == 130
    err = capsys.readouterr().err
    assert "Interrupted." in err and f"delete {out}" in err
    assert not list(out.rglob("*" + mld.PARTIAL_SUFFIX))
    assert len(tree(out)) == 4
    assert not mld.mapping_path(out).exists()


# --- verify -----------------------------------------------------------------------------


def record(folder: str, base: str, lat: float | None = 50.0, lon: float | None = 10.0):
    parts = tuple(folder.split("/")) if folder else ()
    return IndexRecord(
        record_name=record_name(parts, base),
        complete=True,
        latitude=lat,
        longitude=lon,
        altitude=None,
        capture_time="2026:07:30 09:00:00",
        bands_found=(1,),
        missing_bands=(),
        relative_folder=folder,
        image_base=base,
    )


@pytest.fixture
def layered(tmp_path):
    data = flat_dataset(tmp_path / "flat", captures=8)
    out = tmp_path / "layered"
    assert run("build", data, out, "--add-duplicate", "1")[0] == 0
    return mld.mapping_path(out)


def write_csv(path: Path, records) -> Path:
    write_index_csv(records, path)
    return path


def test_verify_same(tmp_path, layered):
    flat = write_csv(tmp_path / "f.csv", [record("", "IMG_0001"), record("", "IMG_0005")])
    lay = write_csv(
        tmp_path / "l.csv", [record("0000SET/000", "IMG_0001"), record("0002SET/000", "IMG_0001")]
    )
    code, out, _ = run("verify", layered, flat, lay)
    assert code == 0, out
    assert "Captures: 2 (flat) / 2 (layered)" in out
    assert "RESULT: SAME" in out


def test_verify_different(tmp_path, layered):
    flat = write_csv(tmp_path / "f.csv", [record("", "IMG_0001"), record("", "IMG_0002")])
    lay = write_csv(
        tmp_path / "l.csv",
        [
            record("0000SET/000", "IMG_0001"),
            record("0003SET/000", "IMG_0000"),
            record("elsewhere", "IMG_0001"),
        ],
    )
    code, out, _ = run("verify", layered, flat, lay)
    assert code == 1
    assert "Only in the flat subset: 1\n  IMG_0002" in out
    assert "Only in the layered subset: 1\n  IMG_0006" in out
    assert "Layered records not in the mapping: 1" in out
    assert "RESULT: DIFFERENT" in out


def test_verify_reports_copies_and_positions(tmp_path, layered):
    flat = write_csv(tmp_path / "f.csv", [record("", "IMG_0001", 50.0, 10.0)])
    lay = write_csv(
        tmp_path / "l.csv",
        [record("0000SET/000", "IMG_0001"), record("old_subset/0000SET_000", "IMG_0001")],
    )
    code, out, _ = run("verify", layered, flat, lay)
    assert code == 0, out
    assert "more than once in the layered subset (1 extra)" in out
    assert "--skip-duplicates" in out

    moved = write_csv(tmp_path / "m.csv", [record("0000SET/000", "IMG_0001", 50.1, 10.0)])
    code, out, _ = run("verify", layered, flat, moved)
    assert code == 1 and "Position differs: 1" in out


def test_verify_reads_csvs_with_record_names_only(tmp_path, layered):
    header = "RecordName,Complete,GPSLatitude,GPSLongitude\n"
    flat = tmp_path / "f.csv"
    flat.write_text(header + "IMG_0003,1,50.0,10.0\n", encoding="utf-8")
    lay = tmp_path / "l.csv"
    lay.write_text(header + "0001SET_000_IMG_0001,1,50.0,10.0\n", encoding="utf-8")
    code, out, _ = run("verify", layered, flat, lay)
    assert code == 0, out


def test_verify_missing_or_wrong_files(tmp_path, layered):
    flat = write_csv(tmp_path / "f.csv", [record("", "IMG_0001")])
    code, _, err = run("verify", layered, flat, tmp_path / "missing.csv")
    assert code == 1 and "not found" in err
    code, _, err = run("verify", flat, flat, flat)  # an index CSV is not a mapping
    assert code == 1 and "not a mapping CSV" in err


# --- end to end with real GPS tags -------------------------------------------------------


@pytest.mark.requires_exiftool
def test_flat_and_layered_give_the_same_subset(tmp_path):
    data = tmp_path / "flat"
    # 4 flight lines of 3 captures, flown back and forth (numbers follow the lines).
    for n in range(12):
        line, step = divmod(n, 3)
        step = step if line % 2 == 0 else 2 - step
        write_capture(data, f"IMG_{n:04d}", range(1, 8))
        write_gps(data / f"IMG_{n:04d}_1.tif", 50.0 + step * 0.001, 10.0 + line * 0.001)
    out = tmp_path / "layered"
    assert run("build", data, out, "--add-duplicate", "2")[0] == 0

    reader = ExifToolReader()
    flat_records = build_index(data, reader)
    layered_records = build_index(out, reader)
    assert len(flat_records) == 12
    assert len(layered_records) == 12 + 3

    groups = find_duplicates(layered_records)
    assert len(groups) == 3  # only the old_subset copies, not IMG_0000 in every set
    assert all(g[1].relative_folder.startswith("old_subset/") for g in groups)

    # An AOI across the flight lines: the middle row of every line.
    kml = tmp_path / "cross.kml"
    shell = [(9.9995, 50.0005), (10.0035, 50.0005), (10.0035, 50.0015), (9.9995, 50.0015)]
    kml.write_text(kml_document(polygon_kml(shell)), encoding="utf-8")
    geometry = load_aoi(kml).geometry
    flat_subset = filter_records(flat_records, geometry).inside
    layered_subset = filter_records(layered_records, geometry).inside
    assert len(flat_subset) == 4
    assert {r.relative_folder.split("/")[0] for r in layered_subset} >= {
        "0000SET",
        "0001SET",
        "0002SET",
        "0003SET",
    }

    f_csv = write_csv(tmp_path / "flat_subset.csv", flat_subset)
    l_csv = write_csv(tmp_path / "layered_subset.csv", layered_subset)
    code, stdout, _ = run("verify", mld.mapping_path(out), f_csv, l_csv)
    assert code == 0, stdout
    assert "RESULT: SAME" in stdout and "more than once" in stdout

    plan = plan_copy(out, layered_subset, tmp_path / "dest", skip_duplicates=True)
    dest = tmp_path / "dest"
    names = [t.destination.relative_to(dest).as_posix() for t in plan.tasks if t.destination]
    assert len(names) == len(set(names)) == 4 * 7
    assert "0000SET_000/IMG_0001_1.tif" in names  # default layout: file names unchanged
    flat = plan_copy(out, layered_subset, dest, skip_duplicates=True, layout="flat")
    flat_names = [t.destination.name for t in flat.tasks if t.destination is not None]
    assert len(flat_names) == len(set(flat_names)) == 4 * 7
    assert "0000SET_000_IMG_0001_1.tif" in flat_names
