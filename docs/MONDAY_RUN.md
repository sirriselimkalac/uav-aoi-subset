# Monday run on the work computer (2026-11-09): checklist, assets, v0.1.0

Internal runbook for the AI agent on the work computer. It is **deleted before the repository
goes public** (last step). Everything the agent needs is in this file, `CLAUDE.md`,
`docs/VALIDATION.md` and `docs/RELEASE.md`; the Mac session that wrote it is not available.

## Prompt for the agent

Copy this into the agent session, started inside the clone (or in `D:\uav-demo` if there is no
clone yet):

```text
You are working on the uav-aoi-subset repository (private on GitHub until today's checks pass).
First run `git pull`, then read CLAUDE.md and docs/MONDAY_RUN.md completely, and follow
docs/MONDAY_RUN.md step by step. Talk to me in Turkish; write everything in the repository in
English. Rules: never commit data, outputs, Pix4D files, screenshots of anything other than the
public blueberry dataset, coordinates other than the example files, work paths, user or computer
names. Results contain numbers only. Do not edit the <!-- AUTHOR: --> blocks in README.md. No
force push, no history rewrite. Create the v0.1.0 tag only when every check is pass or n.a.,
CI is green, and I have said yes in this session. Never change the repository visibility: I do
that myself. If something is unexpected (counts differ, a command fails, CI red), stop and tell
me what you saw instead of guessing.
```

## Context (what is already done)

- The code is finished for v0.1.0; `pyproject.toml` already says `0.1.0`. CI is green on
  Windows, macOS and Linux (3.11 and 3.12).
- The whole checklist already ran, scripted, on a Linux server with the same dataset: every
  check passed (numbers in `docs/VALIDATION.md`, *Pre-release run*). Today's run is the
  hands-on Windows run: NTFS hard links, PowerShell, the Windows console, Google Earth Pro, and
  a person following the README.
- Expected numbers: 480 captures (all complete, all with GPS); `examples/area-of-interest.kml`
  → 74 captures, 518 band files; `examples/blueberries.kml` → 480; layered copy (`--add-duplicate`)
  → 600 captures, 120 extra copies; area-of-interest on the layered copy → 113 (39 copies), 74
  with `--skip-duplicates`, `verify` → `RESULT: SAME`.
- On this computer (from the user, 2026-11-08):
  - the dataset is downloaded and extracted (one folder, 3,361 files):
    `D:\altum-pt-blueberries-60m-sample-data\altum-pt-blueberries-60m-sample-data`;
  - the photogrammetry project next to it is processed: orthomosaics exist, and a KML for the
    blue-band mosaic was generated (used only for the `blueberry_mosaic_extent.png`
    screenshot; it is never committed);
  - the installation from the README was started earlier (Phase 1); four snags were found and
    the README was fixed (VALIDATION.md *Snag log*). Where it stopped is unknown, and the tool
    has not been run on the dataset yet.

## Step 1. Where are we? (installation state)

In a new PowerShell window:

```powershell
winget --version; git --version; uv --version; exiftool -ver
Get-ChildItem C:\uav-demo, D:\uav-demo -ErrorAction SilentlyContinue
Get-PSDrive C, D
```

- Find an existing clone (earlier: `C:\uav-demo\phase1\uav-aoi-subset`, or
  `D:\uav-demo\uav-aoi-subset`). Use **`D:\uav-demo\uav-aoi-subset`** for today: clone it there if
  it does not exist (`git clone https://github.com/sirriselimkalac/uav-aoi-subset.git`, the
  browser sign-in is expected while the repo is private). An old Phase 1 clone may be deleted
  after `git status` shows nothing unpushed.
- Repo-local identity in the clone (never the global one):
  `git config user.name "Sırrı Selim Kalaç"` and
  `git config user.email "260359645+sirriselimkalac@users.noreply.github.com"`.
- Continue the README *Installation* from the first step that is not done (uv, ExifTool, Git,
  `uv sync`, `uv run uav-aoi-subset --version`). Follow only the README; every snag (something
  that does not work at once) becomes a row in the VALIDATION.md *Snag log*. If the README
  is wrong, fix it in the same commit.
- D: needs about 15 GB free (copies in M7 and M16; hard links need nothing).

## Step 2. The checklist (about one hour)

Run `docs/VALIDATION.md` *Setup*, then M1–M18 in order, with these values:

```powershell
$Demo = "D:\uav-demo"
$Repo = "$Demo\uav-aoi-subset"
$Data = "D:\altum-pt-blueberries-60m-sample-data\altum-pt-blueberries-60m-sample-data"
```

- `$Lay`, the M9 `--dest` and all hard-link outputs must be on **D:** (same drive as `$Data`).
  If a cross-drive refusal is to be seen, use a `--dest` on C: with `--mode hardlink` (it must
  refuse) and delete it afterwards.
- The user does the Google Earth Pro parts (M3 look, M4 drawing `blocks.kml` with a hole and the
  KMZ, M12 drawing `cross.kml`, M14 look). These hand-drawn files are test files: they stay in
  `$Aoi` and are **not committed**.
- Note for each check: pass / fail / n.a., the numbers asked for, times of M2, M7, M8, M11.
- A failed check: tell the user, write it down, and either (a) fix it now if it is small and
  clear (with a test, `uv run ruff check`, `uv run ruff format`, `uv run pytest`, then re-run the
  affected checks), or (b) open a GitHub issue with the bug report form (no paths, names or
  coordinates) and put its number in the table. Ask the user which.
- The *Results* table: commit tested, date, Windows version, Python, ExifTool, then one row per
  check. Commit and push the results as soon as M1–M18 are done (before the assets).

## Step 3. Assets for the README (RELEASE.md B1)

The user takes the screenshots; the agent checks them and puts them into `docs/images/`.
Requirements: PNG, cropped to the window, at most 1600 px wide, preferably under 400 KB; no user
name, company name, e-mail, taskbar or notifications; the Google imagery attribution stays
visible. Check size and width with
`uv run --with pillow python -c "from PIL import Image; import sys; im=Image.open(sys.argv[1]); print(im.size)" FILE`
and resize with Pillow if needed (keep the aspect ratio).

| File | What it shows |
|---|---|
| `blueberry_mosaic_extent.png` | the processed blue-band mosaic extent (its KML) in Google Earth Pro, with `examples/blueberries.kml` on top. The README already links to it. |
| `01_google_earth_aoi.png` | `examples/blueberries.kml` and `examples/area-of-interest.kml` over the field |
| `02_index.png` | terminal: the `index` summary (M2) |
| `03_copy.png` | terminal: the `copy --mode hardlink` summary with `Space needed: 0 bytes` and the report path |
| `04_layered_footprint.png` | the `--per-folder 1` footprint of the layered copy (M14) with `examples/area-of-interest.kml` |
| `05_verify.png` | terminal: `make_layered_dataset.py verify` printing `RESULT: SAME` (M17) |

Terminal screenshots must not show user names or work paths: run them from a short prompt
(for example `function prompt { "PS> " }`) and crop paths out where needed.

Then in README.md, section *Example dataset*: keep the mosaic image where it is; put
`01_google_earth_aoi.png` after the example-files table, `02_index.png` and `03_copy.png` after
the one-folder commands, `04_layered_footprint.png` and `05_verify.png` after the layered-copy
commands, each with a short alt text. Check that every count in that section matches today's
results; if one differs, stop and ask.

## Step 4. Public gate (RELEASE.md A), then v0.1.0

1. `git pull` (the user may have pushed the AUTHOR texts). List what is still open:
   `Select-String -Path README.md -Pattern "AUTHOR:"`. Tell the user; never write those
   blocks yourself.
2. Privacy and brands, report the results to the user:

   ```powershell
   git log -p --all | Select-String -SimpleMatch -Pattern "C:\Users", "/Users/", "D:\"
   git log --format=%ae | Sort-Object -Unique        # only the noreply address
   git rev-list --objects --all | Select-String -Pattern "\.(tif|tiff|zip|p4d|jpg|jpeg)$"
   uv run uav-aoi-subset --help                      # and each command's --help: no brands
   ```

   `D:\` and `C:\Users` hits in the docs that only describe paths are fine; anything with a
   real user name, a work path other than the public dataset, or coordinates outside the
   blueberry field is not: stop and tell the user. Images: only the six PNGs above.
3. Delete this file (`git rm docs/MONDAY_RUN.md`) and update `CLAUDE.md` *Status* / *Next*:
   milestone 7 and 8 done (with the date and test count), remove the Monday notes (the `D:`
   paths), next = "v0.1.0 released; feedback from users". Remove the matching line from
   RELEASE.md A. Commit, push, and wait until CI is green on all 6 jobs (`gh run watch` if `gh`
   is installed, otherwise the Actions page in the browser).
4. Ask the user: "Every check is pass or n.a. and CI is green. Shall I create the v0.1.0 tag?"
   On yes:

   ```powershell
   git pull
   git status                                   # must be clean
   git tag -a v0.1.0 -m "uav-aoi-subset 0.1.0"
   git push origin v0.1.0
   git ls-remote --tags origin                  # shows refs/tags/v0.1.0
   ```

   Never move or delete the tag after it is pushed; a later fix becomes v0.1.1.
5. GitHub Release: with `gh`: `gh release create v0.1.0 --title "v0.1.0" --notes-file <file with
   the notes below>`. Without `gh`, the user does it in the browser: repository page →
   *Releases* → *Draft a new release* → choose tag `v0.1.0` → title `v0.1.0` → paste the notes →
   *Set as the latest release* → *Publish release*.
6. Tell the user that the repository can now be made public (*Settings → General → Danger
   Zone → Change visibility*). The agent never does this. After that: delete the clone if it was
   only for today, and the stored GitHub credentials (Windows *Credential Manager* → *Windows
   Credentials* → `git:https://github.com`), as the user wishes.

## Release notes for v0.1.0 (draft; adjust to today's results)

```markdown
First public release (alpha).

uav-aoi-subset splits very large drone image datasets (multispectral cameras that write one
file per band) into subsets that fall inside an area of interest drawn as a KML/KMZ polygon.

- `index`: scans a project folder at any depth, groups the band files into captures, checks
  that every band is present and reads the capture position from the GPS tags (ExifTool).
- `filter`: keeps the captures inside one or more AOI polygons (holes, optional buffer in metres).
- `copy`: puts the selected captures into a new sub-folder, one folder per source folder with
  the original file names; `--mode hardlink` needs no extra disk space. Resume, dry run, report
  CSV, copies of the same capture detected (`--skip-duplicates`).
- `footprint`: the outline of all capture positions as a KML polygon, also per flight folder.

Tested on Windows, macOS and Linux (automated tests), and by hand with the public
"Altum-PT data of a blueberry field" example dataset and a layered copy of it (see the README,
*Example dataset*, and `examples/`).

Requirements: Python 3.11 or newer (uv installs it), ExifTool.
Please report problems with the bug report form in Issues.
```
