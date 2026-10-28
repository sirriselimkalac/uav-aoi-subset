"""Split large multispectral UAV image sets into subsets inside an area of interest."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("uav-aoi-subset")
except PackageNotFoundError:  # running from a source tree without installation
    __version__ = "0.0.0"
