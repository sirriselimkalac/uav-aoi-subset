# Real-data validation on the work computer (Windows)

**Do this first, every time the repository is pulled on the work computer.** This is the only
machine that has real imagery. The Mac (development machine) only ever sees synthetic test data.

The repository stays **private until every check below has passed** on the commit that will
become v0.1.0, and the README assets in [RELEASE.md](RELEASE.md) are committed.

The clone on the work computer is **temporary**. When validation and the README assets are
done, it is deleted (section 9). Only the Mac copy remains. So:

- everything worth keeping (results, KMLs, screenshots) must be **committed and pushed** from
  here before the clone is removed;
- data and outputs live **outside** the clone (in `C:\uav-demo\data` and `C:\uav-demo\results`),
  so `git status` only ever shows files meant for the repo.

If a check fails: write it down in the results table (section 10), commit and push the results,
fix it on the Mac, then `git pull` here and run the failed check and everything after it again.
Do not delete the clone while any check is open.

Dataset: EagleNXT *"Altum-PT data of a blueberry field"*. It has 480 captures × 7 bands =
3,360 TIFFs plus one calibration-panel reflectance CSV. It is public, but it is **never**
committed or redistributed; the README only links to it.

---

## 0. Before you start

- [ ] On GitHub, check the latest commit on `main` and its CI status (green on all 6 jobs).
- [ ] Read the *Status* section of `CLAUDE.md`. Sections marked *(milestone 5)* or
      *(milestone 6)* can only be checked once those milestones are done. It is best to come
      to the work computer when milestones 1–6 are all done, so one visit covers everything.

## 1. Setup (once)

PowerShell (not admin):

```powershell
# Tools. If winget is blocked, use the installers from the websites instead.
winget install --id Git.Git -e
winget install --id OliverBetz.ExifTool -e      # or the Windows build from https://exiftool.org
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# Open a NEW PowerShell window afterwards so PATH is updated.
git --version; exiftool -ver; uv --version
```

Folders and console encoding (run these at the start of every PowerShell session):

```powershell
$Demo = "C:\uav-demo"                      # short ASCII path, no user name in screenshots
$Repo = "$Demo\uav-aoi-subset"
$Data = "$Demo\data\blueberry"             # the extracted dataset: the folder that holds its image folders
$Aoi  = "$Demo\aoi"                        # KMLs drawn in Google Earth
$Res  = "$Demo\results"                    # every output of the checks
New-Item -ItemType Directory -Force $Demo, "$Demo\data", $Aoi, $Res | Out-Null
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"
function aoi { uv run --project $Repo uav-aoi-subset @args }   # short alias
```

Clone and sign in. The repository is private: on the first clone, Git Credential Manager opens a
browser window to sign in to GitHub. Section 9 removes the stored credentials again.

```powershell
cd $Demo
git clone https://github.com/sirriselimkalac/uav-aoi-subset.git
cd $Repo
# Identity for THIS repository only (does not touch your work Git settings):
git config user.name  "Sırrı Selim Kalaç"
git config user.email "260359645+sirriselimkalac@users.noreply.github.com"
git log -1 --format="%h %an <%ae>"
```

Download the dataset, extract it to `$Data`, then:

```powershell
(Get-ChildItem $Data -Recurse -Include *.tif,*.tiff -File).Count     # expect 3360
Get-ChildItem $Data -Recurse -Directory | Select-Object FullName      # note the folder layout
```

## 2. Unit tests on this machine

| ID | Step | Expected |
|---|---|---|
| V1 | `cd $Repo; uv sync --locked; uv run pytest` | all pass, **0 skipped** (ExifTool found) |
| V2 | `git rev-parse --short HEAD` | write the commit hash into the results table |
| V3 | `Get-ItemProperty HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem -Name LongPathsEnabled` | note the value (0 or 1); it matters for V41 |

## 3. index

```powershell
Measure-Command { aoi index $Data --out "$Res\ours_index.csv" | Out-Default }
```

| ID | Check | Expected |
|---|---|---|
| V10 | Summary | 480 captures, all complete, 480 with GPS, no ExifTool warnings. Write down the time. |
| V11 | Open `ours_index.csv` in Excel (double-click) | Note whether the columns split correctly. With a Turkish locale Excel may expect `;`. Turkish characters must display correctly. |
| V12 | Turkish path: `Copy-Item -Recurse $Data "$Demo\data\Saha Fotoğrafları – deneme"`, then `aoi index "$Demo\data\Saha Fotoğrafları – deneme" --out "$Res\tr_index.csv"` | same numbers as V10 |
| V13 | ExifTool not on PATH: `aoi index $Data --out "$Res\x.csv" --exiftool "<full path to exiftool.exe>"` with a PATH without ExifTool (`$env:Path = ($env:Path -split ';' \| ? { $_ -notmatch 'exiftool' }) -join ';'`) | works with `--exiftool`; without it, a clear "ExifTool was not found" error. Open a new window afterwards. |
| V14 | If the dataset contains calibration-panel captures in their own folder: `aoi index $Data --exclude "<panel folder>" --out "$Res\nopanel.csv"` | panel captures left out |

## 4. footprint *(milestone 5)*

| ID | Check | Expected |
|---|---|---|
| V20 | `aoi footprint "$Res\ours_index.csv" --out "$Aoi\blueberry_footprint.kml"`, open in Google Earth Pro | one polygon around the whole field |

## 5. Draw the AOIs in Google Earth Pro

Draw these in a **new, empty folder** under *Temporary Places* (not *My Places*), then right-click
the folder → *Save Place As… → KML*. They become the public examples (see RELEASE.md).

- `$Aoi\blueberry_aoi_north.kml`: one simple polygon over roughly the northern third of the field.
- `$Aoi\blueberry_aoi_blocks.kml`: two separate polygons, one of them with a hole (draw the hole
  as a second polygon and combine them, or edit the KML by hand to add `innerBoundaryIs`).
- `$Aoi\blueberry_aoi_north.kmz`: the same as the first one, saved as KMZ.

Tip: *File → Import* of `ours_index.csv` (latitude/longitude columns) shows the capture
positions as points, which helps with drawing and with V21–V24.

## 6. filter

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

## 7. Compare with the MATLAB scripts

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

## 8. copy

```powershell
$Dest = "$Demo\data\blueberry_subset_01"     # the default destination of the first run
aoi copy $Data $North.FullName --dry-run
```

| ID | Check | Expected |
|---|---|---|
| V30 | `--dry-run` | summary shows `Output folder: ...\blueberry_subset_01`; `Test-Path $Dest` is `False`; no report written |
| V31 | `Measure-Command { aoi copy $Data $North.FullName --include '**/*.csv' \| Out-Default }` | files copied = V21 × 7 (+ the reflectance CSV); output in `$Dest`, folders flat; report CSV next to `$Dest`; write down the time |
| V32 | `uv run python scripts\compare_outputs.py tree $Dest "$Res\matlab_copy_north"` | only differences are our extra report/include files, if any |
| V33 | Resume: `aoi copy $Data $North.FullName --include '**/*.csv' --dest $Dest` | everything skipped, exit code 0 (`$LASTEXITCODE`), takes seconds |
| V33a | New run without `--dest`: `aoi copy $Data $North.FullName --dry-run` | output folder is `blueberry_subset_02`; `$Dest` untouched. `Get-Content "$Dest\.uav-aoi-subset-output"` names the subset CSV |
| V34 | Interrupt: `aoi copy $Data "$Res\ours_index.csv" --dest "$Res\full_copy"`, press Ctrl+C after a few seconds, then run it again | no `*.uas-partial` files left (`Get-ChildItem "$Res\full_copy" -Recurse -Filter *.uas-partial`); the second run completes; 3,360 files in total |
| V35 | Conflict: `Set-Content "$Res\full_copy\<some folder>\IMG_0001_3.tif" "x"`, run again | exit code 1, the file is listed under *Conflicts* and left as it is; with `--overwrite` it is replaced |
| V36 | Report: open the newest `*_copy_report_*.csv` in Excel | one row per file; statuses are plausible |
| V37 | Hard links (same NTFS drive): `aoi copy $Data $North.FullName --mode hardlink --dest "$Demo\data\linked_north"` | "Space needed: 0 bytes"; `fsutil hardlink list "<a linked file>"` shows two paths |
| V38 | Move refused: `aoi copy $Data $North.FullName --mode move` | refused, asks for `--confirm-move`; nothing moved |
| V39 | Move on a **disposable copy** (never the original): copy `$Res\full_copy` to `$Demo\data\move_src`, delete `.uav-aoi-subset-output` in it, `aoi index $Demo\data\move_src --out "$Res\move_index.csv"`, then `aoi copy $Demo\data\move_src "$Res\move_index.csv" --dest "$Demo\data\move_dst" --mode move --confirm-move`; run it a second time | first run: all moved, no TIFFs left in `move_src`; second run: all "already at the destination", nothing reported missing |
| V40 | Destination inside the root: `aoi copy $Data $North.FullName --dest "$Data\_subset_test"`, then `aoi index $Data --out "$Res\after.csv"` | warning on copy; the index still shows 480 captures. Then delete `$Data\_subset_test`. |
| V41 | Long path: `aoi copy $Data $North.FullName --dest "$Res\$('a'*120)\$('b'*120)"` | warning about long paths; files exist. Note whether Explorer and Pix4Dmapper can open them. |
| V42 | Extra captures (if the dataset has panel captures): `--extra-captures <panel record names>` or a text file with one name per line | panel captures copied into their own flat folder |
| V43 | Other drive (USB stick or D:, optional): `--dest` on that drive with `--mode copy` | works |
| V44 | Same, with `--mode hardlink` | refused **before** anything is written ("hard links only work on one drive") |
| V45 | exFAT/FAT32 stick (optional): put a small subset folder on the stick as ROOT, index it, then `--mode hardlink` with a `--dest` on the stick | stops with the "may not support hard links … use --mode copy" message; no fallback to copying |
| V46 | Cross-drive move (optional, disposable copy as in V39, `--dest` on the other drive) | all moved; sources deleted only after each file is complete |

## 8b. Pix4Dmapper

| ID | Check | Expected |
|---|---|---|
| V50 | New project → *Add Directories…* → `$Dest` | all images load; camera rig recognised (Altum-PT); image count noted |
| V51 | Map view | camera positions lie inside the AOI |
| V52 | Optional: run step 1 (Initial Processing) | completes; calibration panel detected if included (V42) |

## 8c. File pickers *(milestone 6)*

| ID | Check | Expected |
|---|---|---|
| V60 | `aoi index` with no ROOT, `aoi filter` with no files, `aoi copy` with no arguments | folder/file pickers open; the result is the same as with arguments |

## 9. Finish and clean up (only when every check has passed)

1. Prepare the README assets listed in [RELEASE.md](RELEASE.md), section A.
2. Fill in the results table below. Use numbers only: no coordinates, no work paths, no user
   names.
3. Commit and push:

   ```powershell
   cd $Repo
   git status                       # only docs/, examples/ and docs/images/ should change
   git add docs examples
   git commit -m "Record real-data validation results and README assets"
   git push
   git log origin/main -1 --format="%h %an <%ae> %s"    # check that the push arrived
   ```

4. Check on GitHub that the commit, the images and the KMLs are there and that CI is green.
5. Remove the temporary setup:

   ```powershell
   cd $Demo
   Remove-Item -Recurse -Force $Repo, $Res, "$Demo\data\blueberry_subset_*", "$Demo\data\linked_north", "$Demo\data\move_src", "$Demo\data\move_dst", "$Demo\data\Saha Fotoğrafları – deneme" -ErrorAction SilentlyContinue
   cmdkey /list | Select-String github           # stored GitHub credentials
   cmdkey /delete:git:https://github.com         # remove them (repeat for each one listed)
   uv cache clean
   ```

   Keep or delete the dataset (`$Data`), ExifTool, uv and Git as you prefer.
6. On the Mac: `git pull`, then tell Claude that validation is done (see RELEASE.md, section B).

## 10. Results

Commit tested: `_______`  Date: `__________`  Windows version: `______`  Python: `____`
ExifTool: `_____`  LongPathsEnabled: `_`  Dataset folder layout: `________________________`

| ID | Result (pass / fail / n.a.) | Numbers / notes |
|---|---|---|
| V1 | | |
| V10 | | captures / complete / with GPS / time |
| V11 | | Excel column split? |
| V12 | | |
| V13 | | |
| V14 | | |
| V20 | | |
| V21 | | captures inside |
| V22 | | |
| V23 | | |
| V24 | | |
| V25 | | largest position difference |
| V26 | | |
| V27 | | ours: … MATLAB: … |
| V30 | | |
| V31 | | files / size / time |
| V32 | | |
| V33 | | time |
| V33a | | |
| V34 | | |
| V35 | | |
| V36 | | |
| V37 | | |
| V38 | | |
| V39 | | |
| V40 | | |
| V41 | | Explorer / Pix4D can open? |
| V42 | | |
| V43 | | |
| V44 | | |
| V45 | | |
| V46 | | |
| V50 | | image count |
| V51 | | |
| V52 | | |
| V60 | | |

Findings to fix on the Mac:

1. …
