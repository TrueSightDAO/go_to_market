"""Tests for naming the gaps -- the diagnostic that was missing.

A month of ``filled=0`` sweeps could say HOW MANY rows were skipped but never
WHAT stayed empty, which is why the real defect went unnamed. ``gap_field_names``
turns a bare counter into a named cause.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import hit_list_enrich_contact as h

HEADER = [
    "Shop Type",
    "Address",
    "City",
    "State",
    "Phone",
    "Website",
    "Latitude",
    "Longitude",
    "Monday Open",
    "Google listing",
]


def _row(**overrides):
    base = {
        "Shop Type": "Cafe",
        "Address": "1 Main St",
        "City": "LA",
        "State": "CA",
        "Phone": "+13105550100",
        "Website": "https://x.test",
        "Latitude": "34.05",
        "Longitude": "-118.24",
        "Monday Open": "09:00",
        "Google listing": "https://maps/x",
    }
    base.update(overrides)
    return [base[k] for k in HEADER]


def test_complete_row_has_no_gaps():
    assert h.gap_field_names(_row(), HEADER) == []
    assert h.has_any_gap(_row(), HEADER) is False


def test_names_only_the_empty_fields():
    row = _row(Phone="", Website="")
    assert h.gap_field_names(row, HEADER) == ["Phone", "Website"]
    assert h.has_any_gap(row, HEADER) is True


def test_names_hours_gap():
    assert h.gap_field_names(_row(**{"Monday Open": ""}), HEADER) == ["Monday Open"]


def test_names_google_listing_gap():
    assert h.gap_field_names(_row(**{"Google listing": ""}), HEADER) == [
        "Google listing"
    ]


def test_missing_column_is_skipped_not_reported():
    """A header lacking a gap column must not be reported as a gap forever."""
    header = ["Shop Type", "Phone"]
    assert h.gap_field_names(["Cafe", "+1310"], header) == []


def test_multiple_gaps_preserve_header_order():
    row = _row(Address="", City="", Phone="")
    assert h.gap_field_names(row, HEADER) == ["Address", "City", "Phone"]
