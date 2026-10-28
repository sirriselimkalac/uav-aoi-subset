"""Synthetic test data: tiny TIFFs in MicaSense-like folder trees."""

from __future__ import annotations

import struct
import subprocess
from collections.abc import Iterable
from pathlib import Path

# Altum-PT layout: <field photos>/<Part>/<####SET>/<000>/IMG_####_<band>.tif
# IMG numbering restarts in every SET folder, so bases repeat across folders.
ALTUM_LAYOUT: dict[str, list[str]] = {
    "Saha Fotoğrafları/Part1/0000SET/000": ["IMG_0000", "IMG_0001", "IMG_0002"],
    "Saha Fotoğrafları/Part1/0000SET/001": ["IMG_0003", "IMG_0004"],
    "Saha Fotoğrafları/Part1/0001SET/000": ["IMG_0000", "IMG_0001"],
    "Saha Fotoğrafları/Part2/0000SET/000": ["IMG_0000"],
}
SET_LOG_FILES = ["diag.dat", "gpslog.dat", "hostlog.dat", "httplog.dat", "paramlog.dat"]


def tiny_tiff_bytes() -> bytes:
    """A valid 1x1 pixel, 8-bit grayscale, uncompressed little-endian TIFF."""
    entries = [
        (256, 3, 1, 1),  # ImageWidth
        (257, 3, 1, 1),  # ImageLength
        (258, 3, 1, 8),  # BitsPerSample
        (259, 3, 1, 1),  # Compression: none
        (262, 3, 1, 1),  # PhotometricInterpretation: BlackIsZero
        (273, 4, 1, 0),  # StripOffsets, patched below
        (277, 3, 1, 1),  # SamplesPerPixel
        (278, 3, 1, 1),  # RowsPerStrip
        (279, 4, 1, 1),  # StripByteCounts
    ]
    ifd_offset = 8
    pixel_offset = ifd_offset + 2 + 12 * len(entries) + 4
    out = bytearray(b"II*\x00" + struct.pack("<I", ifd_offset))
    out += struct.pack("<H", len(entries))
    for tag, typ, count, value in entries:
        if tag == 273:
            value = pixel_offset
        if typ == 3:  # SHORT, left-justified in the 4-byte value field
            out += struct.pack("<HHIHH", tag, typ, count, value, 0)
        else:  # LONG
            out += struct.pack("<HHII", tag, typ, count, value)
    out += struct.pack("<I", 0)  # no next IFD
    out += b"\x80"  # the pixel
    return bytes(out)


def write_capture(folder: Path, base: str, bands: Iterable[int], ext: str = ".tif") -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    data = tiny_tiff_bytes()
    paths = []
    for band in bands:
        path = folder / f"{base}_{band}{ext}"
        path.write_bytes(data)
        paths.append(path)
    return paths


def make_altum_tree(root: Path, n_bands: int = 7) -> None:
    """Build :data:`ALTUM_LAYOUT` with complete captures and camera log files."""
    for rel, bases in ALTUM_LAYOUT.items():
        folder = root / rel
        for base in bases:
            write_capture(folder, base, range(1, n_bands + 1))
        for log in SET_LOG_FILES:
            (folder.parent / log).write_bytes(b"log")


def write_gps(path: Path, lat: float, lon: float, alt: float = 100.0) -> None:
    """Write GPS tags with exiftool (tests using this need the requires_exiftool marker).

    Arguments go through a UTF-8 argfile because Windows mangles non-ASCII command-line
    arguments.
    """
    args = [
        "-q",
        "-overwrite_original",
        f"-GPSLatitude={abs(lat)}",
        f"-GPSLatitudeRef={'S' if lat < 0 else 'N'}",
        f"-GPSLongitude={abs(lon)}",
        f"-GPSLongitudeRef={'W' if lon < 0 else 'E'}",
        f"-GPSAltitude={abs(alt)}",
        f"-GPSAltitudeRef={1 if alt < 0 else 0}",
        "-DateTimeOriginal=2026:07:30 09:00:00",
        str(path),
    ]
    argfile = path.with_name(path.name + ".args")
    argfile.write_text("\n".join(args) + "\n", encoding="utf-8")
    try:
        subprocess.run(["exiftool", "-charset", "filename=utf8", "-@", str(argfile)], check=True)
    finally:
        argfile.unlink()
