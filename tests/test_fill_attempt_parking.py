"""The fill-gap sweep must stop re-selecting rows it can never fill.

Observed 2026-10-26 (run 40332489037): ``filled=0 skipped=11
no_fill_streak=10``, and every sampled row's last blocker was ``Google
listing``. Two defects combined:

1. ``Google listing`` is an EXCEPTION FLAG -- ``google_listing_from_business_status``
   returns a value only for a CLOSED business, so for an operating retailer the
   correct value is empty. Counting it as a gap made every open retailer
   permanently unfillable.
2. The sweep had no memory of failure: it selected on sheet state alone and
   wrote nothing on a failed fill, so the same rows came back every hour until
   the no-fill streak bailed the sweep -- starving rows that DID have real gaps.

These tests pin the contract that fixes both.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import hit_list_enrich_contact as h

HEADER = [
    "Shop Type",
    "Status",
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
    """A healthy, OPERATING retailer: every fillable field present, Google
    listing empty because the business is not closed."""
    base = {
        "Shop Type": "Cafe",
        "Status": "Research",
        "Address": "1 Main St",
        "City": "LA",
        "State": "CA",
        "Phone": "+13105550100",
        "Website": "https://x.test",
        "Latitude": "34.05",
        "Longitude": "-118.24",
        "Monday Open": "09:00",
        "Google listing": "",
    }
    base.update(overrides)
    return [base[k] for k in HEADER]


def test_open_business_is_not_sweep_selectable():
    """The regression this PR exists for.

    An operating retailer has an empty ``Google listing`` by definition. It must
    NOT be selected by the sweep -- otherwise it fills nothing forever, and its
    no-fill streak bails the sweep before reaching real work.
    """
    row = _row()
    assert h.has_any_fillable_gap(row, HEADER) is False
    # Reporting semantics stay unchanged, so the log can still name the flag.
    assert h.has_any_gap(row, HEADER) is True
    assert h.gap_field_names(row, HEADER) == ["Google listing"]


def test_closed_business_value_clears_any_gap():
    row = _row(**{"Google listing": "Closed"})
    assert h.has_any_fillable_gap(row, HEADER) is False
    assert h.has_any_gap(row, HEADER) is False


def test_real_gap_is_still_sweep_selectable():
    """The fix must not stop the sweep doing its actual job."""
    assert h.has_any_fillable_gap(_row(Website=""), HEADER) is True
    assert h.has_any_fillable_gap(_row(**{"Monday Open": ""}), HEADER) is True
    assert h.has_any_fillable_gap(_row(Phone=""), HEADER) is True


def test_missing_column_is_not_a_fillable_gap():
    """A header without the gap columns must not look permanently gappy."""
    assert h.has_any_fillable_gap(["Cafe"], ["Shop Type"]) is False


def test_attempts_default_zero_when_marker_absent():
    assert h.fill_attempts_from_notes("") == 0
    assert h.fill_attempts_from_notes(None) == 0
    assert h.fill_attempts_from_notes("ChIJabc123 no marker here") == 0


def test_attempts_round_trip():
    notes = "ChIJabc123"
    for n in (1, 2, 3):
        notes = h.bump_fill_attempts_in_notes(notes, n)
        assert h.fill_attempts_from_notes(notes) == n


def test_bump_rewrites_rather_than_appends():
    """Hourly runs must not grow an unbounded pile of markers."""
    notes = "ChIJabc123"
    for n in (1, 2, 3, 4):
        notes = h.bump_fill_attempts_in_notes(notes, n)
    assert notes.count("[fill-attempts=") == 1
    assert h.fill_attempts_from_notes(notes) == 4
    assert notes.startswith("ChIJabc123")


def test_attempts_preserve_existing_notes_content():
    notes = "ChIJabc123 [enrich-contact 2026-10-26] outcome=manual"
    out = h.bump_fill_attempts_in_notes(notes, 2)
    assert "ChIJabc123" in out
    assert "outcome=manual" in out
    assert h.fill_attempts_from_notes(out) == 2


def test_attempt_limit_is_a_positive_budget_or_disabled():
    """0 must mean 'disabled', not 'park immediately'."""
    assert h.FILL_ATTEMPT_LIMIT >= 0


def test_parked_status_name_is_the_governor_chosen_one():
    assert h.STATUS_FILL_MANUAL == "AI: Fill \u2014 manual"
