import csv
import errno
import re
from collections import namedtuple
from pathlib import Path

import pytest
from synthetic import ALTUM_LAYOUT, make_altum_tree, write_capture

from uav_aoi_subset.core import copy as copy_mod
from uav_aoi_subset.core.copy import (
    PARTIAL_SUFFIX,
    REPORT_COLUMNS,
    CopyError,
    assign_flat_folders,
    default_dest,
    default_report_path,
    execute_copy,
    load_extra_captures,
    long_path,
    plan_copy,
    write_copy_report,
)
from uav_aoi_subset.core.discovery import OUTPUT_MARKER, discover_captures
from uav_aoi_subset.core.index import CSV_ENCODING, IndexRecord, write_index_csv

FIELD = "Saha Fotoğrafları/Part1/0000SET/000"
FIELD_FLAT = "Saha_Fotoğrafları_Part1_0000SET_000"


def records_for(root: Path, bands: int = 7, folders_like: str = "") -> list[IndexRecord]:
    """Index records for the captures on disk (no GPS), like 'index' + 'filter' would give."""
    return [
        IndexRecord(
            record_name=c.record_name,
            complete=c.is_complete(bands),
            latitude=None,
            longitude=None,
            altitude=None,
            capture_time=None,
            bands_found=c.bands_found,
            missing_bands=c.missing_bands(bands),
            relative_folder=c.relative_folder,
            image_base=c.base,
        )
        for c in discover_captures(root)
        if folders_like in c.relative_folder
    ]


def matlab_record(name: str) -> IndexRecord:
    """A row from a MATLAB CSV: only the record name is known."""
    return load_extra_captures([name])[0]


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "Kampanya"
    make_altum_tree(root)
    return root


def run(root, records, dest, **kwargs):
    plan = plan_copy(root, records, dest, **kwargs)
    execute_copy(plan)
    return plan


def statuses(plan):
    return plan.summary().statuses


def files_under(path: Path) -> set[str]:
    return {p.relative_to(path).as_posix() for p in path.rglob("*") if p.is_file()}


# --- pure helpers -------------------------------------------------------------------------


def test_assign_flat_folders_collisions():
    names = assign_flat_folders(
        [("A B", "x"), ("A_B", "x"), ("Part1", "X"), ("part1", "x"), (), ("C",), ("A B", "x")]
    )
    assert names == {
        (): "",
        ("A B", "x"): "A_B_x",
        ("A_B", "x"): "A_B_x_v02",
        ("C",): "C",
        ("Part1", "X"): "Part1_X",
        ("part1", "x"): "part1_x_v02",
    }
    # The order of the input does not matter.
    assert assign_flat_folders([("A_B", "x"), ("A B", "x")]) == {
        ("A B", "x"): "A_B_x",
        ("A_B", "x"): "A_B_x_v02",
    }


def test_long_path_windows_forms():
    assert long_path(r"C:\data\x.tif", windows=True) == "\\\\?\\C:\\data\\x.tif"
    assert long_path("C:/data/../data/x.tif", windows=True) == "\\\\?\\C:\\data\\x.tif"
    assert long_path(r"\\server\share\x.tif", windows=True) == "\\\\?\\UNC\\server\\share\\x.tif"
    assert long_path("\\\\?\\C:\\x", windows=True) == "\\\\?\\C:\\x"
    assert long_path("/data/x.tif", windows=False) == "/data/x.tif"


def test_default_dest_is_numbered_next_to_root(tmp_path):
    root = tmp_path / "Saha Kampanya"
    root.mkdir()
    dest = default_dest(root)
    assert dest == (tmp_path / "Saha_Kampanya_subset_01").resolve()
    assert not dest.is_relative_to(root.resolve())
    assert not dest.exists()  # only chosen, not created


def test_default_dest_takes_the_first_free_number(tmp_path):
    root = tmp_path / "Kampanya"
    root.mkdir()
    (tmp_path / "Kampanya_subset_01").mkdir()
    (tmp_path / "kampanya_SUBSET_02").write_text("x")  # a file, other case: still taken
    (tmp_path / "Kampanya_subset_04").mkdir()
    assert default_dest(root).name == "Kampanya_subset_03"


def test_default_dest_at_the_top_of_a_drive_goes_inside_it():
    top = Path(Path.cwd().anchor).resolve()
    dest = default_dest(top)
    assert dest.parent == top
    expected = top.drive.rstrip(":") if top.drive else "drive"
    assert re.fullmatch(rf"{re.escape(expected)}_subset_\d\d", dest.name)
    assert not dest.exists()  # only chosen, not created


def test_marker_records_the_source(tree, tmp_path):
    dest = tmp_path / "out"
    plan = plan_copy(tree, records_for(tree), dest, subset_name="Kuzey_image_index.csv")
    execute_copy(plan)
    text = (dest / OUTPUT_MARKER).read_text(encoding="utf-8")
    assert "Subset CSV: Kuzey_image_index.csv" in text
    assert f"ROOT: {tree}" in text


def test_default_report_path(tmp_path):
    import datetime as dt

    path = default_report_path(tmp_path / "out", dt.datetime(2026, 10, 28, 9, 5, 3))
    assert path == tmp_path / "out_copy_report_20261028-090503.csv"


# --- flattening, matching, missing bands --------------------------------------------------


def test_copy_flattens_folders(tree, tmp_path):
    dest = tmp_path / "out"
    plan = run(tree, records_for(tree), dest)

    n_captures = sum(len(b) for b in ALTUM_LAYOUT.values())
    s = plan.summary()
    assert s.captures == n_captures and s.groups_transferred == n_captures
    assert s.statuses["copied"] == 7 * n_captures
    assert s.bytes_transferred == s.bytes_total > 0
    files = files_under(dest)
    assert f"{FIELD_FLAT}_IMG_0000_1.tif" in files
    # IMG_0000 exists in three SET folders and is kept apart.
    assert "Saha_Fotoğrafları_Part1_0001SET_000_IMG_0000_7.tif" in files
    assert "Saha_Fotoğrafları_Part2_0000SET_000_IMG_0000_7.tif" in files
    assert OUTPUT_MARKER in files
    assert not any(f.endswith(".dat") for f in files)
    assert len(files) == 7 * n_captures + 1
    # The output is never indexed.
    assert discover_captures(dest) == []


@pytest.mark.parametrize(
    ("layout", "first", "second"),
    [
        ("flat", "A_B_000_IMG_0001_1.tif", "A_B_000_v02_IMG_0001_1.tif"),
        ("folders", "A_B_000/IMG_0001_1.tif", "A_B_000_v02/IMG_0001_1.tif"),
    ],
)
def test_flat_folder_collision_on_disk(tmp_path, layout, first, second):
    root = tmp_path / "root"
    write_capture(root / "A B" / "000", "IMG_0001", range(1, 8))
    write_capture(root / "A_B" / "000", "IMG_0001", range(1, 8))
    dest = tmp_path / "out"
    run(root, records_for(root), dest, layout=layout)
    files = files_under(dest)
    assert first in files and second in files
    # Resuming finds both captures again.
    assert statuses(run(root, records_for(root), dest, layout=layout)) == {"skipped-existing": 14}


def test_folders_layout_keeps_one_folder_per_source_folder(tree, tmp_path):
    dest = tmp_path / "out"
    plan = run(tree, records_for(tree), dest, layout="folders")
    files = files_under(dest)
    assert f"{FIELD_FLAT}/IMG_0000_1.tif" in files
    assert "Saha_Fotoğrafları_Part2_0000SET_000/IMG_0000_7.tif" in files
    assert len(files) == statuses(plan)["copied"] + 1


def test_root_level_captures_keep_their_name(tmp_path):
    root = tmp_path / "root"
    write_capture(root, "IMG_0001", range(1, 8))
    run(root, records_for(root), tmp_path / "out")
    assert "IMG_0001_1.tif" in files_under(tmp_path / "out")


def test_case_insensitive_name_clash_is_refused(tmp_path):
    root = tmp_path / "root"
    write_capture(root / "a", "IMG_0001", range(1, 8))
    write_capture(root / "b", "IMG_0001", range(1, 8))
    records = records_for(root)
    plan = plan_copy(root, records, tmp_path / "out")
    plan.tasks[7].destination = plan.tasks[0].destination.with_name("A_IMG_0001_1.TIF")
    with pytest.raises(CopyError, match="both be written"):
        copy_mod._check_unique_destinations(plan.tasks)


def test_layout_validation(tree, tmp_path):
    with pytest.raises(ValueError, match="layout"):
        plan_copy(tree, [], tmp_path / "out", layout="nested")


def test_missing_bands_copy_what_exists(tmp_path):
    root = tmp_path / "root"
    write_capture(root / "000", "IMG_0001", [1, 2, 3, 5, 6, 7])
    write_capture(root / "000", "IMG_0002", range(1, 8))
    plan = run(root, records_for(root), tmp_path / "out")
    s = plan.summary()
    assert s.incomplete == ["000_IMG_0001"]
    assert s.statuses["copied"] == 13 and s.statuses["missing-band"] == 1
    (missing,) = [t for t in plan.tasks if t.status == "missing-band"]
    assert missing.band == 4 and missing.record_name == "000_IMG_0001"


def test_extra_bands_beyond_bands_option_are_copied(tmp_path):
    root = tmp_path / "root"
    write_capture(root, "IMG_0001", range(1, 8))
    plan = run(root, records_for(root), tmp_path / "out", bands=5)
    assert statuses(plan)["copied"] == 7


def test_matlab_csv_rows_match_by_record_name(tree, tmp_path):
    root = tmp_path / "root"
    write_capture(root / "A B", "IMG_0001", range(1, 8))
    write_capture(root / "A_B", "IMG_0001", range(1, 8))  # same record name as "A B"
    write_capture(root / "C", "IMG_0002", range(1, 8))
    rows = [matlab_record(n) for n in ["C_IMG_0002", "A_B_IMG_0001", "C_IMG_9999"]]
    plan = run(root, rows, tmp_path / "out")
    s = plan.summary()
    assert s.captures == 1
    assert s.ambiguous == ["A_B_IMG_0001"]
    assert s.not_found == ["C_IMG_9999"]
    assert "C_IMG_0002_7.tif" in files_under(tmp_path / "out")


def test_matlab_csv_from_file(tree, tmp_path):
    csv_path = tmp_path / "matlab.csv"
    csv_path.write_text(
        f"RecordName,Complete,GPSLatitude,GPSLongitude\n{FIELD_FLAT}_IMG_0001,1,50.0,10.0\n",
        encoding="utf-8",
    )
    from uav_aoi_subset.core.index import read_index_csv

    plan = run(tree, read_index_csv(csv_path), tmp_path / "out")
    assert statuses(plan)["copied"] == 7
    assert f"{FIELD_FLAT}_IMG_0001_3.tif" in files_under(tmp_path / "out")


def test_record_not_on_disk(tree, tmp_path):
    (record,) = records_for(tree, folders_like="Part2")
    gone = IndexRecord(
        **{
            **record.__dict__,
            "record_name": record.record_name.replace("IMG_0000", "IMG_0777"),
            "image_base": "IMG_0777",
        }
    )
    plan = run(tree, [record, gone], tmp_path / "out")
    assert plan.summary().not_found == [gone.record_name]


def test_duplicate_records_copied_once(tree, tmp_path):
    records = records_for(tree, folders_like="Part2")
    plan = run(tree, records + records, tmp_path / "out")
    assert statuses(plan)["copied"] == 7


# --- dry run, resume, conflicts -----------------------------------------------------------


def test_dry_run_changes_nothing(tree, tmp_path):
    before = files_under(tmp_path)
    dest = tmp_path / "out"
    plan = plan_copy(tree, records_for(tree), dest)
    assert files_under(tmp_path) == before
    assert not dest.exists()
    dry = plan.summary()
    assert dry.statuses["would-copy"] == 7 * 8
    assert plan.bytes_needed == dry.bytes_total

    execute_copy(plan)
    real = plan.summary()
    assert real.statuses["copied"] == dry.statuses["would-copy"]
    assert real.groups_transferred == dry.groups_transferred
    assert real.bytes_transferred == dry.bytes_transferred


def test_resume_skips_same_size_files(tree, tmp_path):
    dest = tmp_path / "out"
    run(tree, records_for(tree), dest)
    plan = run(tree, records_for(tree), dest)
    s = plan.summary()
    assert s.statuses == {"skipped-existing": 56}
    assert s.groups_skipped == 8 and s.groups_transferred == 0
    assert plan.bytes_needed == 0


def test_partial_file_is_not_counted_as_done(tree, tmp_path):
    dest = tmp_path / "out"
    dest.mkdir()
    (dest / OUTPUT_MARKER).write_text("x")
    (dest / (f"{FIELD_FLAT}_IMG_0000_1.tif" + PARTIAL_SUFFIX)).write_bytes(b"half")
    plan = run(tree, records_for(tree, folders_like="0000SET/000"), dest)
    assert statuses(plan)["copied"] == 7 * 4
    assert not list(dest.rglob("*" + PARTIAL_SUFFIX))
    assert (dest / f"{FIELD_FLAT}_IMG_0000_1.tif").stat().st_size == (
        tree / FIELD / "IMG_0000_1.tif"
    ).stat().st_size


def test_conflict_is_never_overwritten_silently(tree, tmp_path):
    dest = tmp_path / "out"
    records = records_for(tree, folders_like="Part2")
    run(tree, records, dest)
    target = dest / "Saha_Fotoğrafları_Part2_0000SET_000_IMG_0000_3.tif"
    target.write_bytes(b"different")

    plan = run(tree, records, dest)
    assert statuses(plan)["conflict"] == 1
    assert target.read_bytes() == b"different"
    (conflict,) = [t for t in plan.tasks if t.status == "conflict"]
    assert "9 bytes" in conflict.message

    plan = run(tree, records, dest, overwrite=True)
    assert statuses(plan)["overwritten"] == 1
    assert target.read_bytes() != b"different"


def test_failed_copy_leaves_no_partial_file(tree, tmp_path, monkeypatch):
    def broken_copy(src, dst):
        Path(dst).write_bytes(b"half")
        raise OSError("disk unplugged")

    monkeypatch.setattr(copy_mod.shutil, "copy2", broken_copy)
    dest = tmp_path / "out"
    plan = run(tree, records_for(tree, folders_like="Part2"), dest)
    assert statuses(plan)["failed"] == 7
    assert "disk unplugged" in plan.tasks[0].message
    assert files_under(dest) == {OUTPUT_MARKER}


def test_interrupted_copy_leaves_no_partial_file(tree, tmp_path, monkeypatch):
    def interrupted(src, dst):
        Path(dst).write_bytes(b"half")
        raise KeyboardInterrupt

    monkeypatch.setattr(copy_mod.shutil, "copy2", interrupted)
    dest = tmp_path / "out"
    with pytest.raises(KeyboardInterrupt):
        run(tree, records_for(tree, folders_like="Part2"), dest)
    assert files_under(dest) == {OUTPUT_MARKER}


# --- modes --------------------------------------------------------------------------------


def test_hardlink(tree, tmp_path):
    dest = tmp_path / "out"
    plan = run(tree, records_for(tree, folders_like="Part2"), dest, mode="hardlink")
    assert statuses(plan)["linked"] == 7
    assert plan.bytes_needed == 0
    source = tree / "Saha Fotoğrafları/Part2/0000SET/000/IMG_0000_1.tif"
    target = dest / "Saha_Fotoğrafları_Part2_0000SET_000_IMG_0000_1.tif"
    assert target.samefile(source)
    assert source.stat().st_nlink == 2
    plan = run(tree, records_for(tree, folders_like="Part2"), dest, mode="hardlink")
    assert statuses(plan) == {"skipped-existing": 7}


def test_hardlink_failure_stops_the_run(tree, tmp_path, monkeypatch):
    def no_links(source, target):
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr(copy_mod, "_link", no_links)
    dest = tmp_path / "out"
    plan = plan_copy(tree, records_for(tree), dest, mode="hardlink")
    with pytest.raises(CopyError, match="--mode copy"):
        execute_copy(plan)
    s = plan.summary()
    assert s.statuses["failed"] == 1 and s.statuses["aborted"] == 55
    assert files_under(dest) == {OUTPUT_MARKER}


def test_hardlink_to_other_drive_refused_before_start(tree, tmp_path, monkeypatch):
    real_stat = Path.stat
    Stat = namedtuple("Stat", "st_size st_dev st_ino")

    def fake_stat(self, **kwargs):
        st = real_stat(self, **kwargs)
        if "Kampanya" in self.parts and self.suffix == ".tif":
            return Stat(st.st_size, st.st_dev + 1, st.st_ino)
        return st

    monkeypatch.setattr(Path, "stat", fake_stat)
    with pytest.raises(CopyError, match="one drive"):
        plan_copy(tree, records_for(tree), tmp_path / "out", mode="hardlink")


def test_move_same_drive(tree, tmp_path):
    records = records_for(tree, folders_like="Part2")
    source = tree / "Saha Fotoğrafları/Part2/0000SET/000/IMG_0000_1.tif"
    data = source.read_bytes()
    dest = tmp_path / "out"
    plan = run(tree, records, dest, mode="move")
    assert statuses(plan)["moved"] == 7
    assert plan.bytes_needed == 0
    assert not source.exists()
    assert (dest / f"Saha_Fotoğrafları_Part2_0000SET_000_{source.name}").read_bytes() == data

    # Running again finds the files at the destination instead of reporting them as lost.
    plan = run(tree, records, dest, mode="move")
    assert statuses(plan) == {"already-at-destination": 7}
    assert plan.summary().not_found == []


@pytest.mark.parametrize("layout", ["flat", "folders"])
def test_move_resume_after_partial_move(tree, tmp_path, layout):
    records = records_for(tree, folders_like="Part2")
    dest = tmp_path / "out"
    folder = tree / "Saha Fotoğrafları/Part2/0000SET/000"
    flat_name = "Saha_Fotoğrafları_Part2_0000SET_000"
    target, prefix = (dest, flat_name + "_") if layout == "flat" else (dest / flat_name, "")
    target.mkdir(parents=True)
    (dest / OUTPUT_MARKER).write_text("x")
    for band in (1, 2):
        (folder / f"IMG_0000_{band}.tif").replace(target / f"{prefix}IMG_0000_{band}.tif")
    plan = run(tree, records, dest, mode="move", layout=layout)
    assert statuses(plan) == {"already-at-destination": 2, "moved": 5}
    assert plan.summary().incomplete == []
    assert len(list(target.glob("*.tif"))) == 7


def test_move_to_other_drive_copies_then_deletes(tree, tmp_path, monkeypatch):
    records = records_for(tree, folders_like="Part2")
    plan = plan_copy(tree, records, tmp_path / "out", mode="move")
    for task in plan.tasks:
        task.same_device = False
    plan.bytes_needed = sum(t.size for t in plan.tasks if t.writes_data)
    assert plan.bytes_needed > 0

    renamed = []
    real_replace = Path.replace

    def spy_replace(self, target):
        renamed.append(Path(self).name)
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", spy_replace)
    execute_copy(plan)
    assert statuses(plan)["moved"] == 7
    assert all(name.endswith(PARTIAL_SUFFIX) for name in renamed)
    assert not list((tree / "Saha Fotoğrafları/Part2").rglob("*.tif"))


# --- destination safety, space ------------------------------------------------------------


def test_dest_inside_root_warns_and_is_not_indexed(tree):
    dest = tree / "subsets" / "north"
    plan = run(tree, records_for(tree, folders_like="Part2"), dest)
    assert any("inside ROOT" in w for w in plan.warnings)
    assert len(discover_captures(tree)) == 8  # copies are not picked up


def test_dest_containing_root_refused(tree):
    with pytest.raises(CopyError, match="contains ROOT"):
        plan_copy(tree, records_for(tree), tree.parent)
    with pytest.raises(CopyError, match="contains ROOT"):
        plan_copy(tree, records_for(tree), tree)


def test_foreign_non_empty_dest_refused(tree, tmp_path):
    dest = tmp_path / "someone_elses"
    dest.mkdir()
    (dest / "notes.txt").write_text("keep me")
    with pytest.raises(CopyError, match="not empty"):
        plan_copy(tree, records_for(tree), dest)
    (tmp_path / "empty").mkdir()
    plan_copy(tree, records_for(tree), tmp_path / "empty")  # an empty folder is fine


def test_not_enough_space(tree, tmp_path, monkeypatch):
    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(copy_mod.shutil, "disk_usage", lambda p: Usage(10, 10, 0))
    dest = tmp_path / "out"
    plan = plan_copy(tree, records_for(tree), dest)
    assert not plan.enough_space
    with pytest.raises(CopyError, match="not enough free space"):
        execute_copy(plan)
    assert not dest.exists()
    # Hard links need no space.
    assert plan_copy(tree, records_for(tree), dest, mode="hardlink").enough_space


def test_long_destination_paths(tree, tmp_path):
    dest = tmp_path / ("d" * 120) / ("e" * 120)
    plan = run(tree, records_for(tree, folders_like="Part2"), dest)
    assert statuses(plan)["copied"] == 7
    assert any("characters long" in w for w in plan.warnings)
    target = dest / "Saha_Fotoğrafları_Part2_0000SET_000_IMG_0000_7.tif"
    assert len(str(target)) > 260
    assert Path(long_path(target)).is_file()


# --- include and extra captures -----------------------------------------------------------


def test_include_globs(tree, tmp_path):
    (tree / "Kalibrasyon").mkdir()
    (tree / "Kalibrasyon" / "panel_reflectance.csv").write_text("nm,r\n550,0.5\n")
    (tree / "Saha Fotoğrafları" / "panel_reflectance.csv").write_text("other")
    elsewhere = tmp_path / "notes" / "flight.txt"
    elsewhere.parent.mkdir()
    elsewhere.write_text("notes")
    dest = tmp_path / "out"
    plan = run(
        tree,
        records_for(tree, folders_like="Part2"),
        dest,
        include=["**/panel_*.csv", str(tmp_path / "notes" / "*.txt"), "nothing*.xyz"],
    )
    assert plan.summary().include_files == 3
    files = files_under(dest)
    assert {"panel_reflectance.csv", "panel_reflectance_v02.csv", "flight.txt"} <= files
    assert (dest / "panel_reflectance.csv").read_text().startswith("nm,r")
    assert any("nothing*.xyz" in w for w in plan.warnings)


def test_include_is_copied_in_move_mode(tree, tmp_path):
    panel = tree / "panel.csv"
    panel.write_text("nm,r\n")
    plan = run(
        tree,
        records_for(tree, folders_like="Part2"),
        tmp_path / "out",
        mode="move",
        include=["panel.csv"],
    )
    assert statuses(plan) == {"moved": 7, "copied": 1}
    assert panel.exists()


def test_extra_captures(tree, tmp_path):
    calib = tree / "Kalibrasyon_Fotograflari"
    write_capture(calib, "IMG_0000", range(1, 8))
    write_capture(calib, "IMG_0001", range(1, 8))
    write_capture(calib, "IMG_0002", range(1, 8))
    names_file = tmp_path / "panels.txt"
    names_file.write_text("# panel shots\nKalibrasyon_Fotograflari_IMG_0001  # after\n\n")
    index_csv = tmp_path / "panels.csv"
    write_index_csv(records_for(tree, folders_like="Kalibrasyon"), index_csv)
    subset = records_for(tree, folders_like="Part2")

    extras = load_extra_captures(["Kalibrasyon_Fotograflari_IMG_0000", str(names_file)])
    assert [r.record_name for r in extras] == [
        "Kalibrasyon_Fotograflari_IMG_0000",
        "Kalibrasyon_Fotograflari_IMG_0001",
    ]
    extras += load_extra_captures([str(index_csv)])  # adds IMG_0000..2 again with folders
    dest = tmp_path / "out"
    plan = run(tree, subset, dest, extra_captures=extras, exclude=["kalibrasyon_*"])
    s = plan.summary()
    assert s.captures == 4  # 1 subset + 3 distinct panel captures
    assert s.statuses["copied"] == 28
    assert {t.kind for t in plan.tasks} == {"capture", "extra"}
    assert "Kalibrasyon_Fotograflari_IMG_0002_1.tif" in files_under(dest)


def test_exclude_applies_to_subset_lookup(tree, tmp_path):
    plan = plan_copy(tree, records_for(tree), tmp_path / "out", exclude=["Part2"])
    assert plan.summary().not_found == ["Saha_Fotoğrafları_Part2_0000SET_000_IMG_0000"]


# --- report -------------------------------------------------------------------------------


def test_report_csv(tree, tmp_path):
    (tree / "panel.csv").write_text("x")
    records = records_for(tree, folders_like="Part2")
    records.append(matlab_record("missing_IMG_0001"))
    plan = run(tree, records, tmp_path / "out", include=["panel.csv"])
    report = tmp_path / "report.csv"
    write_copy_report(plan.tasks, report)
    with report.open(encoding=CSV_ENCODING, newline="") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == REPORT_COLUMNS
    assert len(rows) == 7 + 1 + 1
    first = rows[0]
    assert first["Kind"] == "capture" and first["Band"] == "1" and first["Status"] == "copied"
    assert "Saha Fotoğrafları" in first["Source"]
    assert "Saha_Fotoğrafları_Part2_0000SET_000" in first["Destination"]
    assert int(first["Bytes"]) == Path(first["Source"]).stat().st_size
    assert {r["Status"] for r in rows if r["RecordName"] == "missing_IMG_0001"} == {"not-found"}
    assert [r["Kind"] for r in rows if r["Kind"] == "include"] == ["include"]
    assert report.read_bytes().startswith(b"\xef\xbb\xbf")


def test_mode_validation(tree, tmp_path):
    with pytest.raises(ValueError, match="mode"):
        plan_copy(tree, [], tmp_path / "out", mode="symlink")
    with pytest.raises(ValueError, match="bands"):
        plan_copy(tree, [], tmp_path / "out", bands=0)
