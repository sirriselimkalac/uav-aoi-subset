# Release preparation (v0.1.0)

The repository becomes public **only** when:

1. every check in [VALIDATION.md](VALIDATION.md) (all five phases) has passed on the work
   computer, on the commit that will be tagged (or on an earlier commit, with the later fixes
   re-validated there), and every issue opened during validation is closed;
2. the assets in section A are committed;
3. the README is complete (section B).

Untested code is never made public.

## A. Assets to prepare on the work computer

Prepare these **after** all validation checks have passed, so the screenshots show the final
version. Commit them from the work computer (VALIDATION.md, *Finish and clean up*) before the
clone there is deleted. Assets come from the public blueberry dataset only (Phases 2–3), never
from the real campaign data of Phases 4–5.

### A1. Example AOI files: `examples/`

| File | Content |
|---|---|
| `examples/blueberry_aoi_north.kml` | one simple polygon over part of the blueberry field |
| `examples/blueberry_aoi_blocks.kml` | two polygons, one with a hole |
| `examples/blueberry_aoi_north.kmz` | the same as the first one, as KMZ |
| `examples/blueberry_footprint.kml` | output of `footprint` for the whole dataset (V20) |
| `examples/blueberry_aoi_cross_all.kml` | a band across the flight lines that crosses all four set folders of the layered copy (V77) |
| `examples/blueberry_aoi_cross_two.kml` | a shorter band across the border of two set folders only (V77) |
| `examples/README.md` | one line per file: what it shows and the capture count it gives with `filter` |

Before you commit them, open each KML in Notepad and check:

- [ ] Only the AOI placemarks are in it. Nothing from *My Places*, and no other locations.
- [ ] Names are neutral English, like `North block`. No personal or company names, no file paths.
- [ ] All coordinates lie over the public blueberry field.
- [ ] Each file loads with `aoi filter` (V21–V23 and V77a in VALIDATION.md).

### A2. Screenshots: `docs/images/`

General rules:

- PNG, cropped to the relevant window, at most 1600 px wide, preferably under 400 KB each
  (*Snipping Tool* → *Window* mode).
- Use the short `C:\uav-demo\...` paths. Your user name, the company name, e-mail, the taskbar,
  other windows and notifications must not appear.
- Terminal: a clean prompt (`function prompt { "PS> " }`), a large enough font, and the same
  window size in every terminal shot.
- Keep the Google imagery attribution visible in Google Earth screenshots. Google's terms
  require it.

| File | What it shows |
|---|---|
| `01_google_earth_aoi.png` | Google Earth Pro: the footprint and the AOI polygons over the field |
| `02_google_earth_captures.png` | capture positions (index CSV imported as points), with the subset inside the AOI visible |
| `03_index.png` | terminal: `index` summary |
| `04_filter.png` | terminal: `filter` summary for the north AOI |
| `05_copy_dry_run.png` | terminal: `copy --dry-run` summary |
| `06_copy.png` | terminal: `copy` summary, including the report path |
| `07_output_folder.png` | Explorer: the flat output folders and the report CSV next to them |
| `08_copy_report.png` | the copy report CSV opened in Excel (a few rows) |
| `09_pix4d_import.png` | Pix4Dmapper: the subset images loaded / the camera positions on the map |
| `10_pickers.png` | *(milestone 6)* a file/folder picker opened by a command run without arguments |
| `11_layered_footprint.png` | Google Earth Pro: the four-strip `--per-folder 1` footprint of the layered copy (V76a) with the two cross AOIs |
| `12_verify.png` | terminal: `make_layered_dataset.py verify` printing `RESULT: SAME` (V77d) |
| `13_layered_output_folder.png` | Explorer: the flat output of `copy` from the layered copy, with files such as `0000SET_000_IMG_0000_1.tif` and `0001SET_000_IMG_0000_1.tif` side by side (V77b) |

### A3. Facts for the README

Write these into the results section of VALIDATION.md. It will be committed together with the
assets.

- [ ] Dataset citation: exact title, publisher/authors, year, landing-page URL, DOI if any,
      **licence**. Copy them from the download page.
- [ ] Dataset folder layout: one folder, 3,361 files (known; confirm in 2.1).
- [ ] The exact commands used for the worked example, as run.
- [ ] Counts: captures in the index, captures inside each example AOI, files copied, size.
- [ ] Timings: `index` (ours and MATLAB), `copy`, the resume run, `make_layered_dataset.py build`
  (hard links) and `index` of the layered copy.
- [ ] Layered copy: the commands of the README walk-through as run, counts per set folder for
  both cross AOIs, and anything in that README section that was unclear (V74).
- [ ] Windows notes found during validation: ExifTool install, long paths, Excel and CSV
      separators, antivirus slow-downs.
- [ ] Known limitations to state in the README.

## B. On the Mac, after the work computer is done (Claude does this)

1. `git pull`. Check the new files and the results table. Every check is pass or n.a.
2. Fix findings, if any. A fix that changes behaviour needs another visit to the work computer
   before release.
3. Write the final README:
   - overview, the pipeline diagram, a short "why";
   - installation (macOS / Windows / Linux, ExifTool);
   - a worked example with the blueberry dataset (link only), the commands, the screenshots and
     the counts;
   - command reference for `index`, `filter`, `copy` and `footprint`;
   - safety notes (`--dry-run`, resume, `--confirm-move`, the marker file), limitations;
   - how to cite the dataset, licence.
   - Check the *Optional: a layered copy of the example data* section against the V74 notes and
     add the screenshots 11–13 and the cross AOIs there.
   - Remove the "work in progress" status note.
   - Keep the "Positional accuracy" section; add measured numbers only if the user gives them.
   - Never fill in the `<!-- AUTHOR: ... -->` blocks: ask the user to write them (why the tool
     exists, how it was built, author/contact, the optional field note).
4. Public gate. Check each item:
   - [ ] `docs/IS_BILGISAYARI.md` (internal notes for the work-computer sessions) is deleted.
   - [ ] `git log -p --all` contains no private paths, real campaign or project names, or
         coordinates other than the blueberry field. Search for terms such as `C:\Users`,
         `/Users/`, campaign names and `.tif`.
   - [ ] `git rev-list --objects --all` contains no imagery, archives or Pix4D files.
   - [ ] README links work, images render, the CI badge is green.
   - [ ] No `<!-- AUTHOR:` placeholder is left in README.md (`grep -n "AUTHOR:" README.md`):
         the user has written every block.
   - [ ] CLI help (`uav-aoi-subset --help`, each command's `--help`) names no camera, drone or
         photogrammetry software brands. In README.md, brands appear ONLY in the
         "Tested setup and compatibility" section (which must still be present, complete
         and marked `<!-- KEEP -->`) and in the dataset citation.
   - [ ] Package metadata in `pyproject.toml` (description, keywords, classifiers) names no
         camera, drone or photogrammetry software brands.
   - [ ] Version `0.1.0` in `pyproject.toml`; `uv lock`; the classifier is still
         "Pre-Alpha"/"Alpha" as appropriate.
   - [ ] The commit author email on all commits is the GitHub noreply address.
5. Make the repository public, tag `v0.1.0` and create a GitHub release with short notes.
