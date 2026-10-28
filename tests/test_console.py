import io

import pytest

from uav_aoi_subset.console import ConsoleProgress, format_duration


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def _progress(is_terminal):
    stream, clock = io.StringIO(), Clock()
    return ConsoleProgress(stream, clock, is_terminal=is_terminal), stream, clock


def test_format_duration():
    assert format_duration(0) == "0:00:00"
    assert format_duration(72.4) == "0:01:12"
    assert format_duration(3 * 3600 + 5) == "3:00:05"


def test_terminal_bar_uses_carriage_return_only(monkeypatch):
    monkeypatch.setenv("COLUMNS", "100")
    progress, stream, clock = _progress(is_terminal=True)
    progress("exif", 0, 3360)
    clock.now += 10
    progress("exif", 1680, 3360)
    text = stream.getvalue()
    assert "\x1b" not in text  # no ANSI escape codes
    assert "\n" not in text  # one self-overwriting line
    last = text.split("\r")[-1]
    assert "Reading GPS" in last
    assert "[############------------]  50%" in last
    assert "1,680/3,360" in last
    assert "ETA 0:00:10" in last
    assert len(last) == 99  # never writes into the last column

    clock.now += 10
    progress("exif", 3360, 3360)
    progress.finish()
    final = stream.getvalue().split("\r")[-1]
    assert "100%" in final and "0:00:20" in final and final.endswith("\n")


def test_terminal_eta_waits_for_a_rate(monkeypatch):
    monkeypatch.setenv("COLUMNS", "100")
    progress, stream, clock = _progress(is_terminal=True)
    clock.now += 0.5
    progress("copy", 10, 1000)
    assert "ETA --:--" in stream.getvalue()


def test_terminal_redraws_are_throttled(monkeypatch):
    monkeypatch.setenv("COLUMNS", "100")
    progress, stream, clock = _progress(is_terminal=True)
    for i in range(1, 500):
        clock.now += 0.0001
        progress("copy", i, 1000)
    assert stream.getvalue().count("\r") == 1


def test_terminal_unknown_total_and_stage_change(monkeypatch):
    monkeypatch.setenv("COLUMNS", "100")
    progress, stream, clock = _progress(is_terminal=True)
    progress("scan", 12345, None)
    clock.now += 8
    progress("exif", 0, 10)
    lines = stream.getvalue().split("\n")
    assert "Scanning folders: 12,345 files  0:00:08" in lines[0]
    assert "Reading GPS" in lines[1]


def test_log_lines_when_not_a_terminal():
    progress, stream, clock = _progress(is_terminal=False)
    progress("exif", 0, 3360)
    for done in range(1, 3361):
        clock.now += 0.01
        progress("exif", done, 3360)
    progress.finish()
    lines = stream.getvalue().splitlines()
    assert "\r" not in stream.getvalue()
    assert lines[0] == "Reading GPS: started"
    percents = [line.split(": ")[1].split("%")[0] for line in lines[1:]]
    assert percents == [str(p) for p in range(0, 101, 10)]
    assert lines[4] == "Reading GPS: 30% (1,008/3,360), 0:00:10 elapsed"
    assert lines[-1].startswith("Reading GPS: 100% (3,360/3,360)")


def test_log_lines_for_unknown_total():
    progress, stream, clock = _progress(is_terminal=False)
    for done in range(1, 31):
        clock.now += 1
        progress("scan", done * 1000, None)
    progress.finish()
    assert stream.getvalue().splitlines() == [
        "Scanning folders: started",
        "Scanning folders: 1,000 files, 0:00:00 elapsed",
        "Scanning folders: 11,000 files, 0:00:10 elapsed",
        "Scanning folders: 21,000 files, 0:00:20 elapsed",
        "Scanning folders: 30,000 files, 0:00:29 elapsed",
    ]


@pytest.mark.parametrize("is_terminal", [True, False])
def test_finish_without_progress_writes_nothing(is_terminal):
    progress, stream, _ = _progress(is_terminal)
    progress.finish()
    assert stream.getvalue() == ""


def test_detects_terminal_from_stream():
    assert ConsoleProgress(io.StringIO()).is_terminal is False
