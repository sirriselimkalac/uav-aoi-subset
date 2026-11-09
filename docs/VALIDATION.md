# Manual checklist (blueberry dataset, Windows)

A short hands-on run of every command on the public example dataset, on a normal Windows
computer with Google Earth Pro. It takes about one hour (plus the dataset download). The
automated tests already cover the details; this checklist shows that the tool works for a
user, from the README, on real files.

Dataset: EagleNXT *"Altum-PT data of a blueberry field"* (link in the README). One folder,
3,361 files: 3,360 TIFFs (480 captures × 7 bands) and one calibration-panel CSV;
ZIP 20,822,285,409 bytes, extracted 27,278,926,830 bytes. Two of the captures (`IMG_0000`,
`IMG_0479`) are calibration-panel shots on the ground, in the same folder. Never commit or
redistribute the data.

Results contain numbers only. Every failed check becomes a GitHub issue (*Issues → New issue →
Bug report*); put its number into the results table.

## Setup

Install the tool and ExifTool as the README describes (*Installation*). Keep a snag log of
everything that does not work at once (results, *Snag log*). Then, in PowerShell, at the start
of every session:

```powershell
$Demo = "<work folder>"                    # e.g. C:\uav-demo; short ASCII path, same drive as $Data
$Repo = "$Demo\uav-aoi-subset"             # the clone or the extracted ZIP
$Data = "<folder that holds the 3,361 dataset files>"
$Lay  = "$Demo\data\blueberry_layered"     # layered copy (same drive as $Data: hard links)
$Aoi  = "$Demo\aoi"                        # AOIs drawn in Google Earth Pro
$Res  = "$Demo\results"                    # every output of the checks
New-Item -ItemType Directory -Force $Demo, "$Demo\data", $Aoi, $Res | Out-Null
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"
function aoi { uv run --project $Repo uav-aoi-subset @args }
```

## Part 1: the example dataset

| ID | Step | Expected |
|---|---|---|
| M1 | `aoi --version` | three lines: tool version, Python and Windows version, `ExifTool <version> at <path>` |
| M2 | `aoi index $Data --out "$Res\index.csv"` | 480 captures, all complete, 480 with GPS, no extra copies, no *Folders not scanned*. Note the time. |
| M3 | `aoi footprint "$Res\index.csv" --out "$Aoi\footprint.kml"`, then the same with `--buffer 20 --out "$Aoi\footprint_b20.kml"`; open both in Google Earth Pro | one polygon around all capture positions, the buffered one about 20 m larger everywhere. Note both areas (ha). |
| M4 | Open `$Repo\examples\blueberries.kml` and `$Repo\examples\area-of-interest.kml` in Google Earth Pro, together with the M3 footprint. Then draw your own `blocks.kml` in a new folder under *Temporary Places* (two polygons, one with a hole: edit the KML by hand to add an `innerBoundaryIs` ring if needed) and save the AOI file again as `aoi.kmz`; save both to `$Aoi` (they are not committed). | the field outline covers the footprint; the AOI lies inside the field |
| M5 | `aoi filter "$Res\index.csv" --aoi "$Repo\examples\area-of-interest.kml" --out "$Res\aoi.csv"`, the same for `examples\blueberries.kml`, `$Aoi\aoi.kmz` and `$Aoi\blocks.kml` | AOI **74**, field **480**, KMZ = 74; no capture inside the hole (import the CSV in Google Earth Pro to look) |
| M6 | `aoi copy $Data "$Res\aoi.csv" --dry-run` | output folder `…\<data folder name>_subset_01` shown, nothing written, 518 files (74 × 7) |
| M7 | `aoi copy $Data "$Res\aoi.csv"` | the default layout is `folders`; the dataset is one folder, so the files land directly in the output folder with their **original names** (`IMG_####_<band>.tif`); a report CSV next to it. Note files, size and time. |
| M8 | Resume: the same command with `--dest <the M7 output folder>` | everything skipped, exit code 0 (`$LASTEXITCODE`), takes seconds; a second report CSV next to the first (the first is kept) |
| M9 | `aoi copy $Data "$Res\aoi.csv" --mode hardlink --dest "$Demo\data\linked"` | "Space needed: 0 bytes"; `fsutil hardlink list "<a linked file>"` shows two paths |
| M10 | `aoi copy $Data "$Res\aoi.csv" --mode move` | refused, asks for `--confirm-move`, nothing moved |

## Part 2: the layered copy

The layered copy gives the one-folder dataset a field-like structure: four set folders with
restarting image numbers, sub-folders of 50 captures, and one forgotten copy of a set
(`old_subset`). Follow the README (*Optional: a layered copy of the example data*) and note
anything unclear.

| ID | Step | Expected |
|---|---|---|
| M11 | `cd $Repo; uv run python examples\make_layered_dataset.py build $Data $Lay --parts 4 --folder-captures 50 --add-duplicate --mode hardlink` | 480 captures in four groups of 120 (`0000SET` … `0003SET`, each with sub-folders `000`, `001` (50 captures) and `002` (20)); group 2 again in `old_subset`; space needed 0 bytes; mapping CSV next to `$Lay` |
| M12 | Draw `cross.kml` in Google Earth Pro: a band **across** the flight lines that crosses all four strips (M14 shows them); save it to `$Aoi`. Also run M15–M17 once with `examples\area-of-interest.kml` (README walk-through) | one polygon; with the example AOI: flat 74, layered 113 (39 copies), `RESULT: SAME` |
| M13 | `aoi index $Lay --out "$Res\lay_index.csv"` | 600 captures (480 + the 120 copies in `old_subset`), all complete, **extra copies: 120**, each listed with its two folders; the run does not stop |
| M14 | `aoi footprint "$Res\lay_index.csv" --out "$Aoi\lay_sets.kml" --per-folder 1`, open in Google Earth Pro | five polygons: four parallel strips `0000SET` … `0003SET` (120 captures each) and `old_subset` (120) on top of the second strip |
| M15 | `aoi filter "$Res\index.csv" --aoi "$Aoi\cross.kml" --out "$Res\cross_flat.csv"` and `aoi filter "$Res\lay_index.csv" --aoi "$Aoi\cross.kml" --out "$Res\cross_lay.csv"` | layered count = flat count + the copies inside the AOI; the copies are listed |
| M16 | `aoi copy $Lay "$Res\cross_lay.csv"` | one sub-folder per source folder (`0000SET_000`, `0001SET_001`, …, `old_subset_0001SET_000`, …) with the original file names; no name clashes |
| M17 | `uv run python examples\make_layered_dataset.py verify "$Demo\data\blueberry_layered_mapping.csv" "$Res\cross_flat.csv" "$Res\cross_lay.csv"` | `RESULT: SAME`, exit code 0, plus *Captures found more than once* with the `--skip-duplicates` hint |
| M18 | `aoi filter "$Res\lay_index.csv" --aoi "$Aoi\cross.kml" --skip-duplicates --out "$Res\cross_lay_skip.csv"`, then `aoi copy $Lay "$Res\cross_lay.csv" --skip-duplicates --dry-run`, then M17 with `cross_lay_skip.csv` | filter: count = flat count, dropped copies listed; copy: the `old_subset` copies shown as skipped duplicates; verify: `RESULT: SAME` with no copies listed |

Afterwards delete the outputs (`$Res`, `$Lay`, the `*_subset_*` folders, `linked`) and, if the
clone was only for this run, the clone and any stored GitHub credentials.

## Pre-release run (Linux)

Run before the repository was made public, with the code of the commit that added this
section, on a Linux server (Ubuntu 24.04, x86_64, 8 cores, local SSD; Python 3.12.3, ExifTool
13.61), scripted, without Google Earth. The test AOIs were derived from
`examples/area-of-interest.kml`: the same AOI with a 25 m inner hole, the same AOI as KMZ, and
a 40 m band across the flight lines (the flight lines run north–south). The full test suite
passed on the server too (276 passed, 1 skipped: Windows junctions).

| ID | Result | Numbers |
|---|---|---|
| Dataset | pass | ZIP 20,822,285,409 B; 3,361 files, 3,360 TIFFs, no sub-folders, 27,278,926,830 B |
| M1 | pass | `0.0.1`, Python 3.12.3, ExifTool 13.61 |
| M2 | pass | 480 captures, 480 complete, 480 with GPS, no copies; 7.1 s |
| M3 | pass | convex 5.89 ha, `--buffer 20` 7.96 ha; the footprint used as an AOI keeps all 480 |
| M5 | pass | AOI 74; with the hole 58; KMZ 74; `--buffer 10` 103; field outline 480 |
| M6 | pass | 74 captures, 518 files, 3.9 GB, nothing written |
| M7 | pass | 519 files (518 + the panel CSV via `--include '*.csv'`), 4.2 GB, 23 s; original names |
| M8 | pass | 0 copied, 519 skipped, exit 0, 0.4 s; second report kept apart (`…_2.csv` when in the same second) |
| M9 | pass | 518 files linked, space needed 0 bytes; link count of a sample file > 1 |
| M10 | pass | refused without `--confirm-move`, exit 1; source still 3,361 files |
| M11 | pass | 4 × 120 captures, group 2 again in `old_subset` (840 files), 4,201 files, 0 bytes, under 1 s |
| M13 | pass | 600 captures, 120 extra copies; 6.7 s |
| M14 | pass | 5 polygons (4 strips 1.26–3.52 ha, `old_subset` 1.26 ha), combined 5.65 ha |
| M15 | pass | example AOI: flat 74, layered 113 (39 copies); cross band: flat 61, layered 79 (18 copies) |
| M16 | pass | example AOI: 791 files, 6.0 GB, 32 s, 9 folders; cross band: 553 files, 15 folders; original names |
| M17 | pass | `RESULT: SAME` for both AOIs |
| M18 | pass | `--skip-duplicates`: 74 / 61 captures, copies listed as skipped; `RESULT: SAME` without copies |
| Content | pass | every copied file compared byte by byte with the original it stands for: 791/791 and 553/553 identical; 7 file names occur in two set folders and are different images |
| Flat | pass | `--layout flat`: 61 captures, 427 files, no name clash |
| Bench | pass | `scripts/bench_scan.py`: 221,000 files, scan 0.32 s (680,863 files/s), 3,000/3,000 captures |
| README | pass | the *Example dataset* commands, run as written with the default build options: 480 / 74 / 518 linked, 0 bytes / 600 (120 copies) / 5 polygons / 113 (39 copies) / 791 linked / `RESULT: SAME` |

Finding: the copy report of a run was replaced when the next run started within the same
second (M7 → M8). Fixed in the same commit; M7 and M8 were re-run.

## Results

Commit tested: `7bb7fee`  Date: `2026-11-09`  Windows version: `Windows Server 2025 (10.0.26100)`
Python: `3.12.16`  ExifTool: `13.59`

Data and outputs on one NTFS drive (SSD); the cross-drive hard-link refusal was checked with a
`--dest` on a second drive. The full test suite passed on this computer too (274 passed,
3 skipped: symlinks and POSIX permissions). The test AOIs of M4 and M12 (`blocks.kml`,
`aoi.kmz`, `cross.kml`) were generated by a script instead of being drawn by hand, as in the
pre-release run: `blocks.kml` = the example AOI with a round 25 m hole at its centre plus a
separate 40 m square in the field; `aoi.kmz` = `examples/area-of-interest.kml` as `doc.kml`;
`cross.kml` = a 40 m band across the flight lines through the field centre. Every expected count
was computed independently from the index CSVs before running `filter`.

| ID | Result (pass / fail / n.a.) | Numbers / notes | Issue # |
|---|---|---|---|
| M1 | pass | `0.1.0`, Python 3.12.16, ExifTool 13.59 found on PATH | |
| M2 | pass | 480 / 480 complete / 480 with GPS, no copies, no folders skipped; 6.0 s | |
| M3 | pass | 5.89 ha, `--buffer 20` 7.96 ha (offset 19.96–20.00 m); looked at in Google Earth Pro | |
| M4 | pass | field outline = footprint (same polygon, 5.89 ha), AOI (1.01 ha) inside the field; looked at in Google Earth Pro. `blocks.kml` / `aoi.kmz` generated (see above) | |
| M5 | pass | AOI 74 / field 480 / KMZ 74 / blocks 72 (2 polygons, 1 hole: 61 + 11; the 13 captures in the hole left out) | |
| M6 | pass | 74 captures, 518 files, 3.9 GB, nothing written | |
| M7 | pass | 518 files, 3.9 GB, 4.5 s; original names; report next to the output folder | |
| M8 | pass | 0 copied, 518 skipped, exit 0, 0.6 s; second report kept apart | |
| M9 | pass | 518 files linked, space needed 0 bytes; `fsutil hardlink list` shows two paths; `--dest` on another drive refused, nothing created | |
| M10 | pass | refused without `--confirm-move`, exit 1; source still 3,361 files | |
| M11 | pass | 4 × 120 captures (sub-folders 50 / 50 / 20), group 2 again in `old_subset` (840 files), 4,201 files, 0 bytes; 1.2 s | |
| M12 | pass | `cross.kml` generated: 1 polygon, 1.16 ha, crosses all four sets. Example AOI: flat 74, layered 113 (39 copies), `RESULT: SAME` | |
| M13 | pass | 600 captures, all complete, 120 extra copies listed; 7.4 s | |
| M14 | pass | 5 polygons (0000SET 1.43, 0001SET 1.26, 0002SET 1.30, 0003SET 3.52, `old_subset` 1.26 ha), combined 5.65 ha; set centres side by side across the flight lines, `old_subset` on the second set (checked by script) | |
| M15 | pass | example AOI: flat 74, layered 113 (39 copies); cross band: flat 62, layered 82 (20 copies) | |
| M16 | pass | example AOI: 791 files, 6.0 GB, 8.7 s, 9 folders; cross band: 574 files, 4.3 GB, 15 folders; original names, no clashes | |
| M17 | pass | `RESULT: SAME`, exit 0, copies listed with the `--skip-duplicates` hint (both AOIs) | |
| M18 | pass | `--skip-duplicates`: example AOI 74, cross band 62; copy dry run 74 / 62 to copy, copies listed as left out; `RESULT: SAME` without copies (both AOIs) | |

Note (not a failure): the cross-drive hard-link error gives its next step on the same line,
while other errors put it on an indented second line.

### Snag log (installation from the README)

| Step | What I expected | What happened | How I solved it | Time (min) | Issue # |
|---|---|---|---|---|---|
| uv: `uv --version` | version | not recognized in the window used for the install | closed and opened a new window | 1 | README step 1 wording (commit 3d9b474) |
| ExifTool: `winget install --id OliverBetz.ExifTool -e` | installed into a folder of its own | installed for the user under `AppData\Local\Programs` | left as it is; on `PATH` (checked in the environment variables, 2 min) | 2 | README step 2 note |
| Git: `git clone …` | clone | Git not installed, so the command failed | `winget install --id Git.Git -e --source winget` | 10 | README steps 0 and 3 |
| Git: `git clone …` | clone | sign-in requested (repository still private) | signed in through the browser | 10 | none (public repo needs no sign-in) |

2026-11-09: the installation was resumed at `uv sync` (uv, ExifTool and Git were already installed); no snags.
