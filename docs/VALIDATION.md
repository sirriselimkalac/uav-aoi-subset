# Real-data validation on the work computer (Windows)

**Do this first, every time the repository is pulled on the work computer.** This is the only
machine that has real imagery. Setup-specific notes (folders, order, status) for the current work
computer are in [IS_BILGISAYARI.md](IS_BILGISAYARI.md); read its *Status* section first, but not
before Phase 1 is done. The Mac (development machine) only ever sees synthetic test data.

The repository stays **private until every check below has passed** on the commit that will
become v0.1.0, and the README assets in [RELEASE.md](RELEASE.md) are committed.

The validation runs in five phases, in this order:

| Phase | What | Data | Goes into the repo |
|---|---|---|---|
| 1 | Install like an ordinary user, **README only** | none | snag log, numbers |
| 2 | Every command on the public blueberry dataset (V1–V69) | blueberry | numbers, example KMLs, screenshots |
| 3 | Same data: unusual KMLs (V70–V72) and the layered copy (V74–V79) | blueberry | numbers, example KMLs, screenshots |
| 4 | Real campaign data (V80–V87) | private | **anonymous numbers only** |
| 5 | Real data with ROOT one level too high (V90–V93) | private | **anonymous numbers only** |

The clone on the work computer is **temporary**. When validation and the README assets are
done, it is deleted (*Finish and clean up*). Only the Mac copy remains. So:

- everything worth keeping (results, KMLs, screenshots) must be **committed and pushed** from
  here before the clone is removed;
- data and outputs live **outside** the clone (in `C:\uav-demo\data`, `C:\uav-demo\results`
  and, for Phases 4–5, `C:\uav-demo\private`), so `git status` only ever shows files meant for
  the repo.

## How to report a finding

Every failed check or snag becomes a GitHub issue, opened with the **Bug report** form
(*Issues → New issue*). The form asks for `--version`, the command and its output. Put the issue
number into the results table. Then commit and push the results, fix it on the Mac, `git pull`
here and run the failed check and everything after it again. Do not delete the clone while any
check or issue is open.

Issues become public together with the repository, so the same privacy rules apply as for the
results: **no coordinates, no imagery, no campaign or field names, no work paths, no
screenshots of real data.** Replace paths with placeholders (`D:\<campaign>\...`).

Dataset for Phases 2–3: EagleNXT *"Altum-PT data of a blueberry field"*. It has 480 captures ×
7 bands = 3,360 TIFFs plus one calibration-panel reflectance CSV. It is public, but it is
**never** committed or redistributed; the README only links to it. The dataset page states no
licence.

As published it is **one folder** (`altum-pt-blueberries-60m-sample-data`): 3,361 files, no
sub-folders, ZIP 20,822,285,409 bytes (19.3 GB), extracted 27,278,926,830 bytes (25.4 GB). So
Phase 2 cannot exercise folder handling (set folders, repeated image names, flattening); Phase 3
does that with a layered copy made by `examples/make_layered_dataset.py`.

---

## Phase 1: install like an ordinary user (README only)

The goal is to find out whether someone who has only the README can install the tool on a
normal Windows computer. So:

- **Do not read further in this file until Phase 1 is done.** Open only the README (on GitHub,
  in the browser) and follow its *Installation* section exactly, as a new user would. Do not
  use knowledge from this file or from the development work.
- Where the README lets you choose a folder, use `C:\uav-demo\phase1`.
- Keep a **snag log** while you go: every time something does not work at once, or the README
  is unclear, write one row. Afterwards copy it into the Phase 1 results.

  | Step | What I expected | What happened | How I solved it | Time (min) |
  |---|---|---|---|---|
  | e.g. install uv | the script installs uv | "running scripts is disabled" | used `winget` route | 5 |

- Open an issue for every snag that needs a change in the README or the code.

| ID | Check | Expected |
|---|---|---|
| P1 | Start state, before installing anything: Windows version; admin rights or not; `winget --version`; `Get-ExecutionPolicy -List`; are `git`, `uv`, `exiftool`, `py` already found? | noted in the results (yes/no answers only) |
| P2 | README step 1: uv | `uv --version` works in a new window; note the route used (script / winget / pip / ZIP) and the minutes |
| P3 | README step 2: ExifTool | `exiftool -ver` works in a new window, or the README's `--exiftool` route is used; note the route and the minutes |
| P4 | README step 3: get the tool (Git or ZIP) and `uv sync` | no errors; note the route and the minutes |
| P5 | `uv run uav-aoi-subset --version` | three lines, the last one `ExifTool <version> at <path>`; note the total minutes since P1 |
| P6 | `uv run uav-aoi-subset --help` and `uv run uav-aoi-subset index --help` in a normal PowerShell window | readable, no broken characters; the README *Usage* section matches |
| P7 | Optional: `uv tool install .`, new window, `uav-aoi-subset --version` in another folder | works from any folder |

Only now continue with Phase 2.

---

## Phase 2: blueberry dataset

These are the original checks V1–V69. Their IDs are unchanged. The data is one folder, so
every capture lies in ROOT itself: there is one footprint polygon, `copy` does not rename files,
and `--layout folders` gives the same result as the flat layout. Those parts are checked on the
layered copy in Phase 3.

### 2.0 Before you start

- [ ] On GitHub, check the latest commit on `main` and its CI status (green on all 6 jobs).
- [ ] Read the *Status* section of `CLAUDE.md`.

### 2.1 Setup (once)

PowerShell (not admin). Skip the tools Phase 1 already installed; Git is needed from here on
(results are pushed from this clone), even if Phase 1 used the ZIP route:

```powershell
# Tools. If winget is blocked, use the installers from the websites instead.
winget install --id Git.Git -e --source winget
winget install --id OliverBetz.ExifTool -e --source winget   # or the Windows build from https://exiftool.org
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# Open a NEW PowerShell window afterwards so PATH is updated.
git --version; exiftool -ver; uv --version
```

Folders and console encoding (run these at the start of every PowerShell session):

```powershell
$Demo = "C:\uav-demo"                      # short ASCII path, no user name in screenshots
$Repo = "$Demo\uav-aoi-subset"
$Data = "$Demo\data\blueberry"             # the extracted dataset: the folder that holds the TIFFs
$Lay  = "$Demo\data\blueberry_layered"     # Phase 3: layered copy (same drive, so hard links work)
$Aoi  = "$Demo\aoi"                        # KMLs drawn in Google Earth (blueberry only)
$Res  = "$Demo\results"                    # every output of the checks
New-Item -ItemType Directory -Force $Demo, "$Demo\data", $Aoi, $Res | Out-Null
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"
function aoi { uv run --project $Repo uav-aoi-subset @args }   # short alias
```

Clone and sign in. The repository is private: on the first clone, Git Credential Manager opens a
browser window to sign in to GitHub. *Finish and clean up* removes the stored credentials again.

```powershell
cd $Demo
git clone https://github.com/sirriselimkalac/uav-aoi-subset.git
cd $Repo
# Identity for THIS repository only (does not touch your work Git settings):
git config user.name  "Sırrı Selim Kalaç"
git config user.email "260359645+sirriselimkalac@users.noreply.github.com"
git log -1 --format="%h %an <%ae>"
```

Download the dataset from the link in the README (ZIP: 20,822,285,409 bytes; the README says
"about 19 GB") and extract it. The ZIP holds one folder, `altum-pt-blueberries-60m-sample-data`.
Move that folder to `$Data` (replace the first path with where you extracted it):

```powershell
Move-Item "<extract folder>\altum-pt-blueberries-60m-sample-data" $Data
(Get-ChildItem $Data -File).Count                                     # expect 3361
(Get-ChildItem $Data -Recurse -Include *.tif,*.tiff -File).Count      # expect 3360
(Get-ChildItem $Data -Recurse -Directory).Count                       # expect 0
(Get-ChildItem $Data -File | Measure-Object Length -Sum).Sum          # expect 27278926830
Get-ChildItem $Data -Exclude *.tif | Select-Object Name               # the calibration CSV
```

### 2.2 Unit tests on this machine

| ID | Step | Expected |
|---|---|---|
| V1 | `cd $Repo; uv sync --locked; uv run pytest` | all pass, **0 skipped** (ExifTool found) |
| V2 | `git rev-parse --short HEAD` | write the commit hash into the results table |
| V3 | `Get-ItemProperty HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem -Name LongPathsEnabled` | note the value (0 or 1); it matters for V41 |
| V4 | `aoi --version` | three lines: program version, Python version and Windows version, `ExifTool <version> at <path>`; copy Python and ExifTool into the results table header |

### 2.3 index

```powershell
Measure-Command { aoi index $Data --out "$Res\ours_index.csv" | Out-Default }
```

| ID | Check | Expected |
|---|---|---|
| V10 | Summary | 480 captures, all complete, 480 with GPS, no extra copies, no *Folders not scanned*, no ExifTool warnings. Write down the time. |
| V11 | Open `ours_index.csv` in Excel (double-click) | Note whether the columns split correctly. With a Turkish locale Excel may expect `;`. Turkish characters must display correctly. |
| V12 | Turkish path: `Copy-Item -Recurse $Data "$Demo\data\Saha Fotoğrafları – deneme"`, then `aoi index "$Demo\data\Saha Fotoğrafları – deneme" --out "$Res\tr_index.csv"` | same numbers as V10 |
| V13 | ExifTool not on PATH: `aoi index $Data --out "$Res\x.csv" --exiftool "<full path to exiftool.exe>"` with a PATH without ExifTool (`$env:Path = ($env:Path -split ';' \| ? { $_ -notmatch 'exiftool' }) -join ';'`) | works with `--exiftool`; without it, a clear "ExifTool was not found on PATH" error that lists only the **Windows** install steps (installer, or rename `exiftool(-k).exe`), exit code 1, no traceback. Open a new window afterwards. |
| V14 | If the dataset contains calibration-panel captures in their own folder: `aoi index $Data --exclude "<panel folder>" --out "$Res\nopanel.csv"` | panel captures left out. **Blueberry: n.a.** (no panel captures, only the reflectance CSV) |

### 2.4 footprint

```powershell
aoi footprint "$Res\ours_index.csv" --out "$Aoi\blueberry_footprint.kml"
aoi footprint "$Res\ours_index.csv" --out "$Aoi\blueberry_footprint_concave.kml" --hull concave
aoi footprint "$Res\ours_index.csv" --out "$Aoi\blueberry_footprint_b20.kml" --buffer 20
aoi footprint "$Res\ours_index.csv" --out "$Res\blueberry_footprint_folders.kml" --per-folder
```

Keep the merged-area KML you made earlier with Pix4D **outside the clone** (for example in
`$Res`). It shows real coordinates and is never committed.

| ID | Check | Expected |
|---|---|---|
| V20 | Default (convex) footprint, open in Google Earth Pro | one yellow, semi-transparent polygon around all capture positions; 480 captures used, 0 without GPS; click it: the balloon shows captures, area (ha) and the CSV name. Note the area. |
| V20a | `--hull concave` | area smaller than or equal to V20; the outline follows the flight lines (no large empty corners). If it cuts into the field, try `--ratio 0.5` and note which ratio fits best. |
| V20b | `--buffer 20` | outline about 20 m outside V20 everywhere (Google Earth ruler) |
| V20c | Open V20, V20b and the Pix4D merged-area KML together | visual comparison: the Pix4D area (the imaged ground) should lie around the V20 outline; note roughly which buffer (V20b or another value) matches the Pix4D area best |
| V20d | `--per-folder` | one polygon, named `(root)`, with 480 captures: every capture lies in ROOT itself. `--per-folder 2` gives the same. (Several polygons, one per set folder, are checked on the layered copy in V76a.) |
| V20e | `aoi filter "$Res\ours_index.csv" --aoi "$Aoi\blueberry_footprint.kml" --out "$Res\fp_subset.csv"` | 480 captures inside (the footprint as an AOI keeps every capture) |
| V20f | Run the first command again | refused: the KML exists, add `--overwrite` |
| V20g | `aoi footprint "$Res\matlab_index.csv" --out "$Res\matlab_footprint.kml"` (after 2.7) | same polygon as V20 when both are opened in Google Earth |

### 2.5 Draw the AOIs in Google Earth Pro

Draw these in a **new, empty folder** under *Temporary Places* (not *My Places*), then right-click
the folder → *Save Place As… → KML*. They become the public examples (see RELEASE.md).

- `$Aoi\blueberry_aoi_north.kml`: one simple polygon over roughly the northern third of the field.
- `$Aoi\blueberry_aoi_blocks.kml`: two separate polygons, one of them with a hole (draw the hole
  as a second polygon and combine them, or edit the KML by hand to add `innerBoundaryIs`).
- `$Aoi\blueberry_aoi_north.kmz`: the same as the first one, saved as KMZ.

Tip: *File → Import* of `ours_index.csv` (latitude/longitude columns) shows the capture
positions as points, which helps with drawing and with V21–V24.

### 2.6 filter

```powershell
aoi filter "$Res\ours_index.csv" --aoi "$Aoi\blueberry_aoi_north.kml"
aoi filter "$Res\ours_index.csv" --aoi "$Aoi\blueberry_aoi_blocks.kml"
aoi filter "$Res\ours_index.csv" --aoi "$Aoi\blueberry_aoi_north.kmz" --out "$Res\north_kmz.csv"
aoi filter "$Res\ours_index.csv" --aoi "$Aoi\blueberry_aoi_north.kml" --buffer 10 --out "$Res\north_b10.csv"
$North = Get-ChildItem "$Aoi\blueberry_aoi_north_image_index_*.csv" | Select-Object -Last 1
```

| ID | Check | Expected |
|---|---|---|
| V21 | north KML | count noted; Google Earth import of the subset CSV shows only points inside |
| V22 | blocks KML | both polygons used; no points inside the hole |
| V23 | KMZ | same count as V21 |
| V24 | buffer 10 m | count ≥ V21 |

### 2.7 Compare with the MATLAB scripts

Use the MATLAB scripts already on the work computer. They are not in this repository; if they
are missing, bring them over privately (never through the repository).

Important: the MATLAB index writes `<project>_image_index_YYYYMMDD.csv` into the data root, and
the MATLAB copy writes its output **inside** the data root. Move both to `$Res` right after each
run. Otherwise our later `index` runs would pick up the MATLAB copies as duplicates.

1. `BUILD_PROJECT_IMAGE_INDEX.m`, root `$Data` → move the CSV to `$Res\matlab_index.csv`.
   Write down the time.
2. `EXPORT_CSV_WITHIN_KML_AREA.m` with `$Res\matlab_index.csv` and `blueberry_aoi_north.kml`
   → move the result to `$Res\matlab_north.csv`.
3. `COPY_GEOTIFFS_FROM_CSV.m`, root `$Data`, CSV `$Res\matlab_north.csv` → move its output
   folder out of `$Data` to `$Res\matlab_copy_north`.

```powershell
cd $Repo
uv run python scripts\compare_outputs.py csv "$Res\ours_index.csv" "$Res\matlab_index.csv"
uv run python scripts\compare_outputs.py csv $North.FullName "$Res\matlab_north.csv"
```

| ID | Check | Expected |
|---|---|---|
| V25 | index comparison | `RESULT: SAME` (same names, flags and positions within 5 cm) |
| V26 | subset comparison | `RESULT: SAME` |
| V27 | Time: ours (V10) vs. MATLAB index | write both down (README benchmark) |

### 2.8 copy

```powershell
$Dest = "$Demo\data\blueberry_subset_01"     # the default destination of the first run
aoi copy $Data $North.FullName --dry-run
```

| ID | Check | Expected |
|---|---|---|
| V30 | `--dry-run` | summary shows `Output folder: ...\blueberry_subset_01`; `Test-Path $Dest` is `False`; no report written |
| V31 | `Measure-Command { aoi copy $Data $North.FullName --include '**/*.csv' \| Out-Default }` | files copied = V21 × 7 (+ the reflectance CSV); all files directly in `$Dest`, named `IMG_####_<band>.tif` as in the dataset (the captures lie in ROOT itself, so there is no folder chain to add; renaming is checked in V77b); report CSV next to `$Dest`; write down the time |
| V32 | MATLAB keeps one folder per source folder, so compare with that layout: `aoi copy $Data $North.FullName --layout folders --dest "$Res\ours_copy_folders"`, then `uv run python scripts\compare_outputs.py tree "$Res\ours_copy_folders" "$Res\matlab_copy_north"` | only differences are our extra report/include files, if any. On this one-folder data both tools put the files directly in the output folder; folders appear in V77c |
| V33 | Resume: `aoi copy $Data $North.FullName --include '**/*.csv' --dest $Dest` | everything skipped, exit code 0 (`$LASTEXITCODE`), takes seconds |
| V33a | New run without `--dest`: `aoi copy $Data $North.FullName --dry-run` | output folder is `blueberry_subset_02`; `$Dest` untouched. `Get-Content "$Dest\.uav-aoi-subset-output"` names the subset CSV |
| V34 | Interrupt: `aoi copy $Data "$Res\ours_index.csv" --dest "$Res\full_copy" --layout folders` (folders layout because V35 and V39 reuse this tree), press Ctrl+C after a few seconds, then run it again | "Interrupted." and a resume hint naming `--dest`, `$LASTEXITCODE` = 130, no traceback; a `full_copy_copy_report_*.csv` of the files done so far; no `*.uas-partial` files left (`Get-ChildItem "$Res\full_copy" -Recurse -Filter *.uas-partial`); the second run completes; 3,360 files in total |
| V35 | Conflict: `Set-Content "$Res\full_copy\IMG_0001_3.tif" "x"`, run again | exit code 1, the file is listed under *Conflicts* and left as it is; with `--overwrite` it is replaced |
| V36 | Report: open the newest `*_copy_report_*.csv` in Excel | one row per file; statuses are plausible |
| V37 | Hard links (same NTFS drive): `aoi copy $Data $North.FullName --mode hardlink --dest "$Demo\data\linked_north"` | "Space needed: 0 bytes"; `fsutil hardlink list "<a linked file>"` shows two paths |
| V38 | Move refused: `aoi copy $Data $North.FullName --mode move` | refused, asks for `--confirm-move`; nothing moved |
| V39 | Move on a **disposable copy** (never the original): copy `$Res\full_copy` to `$Demo\data\move_src`, delete `.uav-aoi-subset-output` in it, `aoi index $Demo\data\move_src --out "$Res\move_index.csv"`, then `aoi copy $Demo\data\move_src "$Res\move_index.csv" --dest "$Demo\data\move_dst" --mode move --confirm-move`; run it a second time | first run: all moved, no TIFFs left in `move_src`; second run: all "already at the destination", nothing reported missing |
| V40 | Destination inside the root: `aoi copy $Data $North.FullName --dest "$Data\_subset_test"`, then `aoi index $Data --out "$Res\after.csv"` | warning on copy; the index still shows 480 captures. Then delete `$Data\_subset_test`. |
| V41 | Long path: `aoi copy $Data $North.FullName --dest "$Res\$('a'*120)\$('b'*120)"` | warning about long paths; files exist. Note whether Explorer and Pix4Dmapper can open them. |
| V42 | Extra captures (if the dataset has panel captures): `--extra-captures <panel record names>` or a text file with one name per line | panel files copied next to the others, named `<panel folder chain>_IMG_####_<band>.tif`. **Blueberry: n.a.** (no panel captures) |
| V43 | Other drive (USB stick or D:, optional): `--dest` on that drive with `--mode copy` | works |
| V44 | Same, with `--mode hardlink` | refused **before** anything is written ("hard links only work on one drive") |
| V45 | exFAT/FAT32 stick (optional): put a small subset folder on the stick as ROOT, index it, then `--mode hardlink` with a `--dest` on the stick | stops with the "may not support hard links … use --mode copy" message; no fallback to copying |
| V46 | Cross-drive move (optional, disposable copy as in V39, `--dest` on the other drive) | all moved; sources deleted only after each file is complete |

### 2.8b Pix4Dmapper

| ID | Check | Expected |
|---|---|---|
| V50 | New project → *Add Images…* → all files in `$Dest` (flat layout; here the names are unchanged) | all images load; camera rig recognised (Altum-PT) and the 7 bands of each capture grouped together; image count noted. Whether **renamed** files (`<folder chain>_IMG_####_<band>.tif`) are grouped is checked in V77e |
| V51 | Map view | camera positions lie inside the AOI |
| V52 | Optional: run step 1 (Initial Processing) | completes; calibration panel detected if included (V42) |

### 2.8c Pickers, progress and errors

Pickers open only when a required path is missing **and** the command runs interactively
(PowerShell window, stdin not redirected). Close any Excel window holding a result CSV first,
except in V69.

| ID | Check | Expected |
|---|---|---|
| V60 | `aoi index --out "$Res\picker_index.csv"` (no ROOT), choose `$Data` | folder picker opens **in front of** PowerShell, text sharp (not blurry) on a high-DPI / scaled display; then `Equivalent command: uav-aoi-subset index "C:\uav-demo\data\blueberry" --out ...`; same numbers as V10 |
| V61 | `aoi filter` (no arguments): choose `$Res\ours_index.csv`, then `$Aoi\blueberry_aoi_north.kml` | CSV picker first; the AOI picker opens in `$Res` (the CSV's folder); same captures inside as V21 |
| V62 | `aoi copy --dry-run` (no arguments): choose `$Data`, then the north subset CSV | folder picker first, then the CSV picker opens in `$Data`; same summary as V30 |
| V63 | `aoi footprint`, press *Cancel* | "Cancelled: no file selected; nothing was done.", `$LASTEXITCODE` = 1 |
| V64 | `aoi index --no-picker`; then `$env:UAV_AOI_SUBSET_NO_PICKER = "1"; aoi index; Remove-Item Env:UAV_AOI_SUBSET_NO_PICKER`; then `$null \| uv run --project $Repo uav-aoi-subset index` (stdin redirected; the `aoi` function would not pass the pipe on) | no window in any of the three; usage error "the following arguments are required: ROOT", `$LASTEXITCODE` = 2 |
| V65 | Rename the subset CSV written in V61 to `picked.csv`, then paste the *Equivalent command* line printed in V61 (replace `uav-aoi-subset` with `aoi`) and run it | no picker opens; `uv run python scripts\compare_outputs.py csv <new CSV> <picked.csv>` reports no differences |
| V66 | `aoi index $Data --out "$Res\bar.csv"` in a normal PowerShell window; also once in a narrow window (about 60 columns) | one bar that updates in place with count, percentage and ETA (Scanning, then Reading GPS); no wrapped or repeated lines, no stray characters |
| V67 | `aoi index $Data --out "$Res\log_index.csv" 2> "$Res\progress_log.txt"`, then `Get-Content "$Res\progress_log.txt"` | plain lines: `Reading GPS: started`, then one line per 10 % (`Reading GPS: 30% (…/480), 0:00:… elapsed`), no `\r` garbage |
| V68 | `aoi index $Data --out "$Res\x.csv"`, press Ctrl+C during "Reading GPS" | "Interrupted.", `$LASTEXITCODE` = 130, no traceback |
| V69 | Open `$Res\fp_subset.csv` in Excel, then run the V20e command again (same `--out`) | "cannot write …: permission denied" with the hint to close the file or use `--out`; exit 1, no traceback. Close Excel afterwards. |

---

## Phase 3: same data, different KMLs and a layered copy

### 3A. Unusual KMLs

Blueberry data, `$Res\ours_index.csv` from V10. Keep these KMLs in `$Aoi`; they are not public
examples.

| ID | Check | Expected |
|---|---|---|
| V70 | **KML exported from QGIS.** In QGIS, load `$Aoi\blueberry_aoi_north.kml` (or draw the same area as a polygon layer), then *Export → Save Features As… → KML* to `$Aoi\north_qgis.kml`. `aoi filter "$Res\ours_index.csv" --aoi "$Aoi\north_qgis.kml" --out "$Res\north_qgis.csv"` | read without AOI warnings (QGIS writes `MultiGeometry`, `ExtendedData` and a schema; all fine); same captures inside as V21 when it is the same polygon (`compare_outputs.py csv` against the V21 subset reports no differences) |
| V71 | **Area drawn as a line.** In Google Earth, draw the outline of the field with *Add Path* (not *Add Polygon*), save as `$Aoi\north_line.kml`, then `aoi filter "$Res\ours_index.csv" --aoi "$Aoi\north_line.kml" --out "$Res\line.csv"` | exit code 1, `error: …: no usable Polygon found. Draw the area with … 'Add Polygon' tool; paths (LineStrings) and placemarks (Points) are not areas.` plus the next step; `Test-Path "$Res\line.csv"` is `False`; no traceback |
| V72 | **Polygon away from the flight.** Draw a polygon a few km away, save as `$Aoi\elsewhere.kml`; `aoi filter "$Res\ours_index.csv" --aoi "$Aoi\elsewhere.kml" --out "$Res\elsewhere.csv"`; then `aoi copy $Data "$Res\elsewhere.csv" --dry-run` | filter: exit 0, `inside the AOI:   0`, the warning "no capture lies inside the AOI …", a CSV with only the header row. copy: 0 files to copy, nothing written (`Test-Path` of the shown output folder is `False`) |
| V73 | **Polygon across the border of two flights.** Blueberry is one folder: replaced by V77 on the layered copy (`cross_two` crosses the border between two set folders). Mark n.a. here; the real-data version is V86 | n.a. |

### 3B. Layered copy (`examples/make_layered_dataset.py`)

The one-folder data cannot show set folders, repeated image names or forgotten subset folders.
`examples/make_layered_dataset.py` makes a copy with that structure. **Follow the README
(*Example dataset → Optional: a layered copy of the example data*), not this file, for the
commands**, and note in V74 whatever was unclear: this also tests the README. The commands
below are only for checking.

Hard links keep the extra space near zero (`$Lay` is on the same drive as `$Data`). The tool
never writes into its inputs, so the shared files are safe here; do not use `$Lay` for the move
checks.

```powershell
cd $Repo
uv run python examples\make_layered_dataset.py build $Data $Lay --mode hardlink
aoi index $Lay --out "$Res\lay_index.csv"
aoi footprint "$Res\lay_index.csv" --out "$Res\lay_footprint_sets.kml" --per-folder 1
```

| ID | Check | Expected |
|---|---|---|
| V74 | **Build, following the README.** Note anything in the README that was unclear or missing | summary: 480 captures (0 incomplete), four lines `0000SET` … `0003SET` with 120 captures each (`IMG_0000 to IMG_0119`, `IMG_0120 to IMG_0239`, …), other files: 1, space needed `0 bytes`; then progress lines and `Mapping: …\blueberry_layered_mapping.csv`. In Explorer: `0000SET\000` … `0003SET\000`, each with `IMG_0000_1.tif` … `IMG_0119_7.tif` (840 files), the calibration CSV in `0000SET\000`. `$Data` unchanged: 3,361 files, no new ones (an index CSV written into `$Data` earlier is listed as "Not copied") |
| V74a | Run the same `build` command again | `error: …blueberry_layered is not empty` with the next step; exit code 1; nothing written |
| V74b | Ctrl+C: `uv run python examples\make_layered_dataset.py build $Data "$Demo\data\lay_ctrl_c"` (copy mode), press Ctrl+C after a few seconds; then `Remove-Item -Recurse "$Demo\data\lay_ctrl_c"` | "Interrupted." and "delete … and run again", `$LASTEXITCODE` = 130, no traceback, no `*.partial` file left, no mapping CSV |
| V75 | **Flight lines and numbering.** In Google Earth Pro, *File → Import* `$Res\ours_index.csv` (flat index from V10) as points; look at the labels/order (Excel: sort by `ImageBase`) | note the direction of the flight lines (e.g. N–S) and whether consecutive numbers follow one line, then the next (back and forth). Then the four groups of 120 are strips parallel to the lines |
| V76 | Layered `index` | 480 captures, all complete, 480 with GPS, **extra copies: 0** (each `IMG_0000` … `IMG_0119` exists in four set folders but they are different captures), no *Folders not scanned*. `RecordName` values are unique (`0000SET_000_IMG_0000` …) |
| V76a | `footprint --per-folder 1`, open in Google Earth | four coloured strips, 120 captures each, side by side and parallel to the flight lines (V75); together they cover the V20 polygon |

Draw two AOIs **across** the flight lines (as in 2.5, in a new folder under *Temporary Places*;
they become public examples):

- `$Aoi\blueberry_aoi_cross_all.kml`: a band across the field that crosses all four strips;
- `$Aoi\blueberry_aoi_cross_two.kml`: a shorter band that crosses only the border between two
  neighbouring strips.

```powershell
foreach ($a in "cross_all", "cross_two") {
  aoi filter "$Res\ours_index.csv" --aoi "$Aoi\blueberry_aoi_$a.kml" --out "$Res\${a}_flat.csv"
  aoi filter "$Res\lay_index.csv"  --aoi "$Aoi\blueberry_aoi_$a.kml" --out "$Res\${a}_lay.csv"
}
$Map = "$Demo\data\blueberry_layered_mapping.csv"
```

| ID | Check | Expected |
|---|---|---|
| V77 | Both AOIs drawn and saved | `cross_all` crosses the four strips of V76a, `cross_two` exactly two |
| V77a | The four `filter` runs | flat and layered counts equal for each AOI; in Excel, `RelativeFolder` of `cross_all_lay.csv` has all four set folders, `cross_two_lay.csv` two; counts per set folder noted |
| V77b | `aoi copy $Lay "$Res\cross_all_lay.csv" --include '**/*.csv'` (default flat layout; output `$Demo\data\blueberry_layered_subset_01`) | no error about two files with the same name; files = captures × 7 + 1 CSV; names like `0000SET_000_IMG_0000_1.tif` and `0001SET_000_IMG_0000_1.tif` side by side; report next to the folder |
| V77c | `aoi copy $Lay "$Res\cross_all_lay.csv" --layout folders --dest "$Res\lay_copy_folders"` | one folder per set folder (`0000SET_000`, `0001SET_000`, …), original file names inside; same file count as V77b |
| V77d | `uv run python examples\make_layered_dataset.py verify $Map "$Res\cross_all_flat.csv" "$Res\cross_all_lay.csv"`, then the same for `cross_two` | `RESULT: SAME`, exit code 0, capture counts as in V77a, no copies listed |
| V77e | **Pix4Dmapper with renamed files** (the open question of V50): new project → *Add Images…* → all TIFFs in the V77b folder | all images load; the 7 bands of each capture are grouped (renamed files keep the `_<band>` suffix); image count = V77b ÷ 7 captures. **If the bands are not grouped correctly**, repeat with the V77c output (*Add Directories…*) and write down which layout works |
| V77f | Wrong pairing: `verify $Map "$Res\cross_two_flat.csv" "$Res\cross_all_lay.csv"` | `RESULT: DIFFERENT`, exit code 1, the extra captures listed under *Only in the layered subset* |

Forgotten subset folder:

```powershell
$Dup = "$Demo\data\blueberry_layered_dup"
uv run python examples\make_layered_dataset.py build $Data $Dup --mode hardlink --add-duplicate
aoi index $Dup --out "$Res\dup_index.csv"
aoi filter "$Res\dup_index.csv" --aoi "$Aoi\blueberry_aoi_cross_all.kml" --out "$Res\cross_all_dup.csv"
aoi filter "$Res\dup_index.csv" --aoi "$Aoi\blueberry_aoi_cross_all.kml" --skip-duplicates --out "$Res\cross_all_dup_skip.csv"
```

| ID | Check | Expected |
|---|---|---|
| V78 | `build --add-duplicate` | summary adds `Duplicate: group 2 again in old_subset/ (840 files)`; `old_subset\0001SET_000` holds 840 files |
| V78a | `index` of `$Dup` | 600 captures; **extra copies: 120**, each listed with `0001SET/000` and `old_subset/0001SET_000`; the `IMG_0000` of the other set folders are **not** listed (same name, different capture); the run does not stop |
| V78b | The two `filter` runs | without `--skip-duplicates`: the copies inside the AOI are listed, count = V77a + the copies of `0001SET`; with it: same count as `cross_all_lay.csv` (V77a), dropped copies listed |
| V78c | `aoi copy $Dup "$Res\cross_all_dup.csv" --skip-duplicates --dry-run` | same capture and file count as V77b; the `old_subset` copies shown as skipped duplicates |
| V78d | `verify "$Demo\data\blueberry_layered_dup_mapping.csv" "$Res\cross_all_flat.csv" "$Res\cross_all_dup.csv"`, then with `cross_all_dup_skip.csv` | first: `RESULT: SAME` plus *Captures found more than once in the layered subset* with the number of copies and the `--skip-duplicates` hint; second: `RESULT: SAME` with no copies listed |
| V79 | Optional, **MATLAB on the layered copy**: as in 2.7, run `BUILD_PROJECT_IMAGE_INDEX.m` on `$Lay`, `EXPORT_CSV_WITHIN_KML_AREA.m` with `blueberry_aoi_cross_all.kml`, `COPY_GEOTIFFS_FROM_CSV.m`; move every output out of `$Lay` to `$Res\matlab_lay_*` right away. Then `compare_outputs.py csv "$Res\lay_index.csv" "$Res\matlab_lay_index.csv"`, `compare_outputs.py tree "$Res\lay_copy_folders" "$Res\matlab_lay_copy"` and `verify $Map "$Res\cross_all_flat.csv" "$Res\matlab_lay_cross_all.csv"` | `RESULT: SAME` in all three (MATLAB record names match through the mapping); note anything MATLAB does differently with the repeated image names |

---

## Phase 4: real campaign data

> **Privacy first. Read this before you start.**
> - Only **anonymous numbers** go into this file and into issues: counts, times, sizes,
>   percentages, metres.
> - **Never** commit or paste: coordinates, campaign / field / client names, folder paths of the
>   campaign drive, KMLs of real fields, CSVs, reports, screenshots of maps or images.
> - Every input and output of this phase stays in `C:\uav-demo\private` (outside the clone) or on
>   the campaign drive; nothing from here goes to `examples/` or `docs/images/`.
> - Before every commit: `git status` and `git diff` show changes to `docs/VALIDATION.md` only.

```powershell
$Priv = "C:\uav-demo\private"                 # all Phase 4/5 outputs
$Camp = "<path to the campaign root>"         # e.g. D:\<campaign>; never written down here
New-Item -ItemType Directory -Force $Priv | Out-Null
```

| ID | Check | Expected |
|---|---|---|
| V80 | **Scale and time.** `Measure-Command { aoi index $Camp --exclude "<calibration folder>" --out "$Priv\index.csv" \| Out-Default }`; watch Task Manager for the Python process | completes; progress bar works for the whole run; note captures, files, folders (`(Get-ChildItem $Camp -Recurse -Directory).Count`), total time, seconds per 1,000 captures and peak memory |
| V81 | **Incomplete and GPS-less captures.** Read the summary of V80 | the counts are plausible for what you know of the campaign; for 2–3 examples of each list, check in Explorer why (missing band file, empty file, no GPS fix at take-off); describe the reasons in words, no names |
| V82 | **Several days and flights.** `aoi footprint "$Priv\index.csv" --out "$Priv\fp_flights.kml" --per-folder 2` (or the depth of the flight folders); in Excel, the `CaptureTime` column | one polygon per flight, none spanning two days by mistake; the number of flights and days matches the field log; "extra copies" in V80 = 0 (IMG numbering restarts in every SET, which must **not** count as a copy) |
| V83 | **Hard links at scale.** Draw a real AOI (kept in `$Priv`), filter it, then `Measure-Command { aoi copy $Camp <subset CSV> --mode hardlink --dest "<same drive>\<folder>" \| Out-Default }` | "Space needed: 0 bytes"; free space on the drive unchanged afterwards; files = captures × bands; note time |
| V84 | **Old MATLAB results.** For a MATLAB index and subset CSV made earlier on this campaign: `uv run python scripts\compare_outputs.py csv "$Priv\index.csv" <old MATLAB index CSV>` and the same for a subset made with the same KML | `RESULT: SAME`, or every difference explained (e.g. folders added or renamed since the MATLAB run); note the largest position difference |
| V85 | **Copy layout and report at scale.** `aoi copy $Camp <subset CSV> --dest "$Priv\copy_v85"`; open the report in Excel | report opens; statuses plausible; no long-path warning (or note the longest path) |
| V86 | **AOI across two flights** (V73 on real data) | captures from both flights, counts per flight noted; no "extra copies" |
| V87 | **Photogrammetry check.** Process one subset (V83 or V85) in Pix4Dmapper and compare with the earlier processing of the full campaign over the same area | note, numbers only: images used / calibrated (%), GSD, mosaic area, camera RMS, and the visible offset of the mosaic edge from the AOI in metres; the subset product covers the AOI except for a strip at the edges (see README, *Positional accuracy*) |

---

## Phase 5: real data, ROOT one level too high

Users will often point ROOT at a folder above the campaign. Same privacy rules as Phase 4.

| ID | Check | Expected |
|---|---|---|
| V90 | **Drive root.** On the campaign drive (not `C:`): `aoi index D:\ --out "$Priv\drive_index.csv"`, then `aoi copy D:\ "$Priv\drive_index.csv" --dry-run`, then `aoi index D:\ --out "$Priv\drive_index2.csv"` once more | no crash, no traceback; `System Volume Information` and `$RECYCLE.BIN` are skipped without a message; folders that cannot be read appear under *Folders not scanned*; captures = all campaigns on the drive. copy: `Output folder: D:\D_subset_01` and the warning that it is inside ROOT. Without `--out`, the index would be `D:\D_image_index_YYYYMMDD.csv` (or a clear "cannot write … permission denied" message with the `--out` hint). Delete the outputs afterwards. |
| V91 | **Parent folder with old MATLAB subset folders.** ROOT = the folder that holds the campaign **and** old MATLAB copy outputs (folders of `IMG_####_#.tif` copies). `aoi index <parent> --out "$Priv\parent_index.csv"`; then filter it with the V83 AOI once without and once with `--skip-duplicates`; then `aoi copy <parent> <subset CSV> --skip-duplicates --dry-run` | index: "extra copies" = the number of captures in the old MATLAB folders (if they kept their GPS tags), listed with both folders; never stops. With `--skip-duplicates`, filter and copy give the same capture count as V83 on the clean campaign folder. `--exclude "<old subset folder>"` gives the same result as an alternative. |
| V92 | **Folder with photogrammetry projects and other files.** ROOT = a folder with Pix4D project folders, reports, mosaics, spreadsheets next to the images. `Measure-Command { aoi index <folder> --out "$Priv\mixed_index.csv" \| Out-Default }` | unrelated files ignored; anything the photogrammetry software wrote that matches `IMG_####_#.tif` shows up as "extra copies" or under "without GPS" and can be removed with `--exclude "<project folder>"`; note the scan time compared with V80 |
| V93 | **Scan benchmark.** `cd $Repo; uv run python scripts\bench_scan.py --dir $Priv` (synthetic, no real data), and once with `--dir` on the campaign drive | completes, "Captures: 3,000 (expected 3,000)"; note files/s for both drives |

---

## Finish and clean up (only when every check has passed)

1. Prepare the README assets listed in [RELEASE.md](RELEASE.md), section A.
2. Fill in the results tables below. Use numbers only: no coordinates, no work paths, no user
   names, no campaign or field names (Phase 4 and 5 above all).
3. Commit and push:

   ```powershell
   cd $Repo
   git status                       # only docs/, examples/ and docs/images/ should change;
                                    # nothing from Phase 4/5 except numbers in this file
   git add docs examples
   git commit -m "Record real-data validation results and README assets"
   git push
   git log origin/main -1 --format="%h %an <%ae> %s"    # check that the push arrived
   ```

4. Check on GitHub that the commit, the images and the KMLs are there and that CI is green.
5. Remove the temporary setup:

   ```powershell
   cd $Demo
   Remove-Item -Recurse -Force $Repo, $Res, $Priv, "$Demo\phase1", "$Demo\data\blueberry_subset_*", "$Demo\data\blueberry_layered*", "$Demo\data\lay_ctrl_c", "$Demo\data\linked_north", "$Demo\data\move_src", "$Demo\data\move_dst", "$Demo\data\Saha Fotoğrafları – deneme" -ErrorAction SilentlyContinue
   cmdkey /list | Select-String github           # stored GitHub credentials
   cmdkey /delete:git:https://github.com         # remove them (repeat for each one listed)
   uv cache clean
   ```

   Also delete the Phase 5 outputs on the campaign drive (`D:\D_subset_*`,
   `D:\D_image_index_*.csv`, `<parent>_subset_*`, see the Phase 5 checks) and anything the
   Phase 1 `uv tool install` added (`uv tool uninstall uav-aoi-subset`).
   Keep or delete the dataset (`$Data`), ExifTool, uv and Git as you prefer.
6. On the Mac: `git pull`, then tell Claude that validation is done (see RELEASE.md, section B).

## Results

Commit tested: `_______`  Date: `__________`  Windows version: `______`  Python: `____`
ExifTool: `_____`  LongPathsEnabled: `_`  Dataset ZIP size: `20,822,285,409 bytes`
Dataset folder layout: `one folder, 3,361 files (3,360 TIFFs + 1 CSV), no sub-folders`

Numbers only. Phase 4 and 5 rows never contain coordinates, campaign or field names, paths or
screenshots.

### Phase 1: install like an ordinary user

| ID | Result (pass / fail / n.a.) | Numbers / notes | Issue # |
|---|---|---|---|
| P1 | | Windows version, admin?, winget?, execution policy, tools present | |
| P2 | | uv route, minutes | |
| P3 | | ExifTool route, minutes | |
| P4 | | Git or ZIP, minutes | |
| P5 | | minutes from start to --version | |
| P6 | |  | |
| P7 | |  | |

Snag log (copy from your notes; one row per snag):

| Step | What I expected | What happened | How I solved it | Time (min) | Issue # |
|---|---|---|---|---|---|
| uv: `uv --version` | version | not recognized in the window used for the install | closed and opened a new window | 1 | README step 1 wording (commit after 82b0c10) |
| ExifTool: `winget install --id OliverBetz.ExifTool -e` | installed into a folder of its own | installed for the user under `AppData\Local\Programs` | left as it is; on `PATH` (checked in the environment variables, 2 min) | 2 | README step 2 note |
| Git: `git clone …` | clone | Git not installed, so the command failed | `winget install --id Git.Git -e --source winget` | 10 | README steps 0 and 3 |
| Git: `git clone …` | clone | sign-in requested (repository still private) | signed in through the browser | 10 | none (public repo needs no sign-in) |

### Phase 2: blueberry dataset

| ID | Result (pass / fail / n.a.) | Numbers / notes | Issue # |
|---|---|---|---|
| V1 | | | |
| V4 | | | |
| V10 | | captures / complete / with GPS / time | |
| V11 | | Excel column split? | |
| V12 | | | |
| V13 | | | |
| V14 | n.a. | no panel captures in the dataset | |
| V20 | | area (ha) | |
| V20a | | area (ha), ratio used | |
| V20b | | | |
| V20c | | buffer that matches Pix4D best | |
| V20d | | one `(root)` polygon, 480 captures? | |
| V20e | | captures inside | |
| V20f | | | |
| V20g | | | |
| V21 | | captures inside | |
| V22 | | | |
| V23 | | | |
| V24 | | | |
| V25 | | largest position difference | |
| V26 | | | |
| V27 | | ours: … MATLAB: … | |
| V30 | | | |
| V31 | | files / size / time | |
| V32 | | | |
| V33 | | time | |
| V33a | | | |
| V34 | | | |
| V35 | | | |
| V36 | | | |
| V37 | | | |
| V38 | | | |
| V39 | | | |
| V40 | | | |
| V41 | | Explorer / Pix4D can open? | |
| V42 | n.a. | no panel captures in the dataset | |
| V43 | | | |
| V44 | | | |
| V45 | | | |
| V46 | | | |
| V50 | | image count (names unchanged here; renamed files: V77e) | |
| V51 | | | |
| V52 | | | |
| V60 | | sharp on high DPI? in front? | |
| V61 | | | |
| V62 | | | |
| V63 | | | |
| V64 | | | |
| V65 | | | |
| V66 | | | |
| V67 | | | |
| V68 | | | |
| V69 | | | |

### Phase 3: same data, different KMLs and a layered copy

| ID | Result (pass / fail / n.a.) | Numbers / notes | Issue # |
|---|---|---|---|
| V70 | | captures inside (vs. V21) | |
| V71 | |  | |
| V72 | |  | |
| V73 | n.a. | replaced by V77 (one-folder dataset) | |
| V74 | | build time; README unclear points | |
| V74a | |  | |
| V74b | |  | |
| V75 | | flight-line direction; numbering back and forth? | |
| V76 | | captures / extra copies / time | |
| V76a | | strips (polygons, captures each) | |
| V77 | |  | |
| V77a | | cross_all: flat / layered / per set; cross_two: flat / layered / per set | |
| V77b | | files / time | |
| V77c | |  | |
| V77d | | cross_all / cross_two result | |
| V77e | | images loaded; bands grouped with renamed files? which layout works? | |
| V77f | |  | |
| V78 | |  | |
| V78a | | captures / extra copies | |
| V78b | | count without / with --skip-duplicates | |
| V78c | |  | |
| V78d | |  | |
| V79 | | optional; differences, if any | |

### Phase 4: real campaign data (anonymous numbers only)

| ID | Result (pass / fail / n.a.) | Numbers / notes | Issue # |
|---|---|---|---|
| V80 | | captures / files / folders / time / s per 1,000 captures / peak RAM | |
| V81 | | complete / incomplete / without GPS / extra copies | |
| V82 | | flights, days, polygons | |
| V83 | | captures inside, files, time, space used | |
| V84 | | largest position difference; differences explained? | |
| V85 | |  | |
| V86 | | captures per flight | |
| V87 | | images calibrated %, GSD, area, RMS, edge offset (m) | |

### Phase 5: real data, ROOT one level too high

| ID | Result (pass / fail / n.a.) | Numbers / notes | Issue # |
|---|---|---|---|
| V90 | | time; folders not scanned; output names | |
| V91 | | extra copies vs. old subset sizes; counts after --skip-duplicates | |
| V92 | | files scanned, time vs. clean folder; anything matched? | |
| V93 | | files/s (Mac: 0.7–1.1 million/s, warm cache) | |

### Findings to fix on the Mac

One line per finding, with its issue number:

1. …
