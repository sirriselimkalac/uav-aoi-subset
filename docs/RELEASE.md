# Release preparation

The release happens in two stages:

Decided 2026-11-08: the repository goes public only **after** the Monday checklist has passed,
together with v0.1.0; the Monday agent works from [MONDAY_RUN.md](MONDAY_RUN.md).

- **A. Public gate**. The code is tested
  automatically on Windows, macOS and Linux, and was run on the public blueberry dataset and
  its layered copy on a Linux machine (see [VALIDATION.md](VALIDATION.md), *Pre-release run*).
- **B. v0.1.0** (after the Monday run on the work computer): the manual checklist in
  [VALIDATION.md](VALIDATION.md) has passed, the example files and images are committed, the
  README worked example is written, then the tag.

## A. Make the repository public (no tag)

Claude prepares and checks; the user switches the visibility on GitHub.

- [ ] `docs/IS_BILGISAYARI.md` and `docs/MONDAY_RUN.md` (internal work-computer notes) are
      deleted, and the Monday notes are gone from `CLAUDE.md`.
- [ ] `git log -p --all` contains no private paths, user names, real campaign or project
      names, or coordinates other than the blueberry field and synthetic test values. Search
      for `C:\Users`, `/Users/`, drive paths and coordinate-like numbers.
- [ ] `git rev-list --objects --all` contains no imagery, archives or photogrammetry project
      files.
- [ ] The commit author email on all commits is the GitHub noreply address.
- [ ] CLI help (`uav-aoi-subset --help`, each command's `--help`) and the package metadata in
      `pyproject.toml` name no camera, drone or photogrammetry software brands.
- [ ] In README.md, brands appear ONLY in *Tested setup and compatibility* (still present,
      complete and marked `<!-- KEEP -->`) and in the dataset citation.
- [ ] README links work (the mosaic image is added in stage B), the CI badge is green.
- [ ] `examples/blueberries.kml` and `examples/area-of-interest.kml` pass the example-file
      checks in B1; `docs/area-of-interest-v1.kml` (outside the field) stays ignored.
- [ ] The remaining `<!-- AUTHOR:` blocks are listed for the user (`grep -n "AUTHOR:" README.md`).
- [ ] The user makes the repository public. No tag yet.

## B. After the Monday run: v0.1.0

### B1. Assets (made on the work computer, from the public blueberry dataset only)

Example AOI files in `examples/` (committed before the repository goes public):

| File | Content |
|---|---|
| `examples/blueberries.kml` | outline of the field: `footprint` of all capture positions (5.89 ha; 480 captures) |
| `examples/area-of-interest.kml` | the user's AOI of about 1 ha inside the field (74 captures; 113 on the layered copy) |
| `examples/README.md` | one line per file: what it shows and the capture count `filter` gives |

Possibly later: a band across the flight lines (shows the same file name from different set
folders), a KML with a hole, a KMZ. For every new example file, open it in a text editor and
check:

- [ ] Only the AOI placemarks are in it. Nothing from *My Places*, no Google Earth web
      extension data (`ex:extension`), no other locations.
- [ ] Names are neutral English, like `Area of interest`. No personal or company names, no paths.
- [ ] All coordinates lie over the public blueberry field.
- [ ] Each file loads with `filter` and gives the count in `examples/README.md`.

Images in `docs/images/` (PNG, cropped to the window, at most 1600 px wide, preferably under
400 KB; no user name, company name, e-mail, taskbar or notifications; keep the Google imagery
attribution visible in Google Earth shots):

| File | What it shows |
|---|---|
| `blueberry_mosaic_extent.png` | the processed mosaic extent of the example dataset shown in Google Earth (the README already links to it) |
| `01_google_earth_aoi.png` | `blueberries.kml` and `area-of-interest.kml` over the field |
| `02_index.png` | terminal: `index` summary |
| `03_copy.png` | terminal: `copy` summary, including the report path |
| `04_layered_footprint.png` | the `--per-folder 1` footprint of the layered copy with `examples/area-of-interest.kml` |
| `05_verify.png` | terminal: `make_layered_dataset.py verify` printing `RESULT: SAME` |

Facts for the README, written into the VALIDATION.md results: the exact commands as run,
capture counts per AOI, files copied and size, timings of `index`, `copy` and the resume run,
anything in the README that was unclear.

### B2. Release (on the work computer, by the agent there; see MONDAY_RUN.md)

1. `git pull`. Every check in VALIDATION.md is pass or n.a.; every issue is closed or fixed.
2. Fix findings, if any. A fix that changes behaviour is re-checked before the tag.
3. README: add the images to *Example dataset*, check its commands and counts and the
   *layered copy* section against the Monday notes, keep *Positional accuracy*
   and *Tested setup and compatibility*. Never fill in the `<!-- AUTHOR: ... -->` blocks: the
   user writes them.
4. Version `0.1.0` in `pyproject.toml`, `uv lock`; classifier "Alpha" (done 2026-11-08).
5. CI green, then the user approves: tag `v0.1.0` and a GitHub release with short notes.
