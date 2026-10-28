import subprocess
import sys
from pathlib import Path

from uav_aoi_subset.core.discovery import OUTPUT_MARKER

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compare_outputs.py"

HEADER = "RecordName,Complete,GPSLatitude,GPSLongitude\n"


def run(*args):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.returncode, result.stdout


def test_csv_same_within_tolerance(tmp_path):
    ours = tmp_path / "ours.csv"
    matlab = tmp_path / "matlab.csv"
    ours.write_text(HEADER + "A_IMG_0001,1,50.0,10.0\nA_IMG_0002,0,,\n", encoding="utf-8")
    matlab.write_text(HEADER + "A_IMG_0001,1,50.0000001,10.0\nA_IMG_0002,0,NaN,NaN\n")
    code, out = run("csv", ours, matlab)
    assert code == 0, out
    assert "RESULT: SAME" in out


def test_csv_differences(tmp_path):
    ours = tmp_path / "ours.csv"
    matlab = tmp_path / "matlab.csv"
    ours.write_text(HEADER + "A_IMG_0001,1,50.0,10.0\nA_IMG_0002,1,50.0,10.0\n")
    matlab.write_text(HEADER + "A_IMG_0001,0,50.001,10.0\nA_IMG_0003,1,50.0,10.0\n")
    code, out = run("csv", ours, matlab)
    assert code == 1
    assert "Only in ours: 1" in out and "Only in MATLAB: 1" in out
    assert "Complete flag differs: 1" in out
    assert "more than 0.05 m: 1" in out


def test_tree(tmp_path):
    ours, matlab = tmp_path / "ours", tmp_path / "matlab"
    for root in (ours, matlab):
        (root / "A_B").mkdir(parents=True)
        (root / "A_B" / "IMG_0001_1.tif").write_bytes(b"x")
    (ours / OUTPUT_MARKER).write_text("marker")
    assert run("tree", ours, matlab)[0] == 0
    (matlab / "A_B" / "IMG_0001_2.tif").write_bytes(b"x")
    code, out = run("tree", ours, matlab)
    assert code == 1 and "Only in MATLAB: 1" in out
