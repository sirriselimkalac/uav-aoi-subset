# uav-aoi-subset

[![CI](https://github.com/sirriselimkalac/uav-aoi-subset/actions/workflows/ci.yml/badge.svg)](https://github.com/sirriselimkalac/uav-aoi-subset/actions/workflows/ci.yml)

Split very large drone image datasets (for example multispectral cameras that write one
file per band, 100,000+ images per campaign) into subsets that fall inside an area of
interest (AOI) drawn as a polygon in Google Earth or any GIS (KML/KMZ), so that each subset
can be processed separately in your photogrammetry software.

A free, open-source alternative to commercial GIS tools for this one job.

<!-- AUTHOR: "Why this tool exists" — 2-3 sentences in your own words: the field problem
     you hit (dataset too large to process in one go, splitting by hand, paying for a GIS
     licence only for this step) and why you built this. Keep it free of brand names. -->

> **Status:** work in progress, not yet validated on real data. `index`, `filter`, `copy`
> and `footprint` work. The command-line interface below is the target shape.

## Where it fits

```
raw captures  →  AOI subset (this tool)  →  photogrammetry  →  ML tiling
```

## How it works

1. **index**: scan a flight folder tree at any depth, group the per-band files
   (`IMG_0000_1.tif … IMG_0000_7.tif`) into captures, check that every band is present and
   read the capture position from the GPS tags of band 1. A capture is identified by its
   folder *and* image number, because some cameras restart numbering in every
   `####SET` folder. Use `--exclude 'Calibration*'` to skip folders such as
   calibration-panel shots.
2. **filter**: keep the captures that fall inside one or more AOI polygons (KML/KMZ, with
   holes and an optional buffer in metres).
3. **copy**: copy (or hard-link) the band files of the selected captures into one new
   folder next to the project (`<project>_subset_01`, `_02`, …), each file named after its
   folder chain (`Part1/0000SET/000/IMG_0000_1.tif` → `Part1_0000SET_000_IMG_0000_1.tif`)
   so your photogrammetry software gets a single folder of images, and write a report.
4. **footprint**: write the outline of all capture positions as a KML polygon (convex or
   concave, optionally buffered, optionally one polygon per flight folder), which helps when
   you draw the AOIs and can itself be used as an AOI.

## Positional accuracy: what the tool selects by

Read this before you rely on a subset.

**The position used is where the camera was, not what the image shows.** Each capture is
selected by the GNSS position stored in its EXIF tags: the latitude and longitude recorded
when the shutter fired, i.e. the camera's position in the air. It is *not* the ground
position of the image centre, and *not* a corner coordinate as in a world file (`.tfw`).
The altitude tag is not used.

A capture is kept when this single point lies inside the AOI. Because an image covers an
area, and that area is not always centred under the camera, the selected images and the
area you drew never match exactly:

- **Image footprint.** An image covers roughly *flight height × sensor width ÷ focal
  length* across. A camera with an 8 mm lens and a 7.1 mm wide sensor at 100 m above
  ground covers about 89 m × 67 m. Images whose position lies just outside the AOI may
  still show parts of it and are left out; images just inside also show ground outside it.
- **Camera tilt.** If the camera does not point straight down (wind, turns, no gimbal), the
  image centre moves by about *height × tan(tilt)*: around 9 m at 100 m for a 5° tilt.
- **GNSS accuracy.** Standard receivers are accurate to a few metres; RTK/PPK systems to
  centimetres.

**Effect on processed products.** Photogrammetry builds the edges of a mosaic from fewer
overlapping images, so the product made from a subset is usually a little smaller than, or
slightly offset from, the AOI, and its quality drops towards the edges.

**What to do**

- Draw the AOI larger than the area you need, or use `filter --buffer`. As a rule of thumb,
  buffer by at least half the image footprint width, or by one to two flight-line spacings.
- After processing, crop the final product to the exact AOI in your GIS software.
- Use `footprint` and `copy --dry-run` to check the coverage and the capture count before
  copying.

The tool does not compute true image footprints. That would need the camera model, the
camera attitude and a terrain model for every image, which is outside the scope of this
tool.

<!-- AUTHOR (optional): one sentence from your own field experience, e.g. the buffer you use
     in practice and the offset you saw between a subset's mosaic and the AOI. Fill in after
     the real-data validation. -->

## Requirements

- [uv](https://docs.astral.sh/uv/) (it installs a suitable Python, 3.11 or newer)
- [ExifTool](https://exiftool.org/) on your `PATH`:
  - macOS: `brew install exiftool`
  - Windows: the installer from [exiftool.org](https://exiftool.org/) or `choco install exiftool`
  - Debian/Ubuntu: `sudo apt install libimage-exiftool-perl`

## Installation

```bash
git clone https://github.com/sirriselimkalac/uav-aoi-subset.git
cd uav-aoi-subset
uv sync
uv run uav-aoi-subset --help
```

## Usage (target)

```
uav-aoi-subset index     ROOT [--bands 7] [--pattern ...] [--exclude DIR_GLOB ...] [--out CSV]
uav-aoi-subset filter    INDEX_CSV --aoi AREA.kml|.kmz [--buffer METRES] [--out CSV]
uav-aoi-subset copy      ROOT SUBSET_CSV [--dest DIR] [--mode copy|hardlink|move]
                         [--layout flat|folders] [--dry-run] [--include FILE_GLOB ...]
                         [--extra-captures ...]
uav-aoi-subset footprint INDEX_CSV [--out KML] [--hull convex|concave] [--ratio R]
                         [--buffer METRES] [--per-folder [DEPTH]] [--overwrite]
```

`filter` reads every Polygon in the KML/KMZ (also inside folders and multi-geometries),
combines them, and leaves out captures inside polygon holes. Points on the boundary count
as inside. `--buffer 20` grows the area by 20 m (computed in the local UTM zone); a negative
value shrinks it. The output has the same columns as the index CSV and is written next to
the AOI file as `<AOI name>_image_index_YYYYMMDD.csv`.

## Development

```bash
uv sync
uv run ruff check
uv run ruff format
uv run pytest
```

Tests use small synthetic images generated by the test suite. Tests that need ExifTool
are skipped when it is not installed.

## How this was built

<!-- AUTHOR: write this in your own words. Suggested wording:
     "Ported from my original MATLAB tools. Developed with Claude Code as a coding
     assistant; design decisions, validation against the MATLAB version and real-data
     testing by the author." -->

## Author

<!-- AUTHOR: one or two lines about yourself and a contact link (LinkedIn: sirriselimkalac).
     Optionally: how you would like the tool to be cited, and acknowledgements
     (e.g. the provider of the example dataset). -->

## License

[MIT](LICENSE)
