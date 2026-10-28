# uav-aoi-subset — project instructions for Claude Code

Talk to the user (Sırrı Selim Kalaç) in **Turkish**. Write all code, comments, docs,
commit messages, CLI help and file/column names in **English** (public repo).

## What this is

A free, open-source tool that splits very large multispectral UAV flight datasets
(MicaSense Altum-PT / RedEdge; 100,000+ images per campaign) into subsets that fall
inside an area of interest (AOI) drawn as a polygon in Google Earth (KML/KMZ), so each
subset can be processed separately in Pix4Dmapper. It replaces commercial tools such as
Global Mapper Pro for this job.

It is step 1 of a pipeline the author is building:
raw captures → **AOI subset (this repo)** → Pix4D processing → ML tiling (separate future repo).

## Reference implementation (MATLAB) — port faithfully, then improve

The working MATLAB originals live one level up, in `../` (NOT part of this repo, never
copy them in — they contain private local paths and project names):

| MATLAB file | Becomes |
|---|---|
| `../BUILD_PROJECT_IMAGE_INDEX.m` | `index` command |
| `../EXPORT_CSV_WITHIN_KML_AREA.m`, `../EXPORT_CSV_WITHIN_KMZ_AREA.m` | `filter` command |
| `../COPY_GEOTIFFS_FROM_CSV.m` | `copy` command |
| `../CSV_TO_MINAREA_POLYGON_KML.m` | `footprint` command (convex hull of all captures → KML) |
| `../EXPORT_TIFF_EXIF_TO_TXT.m` | debugging aid only; maybe `inspect` later |
| `../BUILD_PROJECT_IMAGE_INDEX_NATIVEGPS_v0*.m` | old experiments, ignore unless asked |

Read the relevant `.m` file before implementing each command. Behaviour to preserve:

- **Capture grouping.** MicaSense writes one file per band: `IMG_0000_1.tif … IMG_0000_7.tif`
  in the same folder. A *capture* = folder + `IMG_####` base. Band count must be a
  parameter (`--bands`, default 7 for Altum-PT; RedEdge = 5). The MATLAB index step
  requires exactly 4 digits but the copy step accepts any; use one shared, configurable
  regex in Python.
- **Completeness flag.** For each capture, whether all N band files exist.
- **Position** comes from band 1's EXIF `GPSLatitude` / `GPSLongitude`.
- **Record name** = sanitized relative folder parts joined with `_` + `_IMG_####`
  (spaces and unsafe chars → `_`, collapse repeats, strip). MATLAB used two slightly
  different sanitizers in index vs copy, which forced a fuzzy fallback match in copy.
  In Python use ONE function for both, so matching is exact.
- **Output names** are tied together: index → `<project>_image_index_YYYYMMDD.csv` in the
  project root; filter → `<aoi-name>_image_index_YYYYMMDD.csv` next to the KML;
  copy → output folder named after that CSV.
- **Folder flattening on copy.** Relative folder `A/B/C` becomes a single folder `A_B_C`
  under the output root, so Pix4Dmapper gets a flat, easy-to-import structure (no chains
  of single sub-folders). Name collisions get `_v02`, `_v03`… suffixes.
- **Summary report**: totals, not found, incomplete captures, files copied.
- **KML coordinates** are `lon,lat[,alt]`; multiple polygons are combined with OR.

Known issues in the MATLAB version to fix:

- ExifTool was launched once **per file** (very slow at 100k images) → batch it (see below).
- Hard-coded Windows ExifTool path → find `exiftool` on PATH, allow `--exiftool PATH`.
- KML reader grabbed every `<coordinates>` element (also LineStrings/Points) and ignored
  polygon holes → parse `Polygon` `outerBoundaryIs`/`innerBoundaryIs` and `MultiGeometry`
  properly.
- Copy wrote its output folder *inside* the source root → a later `index` run would pick
  the copies up as duplicates. Default output must be outside the source tree, or the
  indexer must skip known output folders.
- The DMS-string GPS fallback existed because of locale/text parsing problems; using
  `exiftool -json -n` returns plain decimal numbers and should make it unnecessary
  (keep a small, tested DMS parser only if real data needs it).

## Technical decisions (already agreed with the user)

- **Python ≥ 3.11**, managed with **uv** (`uv sync`, `uv run`). `src/` layout,
  package `uav_aoi_subset`, console script `uav-aoi-subset`.
- **Architecture: UI-independent core + thin front ends.**
  `core/` (discovery, exif, index, aoi, filter, copy, report) has no `print`, no `input`,
  no tkinter; it takes plain arguments and reports progress through a callback.
  `cli.py` (argparse, stdlib) and later a tkinter GUI and a QGIS Processing plugin call
  the same core.
- **AOI is a geometry, not a file.** Core filter functions take shapely geometries;
  KML/KMZ reading is a separate loader. (A future QGIS plugin will pass layer geometries.)
- **ExifTool**: external dependency, user installs it (`brew install exiftool`,
  Windows installer, `apt install libimage-exiftool-perl`). Call it via `subprocess` in
  chunks of a few hundred files using an argfile (`-@`) with
  `-json -n -charset filename=utf8 -GPSLatitude -GPSLongitude -GPSAltitude`.
  Keep this behind a small `ExifReader` interface in `core/exif.py` so PyExifTool could be
  swapped in later. Give a clear, actionable error if exiftool is missing.
- Runtime deps kept minimal: `shapely`, `pyproj` (only for metre buffers via local UTM).
  Dev: `pytest`, `ruff`.
- Cross-platform paths (`pathlib`). Must work on macOS, Windows and Linux.
- License: MIT.

## CLI shape (target)

```
uav-aoi-subset index     ROOT [--bands 7] [--pattern ...] [--out CSV]
uav-aoi-subset filter    INDEX_CSV --aoi AREA.kml|.kmz [--buffer METRES] [--out CSV]
uav-aoi-subset copy      ROOT SUBSET_CSV [--dest DIR] [--mode copy|hardlink|move]
                         [--dry-run] [--include FILE_GLOB ...] [--extra-captures ...]
uav-aoi-subset footprint INDEX_CSV [--out KML]
```

`copy` defaults: mode `copy`, skip files already present with the same size (resume),
never overwrite silently, write a CSV report next to the output. `move` must require an
explicit flag. When required arguments are missing and a display is available, fall back
to file/folder pickers (tkinter) — this mirrors the MATLAB `uigetdir`/`uigetfile` UX.

## Milestones

1. **Scaffold**: `uv init --package`, pyproject, ruff, pytest, `.gitignore` (data, *.tif,
   *.zip, outputs, .venv), LICENSE (MIT), README skeleton, GitHub Actions CI
   (ubuntu + macOS + windows, installs exiftool).
2. **index** + tests (tiny synthetic TIFFs written in tests; GPS tags written with exiftool;
   tests needing exiftool are skipped if it's absent).
3. **filter** (KML/KMZ, multipolygon, holes, buffer) + tests.
4. **copy** (flatten, modes, dry-run, resume, report, include globs, extra captures for
   calibration-panel shots) + tests.
5. **footprint**.
6. Picker fallback, progress bars, polished errors.
7. `docs/VALIDATION.md` and a first real-data run on the work computer; fix findings.
8. README with the public EagleNXT Altum-PT blueberry dataset as the worked example
   (link only — never redistribute the data), sample KMLs in `examples/`, screenshots
   from the validation run. Make the repo public and tag **v0.1.0**.
Later: Docker image (secondary distribution), tkinter GUI, QGIS plugin, benchmarks.

## Data and privacy rules

- Never commit imagery, ZIPs, Pix4D outputs or real campaign coordinates. Test data is
  synthetic. Only the user's own example KMLs over the public blueberry dataset go in
  `examples/`.
- **No real imagery on the development machine.** The blueberry dataset is NOT on this
  Mac and must not be requested here. Everything on this machine is tested with small
  synthetic data generated by the test suite.
- Commits use the user's GitHub noreply email (already configured by the user).

## Development and validation workflow (two machines)

- **Development machine: the user's personal Mac** (this one). Code, unit tests and
  synthetic data only. Repo lives at `~/Developer/resimleri_bloklara_ayirma/uav-aoi-subset`
  (outside iCloud). MATLAB references are in the parent folder.
- **Validation machine: the user's work computer (Windows; MATLAB available there).**
  Real-data runs happen only there, after `git clone` / `git pull` from GitHub.
  Dataset: EagleNXT "Altum-PT data of a blueberry field" — 480 captures × 7 bands =
  3,360 TIFFs + 1 calibration-panel reflectance CSV (wavelength 250–950 nm, ~0.5).
- Therefore the code MUST work on Windows: `pathlib` everywhere, no shell-specific
  commands, UTF-8 / Turkish characters in paths, `exiftool.exe` discovery on Windows,
  CI on `windows-latest`.
- Maintain `docs/VALIDATION.md`: a copy-paste checklist for the work computer
  (install uv + ExifTool on Windows, clone, `uv sync`, run index → filter → copy on the
  blueberry data, compare against the MATLAB output CSV, record timings and results).
  The user brings results back; fix issues on the Mac, push, re-validate.
- Expected blueberry sanity numbers: 480 captures indexed, all complete with `--bands 7`.

## Working style

- Before each milestone, propose a short plan; implement in small commits.
- Run `uv run ruff check`, `uv run ruff format`, `uv run pytest` before saying done.
- Ask before deleting files or rewriting git history.
