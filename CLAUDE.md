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
  copy → a new `<project>_subset_NN` folder next to the project root (first free number, so
  runs with different AOIs never write into each other; the user asked for this in
  milestone 5, replacing MATLAB's "folder named after the CSV"); footprint → `<csv stem>.kml`.
- **Flattening on copy.** Default `--layout flat` (the user's choice in milestone 5): every
  file lands directly in the output folder, named after its folder chain
  (`A/B/C/IMG_0000_1.tif` → `A_B_C_IMG_0000_1.tif`), so Pix4Dmapper gets one folder of
  images. `--layout folders` keeps MATLAB's one folder per source folder (`A_B_C/IMG_…`).
  Folder-name collisions get `_v02`, `_v03`… suffixes in both layouts.
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
                         [--layout flat|folders] [--dry-run] [--include FILE_GLOB ...]
                         [--extra-captures ...]
uav-aoi-subset footprint INDEX_CSV [--out KML] [--hull convex|concave] [--ratio R]
                         [--buffer METRES] [--per-folder [DEPTH]] [--overwrite]
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
7. **Real-data validation on the work computer** following `docs/VALIDATION.md`, in five
   phases: (1) install from the README only, (2) blueberry dataset, (3) same data with unusual
   KMLs, (4) real campaign data (anonymous numbers only), (5) real data with ROOT one level too
   high. Record the results there, file every finding as an issue with the bug report form, fix
   on the Mac, re-validate.
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
**3 filter** (CI green on all 6 jobs, 94 tests), **4 copy** (CI green on all 6 jobs, 136 tests),
**5 footprint** + copy `_subset_NN` / `--layout` (CI green on all 6 jobs, 183 tests),
**6 pickers, progress, polished errors** (CI green on all 6 jobs, 225 tests),
**pre-validation hardening** (system/unreadable folders, links, drive roots, duplicate captures,
scan benchmark; Windows README; bug report form; five-phase VALIDATION.md; CI green on all
6 jobs, 249 tests).
**one-folder example data + layered-copy helper** (`examples/make_layered_dataset.py`, README
section, VALIDATION Phase 3B; CI green on all 6 jobs, 276 tests).
Package version is `0.0.1` until the v0.1.0 tag (milestone 8). Repo is private until then.

Decisions made so far:
- `core/discovery.py` holds the ONE sanitizer (`sanitize_token`, `flat_folder_name`,
  `record_name`); `copy` must reuse it for folder flattening and exact matching.
- Capture key = relative folder + image base, any depth. Pattern regex needs groups `base`
  and `band` and is matched case-insensitively. Captures without band 1 are still listed
  (incomplete, no position).
- Skipped while indexing: hidden folders, `--exclude` globs (case-insensitive on every OS,
  matched against the folder name or the `/`-joined relative path), and any folder containing
  the `OUTPUT_MARKER` file `.uav-aoi-subset-output`. Also, silently: `SYSTEM_FOLDERS`
  (`$RECYCLE.BIN`, `System Volume Information`) and folders with BOTH the Windows hidden and
  system attributes (system alone is not enough: customised user folders can have it).
  Linked folders are never followed: symlinks and Windows junctions (`st_reparse_tag` mount
  point / symlink only, so cloud-sync placeholders are not mistaken for links), plus a visited
  `(st_dev, st_ino)` set. Unreadable folders (`os.walk` `onerror`) and links not followed go into
  the `warnings` list of `discover_captures` / `build_index` / `plan_copy`; `index` prints them
  as *Folders not scanned*, copy as `warning:` lines. Never a crash.
- Drive root as ROOT: `discovery.project_name(root)` = folder name, else drive letter (`D`),
  UNC share (`server_share`) or `drive` for `/`. Index CSV `D:\D_image_index_YYYYMMDD.csv`;
  copy default dest goes INSIDE the drive root (`D:\D_subset_NN`; marker + inside-ROOT warning),
  because there is no folder next to it (the user chose this over requiring `--dest`).
- Duplicates (`core/duplicates.py`): same `ImageBase.upper()`, `CaptureTime`, lat and lon
  (exact; copies are byte-identical) in different folders. Records without time or position
  (MATLAB CSVs) are never duplicates (`can_detect`). index/filter/copy always list the groups
  and never stop; `--skip-duplicates` (filter, copy) keeps the first of each group in
  case-insensitive RelativeFolder order; copy reports the others as `skipped-duplicate`.
- `scripts/bench_scan.py`: synthetic tree (default 3,000 captures × 7 + 200,000 unrelated
  files), times `discover_captures` only. Mac, warm cache: 0.7–1.1 million files/s. No
  optimisation needed; re-run on the work computer as V93.
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
  `_v02`. Default dest `<ROOT parent>/<ROOT name>_subset_NN` (first free number, compared
  case-insensitively; resume = `--dest <that folder>`); refuses a non-empty dest
  without `OUTPUT_MARKER` and a dest that contains ROOT; warns if inside ROOT. Writes go to
  `<name>.uas-partial` then `replace`. Same size → `skipped-existing`; different size →
  `conflict` (exit 1) unless `--overwrite`. Hardlink: other drive (per-file `st_dev`) refused at
  plan time, a failed link aborts the run — never falls back to copying. Move needs
  `--confirm-move`; cross-drive = copy + verify + delete; bands already at the dest →
  `already-at-destination`. Include files are copied (never moved) to the dest root. Free space
  must be ≥ needed × 1.02 + 100 MB. All file-system calls go through `long_path` (`\\?\` on
  Windows); paths > 259 chars give a Pix4D warning. Report CSV columns `Kind, RecordName, Band,
  Source, Destination, Status, Bytes, Message`, written next to the dest with a timestamp; dry
  runs write it only with `--report`. The marker file records Created / ROOT / Subset CSV.
  `--layout flat` names = `flat_folder + "_" + original file name`; `_DestListing` finds
  existing files by (prefix, BASE, band) by trying the pattern after every `_`, so resume and
  move detection work in both layouts; any two tasks with the same destination (NFC,
  casefold) → `CopyError` before anything is written.

- Footprint (`core/footprint.py`, no files): hull in the local UTM zone (`convex_hull` or
  `shapely.concave_hull(ratio, allow_holes=False)`, default ratio 0.3), corners mapped back to
  the **original** lon/lat (dict lookup; reprojection only as fallback), so the KML used as an
  AOI keeps every capture inside. < 3 distinct positions or hull area < 1 m² → `FootprintError`.
  Buffer via `filter.buffer_metres` (can give a MultiPolygon). `group_by_folder(depth)` cuts
  `RelativeFolder` to DEPTH parts (`(root)` for root captures; MATLAB CSVs → error).
  `build_footprints` → `FootprintResult` (skipped groups listed; `combined_hectares` = union
  area); `footprint_placemarks` gives one palette colour per area and an HTML-escaped
  `<br>`-joined description (folder, captures, ha, hull, buffer, CSV name). Areas in ha via
  `filter.area_hectares` (UTM). `filter.to_crs` is the shared reprojection helper.
- KML writer (`core/kml.py`, reusable): ElementTree, `xmlns` KML 2.2, UTF-8 declaration,
  `lon,lat,0`, closed rings, outer CCW / holes CW (`oriented`), coordinates as shortest
  round-trip decimals (`np.format_float_positional(unique=True)`) → `load_aoi` reads back
  exactly. `write_kml` opens with `xb` unless `overwrite=True`. CLI: output must end in `.kml`
  (so the CSV can never be overwritten), existing KML needs `--overwrite`, `--ratio` only with
  `--hull concave`, `--per-folder` without DEPTH = full folder (`const=0`).

- Pickers (`pickers.py`, front end only; tkinter imported inside functions): offered only when
  a required path is missing AND `pickers_available()`: no `--no-picker`, env
  `UAV_AOI_SUBSET_NO_PICKER` unset/0, **stdin is a TTY** (scripts, schedulers, CI and pytest
  never get a window), main thread, `DISPLAY`/`WAYLAND_DISPLAY` on Linux, `import tkinter` ok.
  `Tk()` failing (`TclError`) → `PickerUnavailable` → usage error. Otherwise argparse's
  "the following arguments are required" (exit 2). Hidden topmost root (in front on macOS);
  Windows `SetProcessDpiAwareness(1)` (fallback `SetProcessDPIAware`). Order and start folder in
  `cli.REQUIRED_PATHS`: filter CSV → AOI (in the CSV's folder), copy ROOT → CSV (in ROOT); only
  missing paths asked. Cancel → "Cancelled: …" exit 1. Then `Equivalent command: uav-aoi-subset
  …` on stdout (picked paths always double-quoted, inserted after the last typed positional).
  Positionals are `nargs="?"`, `filter --aoi` is not argparse-required. `--no-picker` and
  `--debug` come from a `parents=[common]` parser on every subcommand.
- Progress (`console.py`, `ConsoleProgress`, stdlib only; `core/` still only calls
  `progress(stage, done, total)`): on a terminal one bar via `\r` only (no ANSI), ASCII `#`/`-`,
  width = terminal − 1, ≤ 10 redraws/s, ETA after 2 s and 1 %. Not a terminal: "<Stage>:
  started", one line per 10 %, unknown totals (scan) every 10 s + a final line. Clock/stream
  injectable for tests. filter/footprint have no stage (fast).
- Errors (`cli.py`): `_error(message, next_step)` → `error: …` + indented next step on every
  error. `_cannot_write` for output paths (PermissionError → "close it in the spreadsheet or use
  --out"). `exif.install_hint()` is OS-specific (Windows: installer or rename
  `exiftool(-k).exe`). `main()` catches KeyboardInterrupt → "Interrupted." exit 130 (copy also
  writes the report so far and prints the `--dest` resume hint) and any other Exception → short
  message + `--debug` hint + issues URL, exit 1; `--debug` prints the traceback. Exit codes 0/1/2/130
  in the main `--help` epilog and the README. `--version` (custom action, runs ExifTool only then)
  prints package, Python + platform, `ExifTool <ver> at <path>` or "not found on PATH".

Validation prep is in place: `docs/VALIDATION.md` (work-computer checklist in five phases:
Phase 1 = P1–P7 + snag log, README only; Phase 2 = blueberry V1–V69 (footprint V20–V20g,
Pix4D flat layout V50, `--version` V4, pickers / progress / Ctrl+C / permission V60–V69);
Phase 3 = unusual KMLs V70–V72 (V73 n.a.) + layered copy V74–V79; Phase 4 = real campaign V80–V87, privacy rules first; Phase 5 =
ROOT too high V90–V93; results tables per phase with an issue column), `docs/RELEASE.md`
(README asset list + public gate), `.github/ISSUE_TEMPLATE/bug_report.yml` (issue form with
privacy warning and checkbox; blank issues disabled), `scripts/compare_outputs.py`,
`scripts/bench_scan.py`, `.gitattributes` (LF in the repo, also for commits from Windows).
README *Installation* is written for an ordinary Windows user (uv/ExifTool without admin or
scripts, `exiftool(-k).exe` rename, `--exiftool`, user PATH, new window, ZIP without Git,
troubleshooting table). Not yet run on real data.

Example data and the layered copy (decided 2026-10-28):
- The blueberry dataset is published as **one folder** (`altum-pt-blueberries-60m-sample-data`):
  3,361 files (3,360 TIFFs + panel CSV), no sub-folders; ZIP 20,822,285,409 B, extracted
  27,278,926,830 B. Its page states no licence: we only link to it, never redistribute.
  Phase 2 expectations are written for one folder (V14/V42 n.a., V20d one `(root)` polygon,
  no renaming in V31, V50 only flat import).
- `examples/make_layered_dataset.py` is a **public helper script, not part of the package**
  (no console script; `uv run python examples/make_layered_dataset.py build|verify`). The README
  (*Example dataset → Optional: a layered copy of the example data*) explains it; using it is
  optional, the tool works with flat data. Stdlib + `core` + `console.ConsoleProgress`; no brands.
  `build`: top-level files of INPUT only (sub-folders ignored with a warning, files written by
  this tool skipped), captures sorted by the trailing number of `base`, `--parts` (4) consecutive
  groups → `{g:04d}SET/{n:03d}` (`--folder-captures` 200 per sub-folder), numbering restarts per
  SET with one digit width for all; other files → `0000SET/000`; `--add-duplicate [GROUP]`
  (default 2, 1-based) → `old_subset/<SET>_<sub>/`; copy (`.partial` → replace) or hardlink
  (same drive, no fallback); OUTPUT new or empty, outside INPUT; space check with
  `copy.required_space`; mapping CSV `<OUTPUT>_mapping.csv` **next to** OUTPUT (columns
  `OriginalFile, OriginalImageBase, OriginalRecordName, Group, Kind, NewPath, NewRelativeFolder,
  NewImageBase, NewRecordName`; record names via `discovery.record_name`). `verify MAPPING FLAT
  LAYERED`: both subsets mapped back to original bases (ImageBase / (RelativeFolder, ImageBase),
  else RecordName, so MATLAB CSVs work); SAME only if the sets match; copies listed but not a
  difference. Tests in `tests/test_make_layered_dataset.py`.
- VALIDATION Phase 3B runs the script **from the README instructions** (also tests the README),
  with cross-line AOIs `blueberry_aoi_cross_all.kml` / `_cross_two.kml` (public examples) and
  screenshots 11–13 (RELEASE.md A). The V50 question (renamed bands grouped in Pix4D?) moved to
  **V77e**.

Next: **milestone 7, real-data validation on the work computer** (Windows). Everything is run
from `docs/VALIDATION.md` top to bottom, phase by phase; results (numbers only) go into its
*Results* tables and are pushed from there before the clone is deleted. Every finding is opened
as a GitHub issue with the bug report form (no coordinates, names, paths or screenshots of real
data: issues become public with the repo). Take to that session:
- **Phase 1 first, with the README only** (do not read VALIDATION.md beyond Phase 1 until it is
  done); keep the snag log. This also installs the tools (uv, ExifTool; Git is needed from
  Phase 2 on). GitHub sign-in through Git Credential Manager (repo is private); repo-local git
  identity with the noreply email (commands in Phase 2, 2.1). Delete the stored credentials in
  *Finish and clean up*.
- Phases 4–5 use real campaign data: outputs only in `C:\uav-demo\private`, anonymous numbers
  only in the repo. Delete the Phase 5 outputs on the campaign drive afterwards.
- Dataset: download the EagleNXT blueberry ZIP (20,822,285,409 B), extract, move the one folder
  `altum-pt-blueberries-60m-sample-data` to `C:\uav-demo\data\blueberry`; expect 3,361 files,
  3,360 TIFFs, no sub-folders, 480 captures, all complete with `--bands 7`. Phase 3B makes the
  layered copy `C:\uav-demo\data\blueberry_layered` with hard links (README route). MATLAB and the `.m` scripts already on the work computer are used for 2.7 and
  V84 (if missing, bring them over privately, never through the repository).
- Draw the AOIs in Google Earth Pro (2.5); they become the `examples/` KMLs (RELEASE.md A).
  Phase 3 needs QGIS for V70.
- Open questions to answer there: V77e — does Pix4Dmapper group the 7 bands of the renamed flat
  files (only the layered copy has renamed files)? If not, switch the default to `--layout folders` (on the Mac). V41 — long paths in
  Explorer/Pix4D. V60/V66 — pickers sharp on high DPI and in front, bar not wrapping in the
  Windows console. V20c — which footprint buffer matches the Pix4D mosaic. Phase 1 — which
  install route works on a company computer. V91/V92 — are duplicates and project folders
  handled well enough, or is a default `--exclude` list needed?
- Also collect the RELEASE.md section A assets (screenshots, example KMLs, README facts) in the
  same visit (blueberry only), then push everything from the work computer (*Finish and clean
  up*).
- Back on the Mac: fix findings, re-validate on the work computer if code changed; then
  milestone 8 (README) and 9 (public gate).

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
- Expected blueberry sanity numbers: one folder, 3,361 files; 480 captures indexed, all
  complete with `--bands 7`. Layered copy (4 parts): 4 × 120 captures, 0 extra copies; with
  `--add-duplicate`: 600 captures, 120 extra copies.

## Working style

- **Public docs are brand-neutral, with two protected exceptions.** README, CLI help and
  other user-facing text must not name camera, drone or photogrammetry software brands (we
  cannot know the user's setup): say "multispectral camera", "photogrammetry software",
  "GIS". File-name patterns such as `IMG_0000_1.tif` are fine. Internal docs (this file,
  docs/VALIDATION.md, docs/RELEASE.md) may name the author's own tools.
  Package metadata (pyproject.toml: description, keywords, classifiers) contains no brands
  either.
  Exceptions that MUST stay, verbatim in meaning, and must never be deleted, shortened or
  "neutralised" by this rule or any later clean-up:
  1. README section **"Tested setup and compatibility"** (marked `<!-- KEEP -->`): the
     author's honest statement that he tested with a MicaSense Altum-PT and Pix4Dmapper,
     the list of brand-independence measures, the request for feedback via GitHub issues
     and the promise to fix problems, and the trademark note. Update its facts if the code
     changes (e.g. new parameters), but keep all four parts.
  2. Dataset citations (the "Example dataset" section and `examples/`), which name the
     dataset by its published title.
- **`<!-- AUTHOR: ... -->` blocks in README.md are written by the user.** Never fill them
  in, rewrite or delete them; keep them in place when restructuring the README.
- The README section "Positional accuracy" was written with the user; keep its meaning
  when editing (selection is by camera GNSS position at exposure, not image footprint).
- Before each milestone, propose a short plan; implement in small commits.
- Run `uv run ruff check`, `uv run ruff format`, `uv run pytest` before saying done.
- Ask before deleting files or rewriting git history.
