import subprocess
import sys

import pytest

from uav_aoi_subset import __version__
from uav_aoi_subset.cli import main

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
