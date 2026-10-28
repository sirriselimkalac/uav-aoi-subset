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

Real-world folder layout (Altum-PT, as seen on the author's campaign drives):

```
<CAMPAIGN>/                       project root; also holds calibration, Pix4D, flight-plan folders
└─ <field photos>/Part1, Part2    created by hand
   └─ 0000SET, 0001SET …          created by the camera, one per battery change
      ├─ diag.dat, gpslog.dat …   camera logs (ignored)
      └─ 000, 001 …               one per 1,400 files = 200 captures × 7 bands
         └─ IMG_0000_1.tif …
```

IMG numbering restarts in every SET, so `IMG_####` alone is never unique: capture identity is
always relative folder + base, at any nesting depth (other sensors may nest differently).
Calibration-panel captures use the same naming in a sibling folder → `index --exclude`.
Never put real campaign/project names in the repo.

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
uav-aoi-subset index     ROOT [--bands 7] [--pattern ...] [--exclude DIR_GLOB ...] [--out CSV]
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
7. **Real-data validation on the work computer** following `docs/VALIDATION.md`; record the
   results there, fix findings on the Mac, re-validate. Best done once milestones 1–6 are all
   finished, so a single visit covers every command.
8. **README assets and README**: after all checks pass, prepare the example KMLs and the
   screenshots on the work computer (list in `docs/RELEASE.md` section A) and push them from
   there; then finish the README on the Mac (worked example with the public EagleNXT Altum-PT
   blueberry dataset, link only, never redistribute the data).
9. **Public gate** (`docs/RELEASE.md` section B): make the repo public and tag **v0.1.0** ONLY
   when every check in `docs/VALIDATION.md` has passed on the commit to be tagged (or fixes
   since were re-validated), the assets are committed and the README is complete. The user
   does not want untested code to be public. Never make the repo public earlier, and never
   suggest doing so.
Later: Docker image (secondary distribution), tkinter GUI, QGIS plugin, benchmarks.

## Status (update at the end of each milestone)

Done: **1 scaffold**, **2 index** (CI green on ubuntu/macOS/windows × Python 3.11/3.12),
**3 filter** (CI green on all 6 jobs, 94 tests), **4 copy** (CI green on all 6 jobs, 136 tests).
Package version is `0.0.1` until the v0.1.0 tag (milestone 8). Repo is private until then.

Decisions made so far:
- `core/discovery.py` holds the ONE sanitizer (`sanitize_token`, `flat_folder_name`,
  `record_name`); `copy` must reuse it for folder flattening and exact matching.
- Capture key = relative folder + image base, any depth. Pattern regex needs groups `base`
  and `band` and is matched case-insensitively. Captures without band 1 are still listed
  (incomplete, no position).
- Skipped while indexing: hidden folders, `--exclude` globs (case-insensitive on every OS,
  matched against the folder name or the `/`-joined relative path), and any folder containing
  the `OUTPUT_MARKER` file `.uav-aoi-subset-output`.
- Index CSV: `RecordName, Complete (1/0), GPSLatitude, GPSLongitude` (same as MATLAB), then
  `GPSAltitude, CaptureTime, BandsFound, MissingBands` (`;`-separated), `RelativeFolder` (`/`),
  `ImageBase`. Written as `utf-8-sig` (Excel). `read_index_csv` also reads MATLAB CSVs.
- ExifTool: chunks of 500, `-json -n -q`; coordinate sign taken from the Ref tags; output
  matched back to the inputs by normalised `SourceFile` path; unreadable files → no position.
- **Windows:** never put a non-ASCII path on a subprocess command line. Pass data through a
  UTF-8 argfile and refer to the argfile by its ASCII name with `cwd=` set to its folder.
  Windows CI caught this.
- Tests: synthetic TIFFs from `tests/synthetic.py` (`ALTUM_LAYOUT` mirrors the real tree,
  `write_gps` uses exiftool); `requires_exiftool` marker skips tests when exiftool is absent.

- AOI (`core/aoi.py`): only `Polygon` elements are areas (outer = shell, inner = holes), at any
  depth incl. `MultiGeometry`; combined with `union_all`. LineStrings/Points/loose LinearRings
  are ignored and counted. Namespace-agnostic (match on local tag name; `ET.iter` has no
  `{*}`). KMZ read in memory: root `doc.kml`, else first root `.kml`, else any. Invalid
  polygons → `make_valid` + warning. No polygon → `AOIError`.
- Filter (`core/filter.py`, geometry only, no files): `shapely.intersects_xy` → **boundary
  counts as inside** (like MATLAB `inpolygon`). Records without GPS are never inside and are
  reported. `buffer_metres` uses the UTM zone of the AOI centroid; negative shrinks, an empty
  result raises `ValueError`.
- Subset CSV = same columns/writer as the index CSV, named `<sanitize_token(AOI stem)>_image_index_
  YYYYMMDD.csv` next to the AOI. `filter` refuses to overwrite its input; an empty result
  still writes a header-only CSV (exit 0, warning). Runtime deps: shapely, pyproj, numpy.

- Copy (`core/copy.py`): `plan_copy` (no disk writes; is also the dry run) → `execute_copy`.
  One `discover_captures` walk; match on `(NFC RelativeFolder, ImageBase.upper())`, MATLAB CSVs
  on exact NFC `RecordName` (2+ candidates → `ambiguous`, no fuzzy scoring). Extra captures are
  looked up WITHOUT `--exclude`. `assign_flat_folders`: sorted, case-insensitive collisions →
  `_v02`. Default dest `<ROOT parent>/<ROOT name>_subsets/<CSV stem>`; refuses a non-empty dest
  without `OUTPUT_MARKER` and a dest that contains ROOT; warns if inside ROOT. Writes go to
  `<name>.uas-partial` then `replace`. Same size → `skipped-existing`; different size →
  `conflict` (exit 1) unless `--overwrite`. Hardlink: other drive (per-file `st_dev`) refused at
  plan time, a failed link aborts the run — never falls back to copying. Move needs
  `--confirm-move`; cross-drive = copy + verify + delete; bands already at the dest →
  `already-at-destination`. Include files are copied (never moved) to the dest root. Free space
  must be ≥ needed × 1.02 + 100 MB. All file-system calls go through `long_path` (`\\?\` on
  Windows); paths > 259 chars give a Pix4D warning. Report CSV columns `Kind, RecordName, Band,
  Source, Destination, Status, Bytes, Message`, written next to the dest with a timestamp; dry
  runs write it only with `--report`.

Validation prep is in place: `docs/VALIDATION.md` (work-computer checklist, covers milestones
2–6), `docs/RELEASE.md` (README asset list + public gate), `scripts/compare_outputs.py`,
`.gitattributes` (LF in the repo, also for commits from Windows). Not yet run on real data.

Next: milestone 5 (`footprint`). Watch out for:
- Read `../CSV_TO_MINAREA_POLYGON_KML.m` first. It takes the convex hull of all valid lat/lon
  (MATLAB projected to a local equirectangular plane first) and writes one KML polygon named
  after the CSV, next to it (`<csv stem>.kml`).
- Read the CSV with `read_index_csv` (MATLAB CSVs too); skip records without a position and
  report how many; need ≥ 3 non-collinear points, else a clear error.
- Core: a pure `footprint(records) -> Polygon` (shapely `convex_hull` on lon/lat is fine at field
  scale; optionally a `--buffer` in metres via `filter.buffer_metres`) and a separate KML writer
  (`lon,lat,0`, closed ring, counter-clockwise outer ring, `xmlns` KML 2.2, UTF-8). Keep the writer
  reusable, and check the output loads with our own `load_aoi` (round-trip test).
- Never overwrite the input CSV or an existing KML silently.

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
- `docs/VALIDATION.md` is the copy-paste checklist for the work computer (check IDs `V…`,
  results table at the end). Running it is the FIRST thing to do whenever the repo is pulled
  there. Keep it up to date: when a command or flag changes, update the affected checks in the
  same commit. `scripts/compare_outputs.py` compares our CSVs and copy folders with the MATLAB
  outputs.
- **The work-computer clone is temporary.** It is deleted after validation and the README
  assets are done (VALIDATION.md section 9), including the stored GitHub credentials. Only the
  Mac copy remains. Therefore everything produced there (results, KMLs, screenshots) must be
  committed and pushed from there, data and outputs stay outside the clone
  (`C:\uav-demo\data`, `C:\uav-demo\results`), and the clone uses a repo-local git identity
  with the noreply email. Results contain numbers only: no coordinates, no work paths or names.
- If Claude Code runs on the work computer: start with `docs/VALIDATION.md`, never commit data
  or outputs, and push results before anything is deleted.
- Expected blueberry sanity numbers: 480 captures indexed, all complete with `--bands 7`.

## Working style

- Before each milestone, propose a short plan; implement in small commits.
- Run `uv run ruff check`, `uv run ruff format`, `uv run pytest` before saying done.
- Ask before deleting files or rewriting git history.
