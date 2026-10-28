import shutil

import pytest


def pytest_collection_modifyitems(config, items):
    if shutil.which("exiftool"):
        return
    skip = pytest.mark.skip(reason="exiftool not found on PATH")
    for item in items:
        if "requires_exiftool" in item.keywords:
            item.add_marker(skip)
