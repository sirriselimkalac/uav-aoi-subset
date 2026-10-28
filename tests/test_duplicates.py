from dataclasses import replace

from uav_aoi_subset.core.duplicates import can_detect, drop_duplicates, find_duplicates
from uav_aoi_subset.core.index import IndexRecord

TIME = "2026:07:30 09:00:00"


def rec(folder: str, base: str = "IMG_0001", time: str | None = TIME, lat=50.0, lon=10.0):
    return IndexRecord(
        record_name=f"{folder.replace('/', '_')}_{base}",
        complete=True,
        latitude=lat,
        longitude=lon,
        altitude=100.0,
        capture_time=time,
        bands_found=(1, 2, 3, 4, 5, 6, 7),
        missing_bands=(),
        relative_folder=folder,
        image_base=base,
    )


def test_same_image_time_and_position_in_two_folders():
    original = rec("Part1/0000SET/000")
    copy = rec("old_subset/Part1_0000SET_000")
    other = rec("Part1/0000SET/000", base="IMG_0002", lat=50.1)
    groups = find_duplicates([copy, other, original])
    assert groups == [[copy, original]]  # case-insensitive folder order: "old_subset" first


def test_differences_are_not_duplicates():
    a = rec("Part1/0000SET/000")
    # Numbering restarts in every SET: same base, other time and place.
    restart = rec("Part1/0001SET/000", time="2026:07:30 10:00:00", lat=50.2)
    same_place_other_time = rec("Part2/0000SET/000", time="2026:07:31 09:00:00")
    other_base = rec("Part3", base="IMG_0009")
    assert find_duplicates([a, restart, same_place_other_time, other_base]) == []


def test_base_compared_case_insensitively():
    assert len(find_duplicates([rec("a"), rec("b", base="img_0001")])) == 1


def test_records_without_time_or_position_are_never_duplicates():
    no_time = [rec("a", time=None), rec("b", time=None)]
    no_gps = [rec("a", lat=None, lon=None), rec("b", lat=None, lon=None)]
    assert find_duplicates(no_time + no_gps) == []
    assert not can_detect(no_time + no_gps)
    assert can_detect([*no_time, rec("c")])


def test_matlab_rows_cannot_be_compared():
    matlab = replace(rec("a"), relative_folder="", image_base="", capture_time=None)
    assert not can_detect([matlab, matlab])
    assert find_duplicates([matlab, matlab]) == []


def test_drop_keeps_the_first_folder_and_the_original_order():
    first = rec("A/000")
    later = rec("B/000")
    third = rec("C/000")
    other = rec("A/000", base="IMG_0002", lat=51.0)
    kept, dropped = drop_duplicates([third, other, first, later])
    assert kept == [other, first]
    assert dropped == [(third, first), (later, first)]


def test_drop_without_duplicates_changes_nothing():
    records = [rec("A"), rec("A", base="IMG_0002", lat=51.0)]
    assert drop_duplicates(records) == (records, [])
