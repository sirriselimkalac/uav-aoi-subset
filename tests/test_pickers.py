"""Picker fallback. No real dialog is ever opened: the ask_* functions are replaced."""

import shlex
import sys
import threading
import types
from pathlib import Path

import pytest
from synthetic import kml_document, polygon_kml, square
from test_cli import FILTER_RECORDS

from uav_aoi_subset import pickers
from uav_aoi_subset.cli import equivalent_command, main
from uav_aoi_subset.core.filter import default_subset_path
from uav_aoi_subset.core.index import read_index_csv, write_index_csv

REAL_PICKERS_AVAILABLE = pickers.pickers_available


class _Tty:
    def isatty(self):
        return True


@pytest.fixture
def interactive(monkeypatch):
    """Conditions under which pickers are allowed."""
    monkeypatch.delenv(pickers.ENV_NO_PICKER, raising=False)
    monkeypatch.setattr(sys, "stdin", _Tty())
    monkeypatch.setattr(sys, "platform", "darwin")
    # Some CI Pythons ship without tkinter; the check only needs the import to succeed.
    monkeypatch.setitem(sys.modules, "tkinter", types.ModuleType("tkinter"))


@pytest.fixture
def filter_files(tmp_path):
    index_csv = tmp_path / "project" / "project_image_index_20261028.csv"
    index_csv.parent.mkdir()
    write_index_csv(FILTER_RECORDS, index_csv)
    aoi = tmp_path / "aoi" / "Kuzey Tarla.kml"
    aoi.parent.mkdir()
    aoi.write_text(kml_document(polygon_kml(square(10.0, 50.0, 0.01))), encoding="utf-8")
    return index_csv, aoi


class FakePickers:
    """Records every picker call and answers from a queue (None = cancel)."""

    def __init__(self, monkeypatch, *answers):
        self.answers = list(answers)
        self.calls = []
        monkeypatch.setattr(pickers, "pickers_available", lambda no_picker=False: not no_picker)
        monkeypatch.setattr(pickers, "ask_folder", self.folder)
        monkeypatch.setattr(pickers, "ask_open_file", self.file)

    def _answer(self):
        answer = self.answers.pop(0)
        if answer is None:
            raise pickers.PickerCancelled
        return Path(answer)

    def folder(self, title, initialdir=None):
        self.calls.append(("folder", title, initialdir))
        return self._answer()

    def file(self, title, filetypes, initialdir=None):
        self.calls.append(("file", title, initialdir))
        return self._answer()


# --- when pickers are offered ---------------------------------------------------------


def test_available_when_interactive(interactive):
    assert pickers.pickers_available() is True


def test_not_available_with_flag_or_env(interactive, monkeypatch):
    assert pickers.pickers_available(no_picker=True) is False
    monkeypatch.setenv(pickers.ENV_NO_PICKER, "1")
    assert pickers.pickers_available() is False
    monkeypatch.setenv(pickers.ENV_NO_PICKER, "0")
    assert pickers.pickers_available() is True


def test_not_available_without_terminal(interactive, monkeypatch):
    class NotTty:
        def isatty(self):
            return False

    monkeypatch.setattr(sys, "stdin", NotTty())
    assert pickers.pickers_available() is False
    monkeypatch.setattr(sys, "stdin", None)
    assert pickers.pickers_available() is False


def test_not_available_on_linux_without_display(interactive, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert pickers.pickers_available() is False
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert pickers.pickers_available() is True


def test_not_available_without_tkinter(interactive, monkeypatch):
    monkeypatch.setitem(sys.modules, "tkinter", None)  # makes "import tkinter" fail
    assert pickers.pickers_available() is False


def test_not_available_off_the_main_thread(interactive):
    result = []
    thread = threading.Thread(target=lambda: result.append(pickers.pickers_available()))
    thread.start()
    thread.join()
    assert result == [False]


def test_tests_never_offer_pickers():
    # pytest's stdin is not a terminal, so a forgotten monkeypatch cannot open a window.
    assert pickers.pickers_available() is False


# --- command line ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("argv", "names"),
    [
        (["index"], "ROOT"),
        (["filter"], "INDEX_CSV, --aoi"),
        (["copy"], "ROOT, SUBSET_CSV"),
        (["footprint"], "INDEX_CSV"),
    ],
)
def test_missing_paths_without_display_is_a_usage_error(argv, names, capsys):
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert f"the following arguments are required: {names}" in err
    assert "usage:" in err


def test_no_picker_flag_and_env_never_call_pickers(monkeypatch, capsys):
    fake = FakePickers(monkeypatch)
    with pytest.raises(SystemExit) as exc:
        main(["index", "--no-picker"])
    assert exc.value.code == 2
    assert fake.calls == []

    # With the real check, the environment variable alone switches pickers off.
    monkeypatch.setattr(pickers, "pickers_available", REAL_PICKERS_AVAILABLE)
    monkeypatch.setattr(sys, "stdin", _Tty())
    monkeypatch.setenv(pickers.ENV_NO_PICKER, "1")
    with pytest.raises(SystemExit) as exc:
        main(["index"])
    assert exc.value.code == 2
    assert fake.calls == []


def test_filter_pickers_in_order_with_same_result(filter_files, monkeypatch, capsys):
    index_csv, aoi = filter_files
    fake = FakePickers(monkeypatch, index_csv, aoi)
    assert main(["filter", "--buffer", "0"]) == 0

    # CSV first, then the AOI picker opens in the CSV's folder.
    assert [c[0] for c in fake.calls] == ["file", "file"]
    assert "CSV" in fake.calls[0][1] and "AOI" in fake.calls[1][1]
    assert fake.calls[0][2] is None
    assert fake.calls[1][2] == index_csv.parent

    out = capsys.readouterr().out
    line = next(x for x in out.splitlines() if x.startswith("Equivalent command: "))
    assert line == (
        f'Equivalent command: uav-aoi-subset filter "{index_csv}" --buffer 0 --aoi "{aoi}"'
    )
    picked_result = read_index_csv(default_subset_path(aoi))
    assert [r.record_name for r in picked_result] == ["P_IMG_0000", "P_IMG_0002"]

    # Running the printed command (without pickers) gives the same subset.
    default_subset_path(aoi).unlink()
    tokens = shlex.split(line.removeprefix("Equivalent command: "), posix=sys.platform != "win32")
    tokens = [t.strip('"') for t in tokens]
    assert main([*tokens[1:], "--no-picker"]) == 0
    assert read_index_csv(default_subset_path(aoi)) == picked_result


def test_only_the_missing_path_is_asked(filter_files, monkeypatch, capsys):
    index_csv, aoi = filter_files
    fake = FakePickers(monkeypatch, aoi)
    assert main(["filter", str(index_csv)]) == 0
    assert fake.calls == [("file", "Select the AOI polygon (KML/KMZ)", index_csv.parent)]
    out = capsys.readouterr().out
    assert str(index_csv) in out
    assert f'--aoi "{aoi}"' in out


def test_copy_asks_root_then_csv_in_root(tmp_path, monkeypatch, capsys):
    root = tmp_path / "project"
    root.mkdir()
    fake = FakePickers(monkeypatch, root, None)
    assert main(["copy", "--dry-run"]) == 1
    assert fake.calls[0] == ("folder", "Select the project root folder", None)
    assert fake.calls[1] == ("file", "Select the subset CSV", root)
    captured = capsys.readouterr()
    assert "Cancelled: no file selected; nothing was done." in captured.err
    assert "Equivalent command" not in captured.out


def test_cancel_exits_1(monkeypatch, capsys):
    FakePickers(monkeypatch, None)
    assert main(["index"]) == 1
    assert "Cancelled: no folder selected" in capsys.readouterr().err


def test_picker_that_cannot_open_is_a_usage_error(monkeypatch, capsys):
    FakePickers(monkeypatch)

    def broken(title, initialdir=None):
        raise pickers.PickerUnavailable("no display name")

    monkeypatch.setattr(pickers, "ask_folder", broken)
    with pytest.raises(SystemExit) as exc:
        main(["index"])
    assert exc.value.code == 2
    assert "no file picker could be opened" in capsys.readouterr().err


# --- equivalent command ---------------------------------------------------------------


def test_equivalent_command_quoting():
    root, csv = Path("/data/Saha Fotoğrafları"), Path("/a/b.csv")
    assert (
        equivalent_command(
            ["copy", "--dry-run", "--include", "**/*.csv"], [("ROOT", root), ("SUBSET_CSV", csv)]
        )
        == f'uav-aoi-subset copy "{root}" "{csv}" --dry-run --include "**/*.csv"'
    )


def test_equivalent_command_keeps_positional_order():
    # ROOT typed after an option, SUBSET_CSV picked: the CSV must follow ROOT.
    command = equivalent_command(
        ["copy", "--dry-run", "proj"], [("SUBSET_CSV", Path("s.csv"))], typed=[Path("proj")]
    )
    assert command == 'uav-aoi-subset copy --dry-run proj "s.csv"'
