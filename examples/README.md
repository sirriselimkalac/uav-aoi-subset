# Example files

Area-of-interest files for the public example dataset
[Altum-PT data of a blueberry field](https://eaglenxt.com/data-set/altum-pt-data-of-a-blueberry-field/)
(EagleNXT). The data itself is not in this repository; download it from the provider's page.
The README section *Example dataset* shows how to use these files.

| File | What it is | `filter` on the dataset as published | `filter` on the layered copy (`--add-duplicate`) |
|---|---|---|---|
| `blueberries.kml` | Outline of the field: the `footprint` of all capture positions (5.89 ha) | 480 captures | 600 (480 + 120 copies in `old_subset`) |
| `area-of-interest.kml` | An AOI of about 1 ha inside the field | 74 captures | 113 (74 + 39 copies); 74 with `--skip-duplicates` |
| `make_layered_dataset.py` | Makes a copy of a one-folder dataset with a field-like folder tree | | |

The counts are for the dataset with all 480 captures and the layered copy made with
`build … --parts 4 --folder-captures 50 --add-duplicate`.
