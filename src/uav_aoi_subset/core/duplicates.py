"""Find captures that exist more than once under ROOT.

A copy of a capture has the same image base, capture time and position as the original but
lies in another folder: an old subset folder, a backup or a second download kept inside the
project. Copies are byte-identical, so the values are compared exactly. Records without a
capture time or position (for example from MATLAB CSVs) cannot be compared and are never
reported as copies.
"""

from __future__ import annotations

from collections.abc import Iterable

from uav_aoi_subset.core.index import IndexRecord


def can_detect(records: Iterable[IndexRecord]) -> bool:
    """True if at least one record has the fields needed to recognise copies."""
    return any(_key(r) is not None for r in records)


def _key(record: IndexRecord) -> tuple[str, str, float, float] | None:
    if not (record.image_base and record.capture_time and record.has_position):
        return None
    return record.image_base.upper(), record.capture_time, record.latitude, record.longitude


def find_duplicates(records: Iterable[IndexRecord]) -> list[list[IndexRecord]]:
    """Groups of two or more records that are the same capture in different folders.

    Each group is sorted by relative folder (case-insensitive), so its first record is the
    one :func:`drop_duplicates` keeps. Groups are sorted by their first record.
    """
    groups: dict[tuple[str, str, float, float], list[IndexRecord]] = {}
    for record in records:
        key = _key(record)
        if key is not None:
            groups.setdefault(key, []).append(record)
    found = [sorted(g, key=_folder_order) for g in groups.values() if len(g) > 1]
    return sorted(found, key=lambda g: _folder_order(g[0]))


def _folder_order(record: IndexRecord) -> tuple[str, str, str]:
    return record.relative_folder.casefold(), record.relative_folder, record.record_name


def drop_duplicates(
    records: Iterable[IndexRecord],
) -> tuple[list[IndexRecord], list[tuple[IndexRecord, IndexRecord]]]:
    """Keep the first record of every duplicate group, in the original order.

    Returns the kept records and ``(dropped, kept instead)`` pairs.
    """
    records = list(records)
    kept_for: dict[int, IndexRecord] = {}
    position = {id(r): i for i, r in enumerate(records)}
    for group in find_duplicates(records):
        for record in group[1:]:
            kept_for[position[id(record)]] = group[0]
    kept = [r for i, r in enumerate(records) if i not in kept_for]
    dropped = [(records[i], kept_for[i]) for i in sorted(kept_for)]
    return kept, dropped
