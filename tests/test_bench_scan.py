import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "bench_scan.py"


def test_bench_scan_finds_every_capture_and_cleans_up(tmp_path):
    args = ["--captures", "450", "--other", "1200", "--dir", str(tmp_path)]
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, encoding="utf-8"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Captures:  450 (expected 450)" in result.stdout
    assert "files/s" in result.stdout
    assert list(tmp_path.iterdir()) == []
