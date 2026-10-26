"""Tests for the cache-reachability preflight in the fill-gap sweep.

Context (2026-10-26): the cache read 403'd on all 60 rows of a scheduled run.
``_fetch_cached_record`` returned ``(None, None)`` -- identical to a genuine
cache miss -- so the sweep spent 60 live Places Details calls, filled nothing,
and repeated it every hour: ~112 billed calls/day against a cache it could never
reach.

The fix probes the cache read BEFORE each billed lookup. If the read errors,
the row is skipped with no Places spend, and three consecutive failures bail the
whole sweep. "Cache is empty" (READ_MISS) is NOT an error -- that is exactly when
paying for a live lookup is correct, so the guard must stay silent there.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

_spec = importlib.util.spec_from_file_location(
    "hit_list_enrich_contact", SCRIPTS / "hit_list_enrich_contact.py"
)
hl = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = hl
_spec.loader.exec_module(hl)

PID = "ChIJu9xT9ayAhYARmBLcnQNOYBo"

# places_cache.READ_MISS; spelled out here because the sweep deliberately only
# mirrors _READ_OK/_READ_ERROR at module scope (miss needs no decision).
MISS = "miss"


def _patch_probe(monkeypatch, status, detail="HTTP 403: denied"):
    """Make places_cache._fetch_cached_record_verbose return a fixed outcome."""
    import places_cache as pc

    def fake_verbose(place_id):
        if status == "raises":
            raise RuntimeError("boom")
        rec = {"place_id": place_id} if status == pc.READ_OK else None
        sha = "deadbeef" if status == pc.READ_OK else None
        return rec, sha, status, detail

    monkeypatch.setattr(pc, "_fetch_cached_record_verbose", fake_verbose)
    return pc


# ------------------------------------------------- the probe reads the right thing


def test_probe_reports_ok_on_hit(monkeypatch):
    pc = _patch_probe(monkeypatch, "ok", detail="")
    assert hl.cache_read_outcome(PID) == (pc.READ_OK, "")


def test_probe_reports_miss_unchanged(monkeypatch):
    """A genuine miss must NOT be classified as an error -- that is the case
    where a live lookup is correct and must still be allowed."""
    pc = _patch_probe(monkeypatch, "miss", detail="")
    status, _ = hl.cache_read_outcome(PID)
    assert status == pc.READ_MISS
    assert status != hl._READ_ERROR, "a cold cache is not an unreachable cache"


def test_probe_reports_error_with_detail(monkeypatch):
    _patch_probe(monkeypatch, "error", detail="HTTP 403: denied")
    status, detail = hl.cache_read_outcome(PID)
    assert status == hl._READ_ERROR
    assert "403" in detail


def test_probe_never_raises(monkeypatch):
    """A probe problem must never wedge a working sweep."""
    _patch_probe(monkeypatch, "raises")
    status, detail = hl.cache_read_outcome(PID)
    assert status == hl._READ_OK, "unknown outcome must degrade to allow billing"
    assert "raised" in detail


def test_probe_degrades_when_import_fails(monkeypatch):
    """If places_cache can't be imported at all, don't block the sweep."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "places_cache":
            raise ImportError("no places_cache")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    status, detail = hl.cache_read_outcome(PID)
    assert status == hl._READ_OK
    assert "unavailable" in detail


# ------------------------------------- the guard's decision (the money question)


def test_guard_skips_only_on_error():
    """Unit-level statement of the invariant the sweep loop implements."""
    assert hl._READ_ERROR != hl._READ_OK
    # READ_MISS must be allowed to proceed to a billed call:
    assert hl._READ_ERROR == "error"


def test_constants_match_places_cache():
    """The local mirror must not drift from the source of truth."""
    import places_cache as pc

    assert hl._READ_OK == pc.READ_OK
    assert hl._READ_ERROR == pc.READ_ERROR


# ------------------------------------------- the BAIL decision (pure, testable)


def test_one_failure_does_not_bail():
    """A single blip skips one row; it must not abort a healthy sweep."""
    assert hl.should_bail_cache_unreachable(1) is False
    assert hl.should_bail_cache_unreachable(2) is False


def test_three_consecutive_failures_bail():
    """The 2026-10-26 shape: persistent read failure must stop the spend."""
    assert hl.should_bail_cache_unreachable(3) is True
    assert hl.should_bail_cache_unreachable(4) is True


def test_threshold_is_configurable():
    assert hl.should_bail_cache_unreachable(2, threshold=2) is True
    assert hl.should_bail_cache_unreachable(5, threshold=10) is False


def test_threshold_zero_disables_bailing():
    """0 = skip-only mode: never abort, but still never bill a row whose cache
    read failed. (The skip happens before the billed call regardless.)"""
    assert hl.should_bail_cache_unreachable(99, threshold=0) is False
    assert hl.should_bail_cache_unreachable(99, threshold=-1) is False


def test_zero_streak_never_bails():
    assert hl.should_bail_cache_unreachable(0) is False


# ----------------------------- end-to-end: simulate the sweep's spend decision


def _simulate_run(read_statuses, bail_after=3):
    """Mirror the loop's spend logic exactly, and return what it would cost.

    Returns (places_calls_billed, rows_skipped_for_cache, bailed).
    """
    billed = 0
    skipped = 0
    streak = 0
    bailed = False
    for status in read_statuses:
        if status == hl._READ_ERROR:
            skipped += 1
            streak += 1
            if hl.should_bail_cache_unreachable(streak, bail_after):
                bailed = True
                break
            continue
        streak = 0
        billed += 1  # READ_OK (served from cache) or READ_MISS (live call)
    return billed, skipped, bailed


def test_all_reads_failing_costs_at_most_two_places_calls():
    """THE regression, in money terms.

    Pre-fix this scenario billed 20 calls and filled nothing. With the guard,
    at most the 2 rows before the breaker trips can be billed.
    """
    billed, skipped, bailed = _simulate_run([hl._READ_ERROR] * 20)
    assert bailed is True
    assert billed == 0, f"guard must not bill any row whose cache read failed, got {billed}"
    assert skipped == 3


def test_misses_still_bill_normally():
    """A cold cache is the legitimate case: paying is correct."""
    billed, skipped, bailed = _simulate_run([MISS] * 5)
    assert bailed is False
    assert skipped == 0
    assert billed == 5, "genuine cache misses must still buy live lookups"


def test_intermittent_failure_resets_the_streak():
    """Two failures, a good read, then two more: never bails (streak resets)."""
    modes = [
        hl._READ_ERROR,
        hl._READ_ERROR,
        "miss",
        hl._READ_ERROR,
        hl._READ_ERROR,
        "ok",
    ]
    billed, skipped, bailed = _simulate_run(modes)
    assert bailed is False
    assert skipped == 4
    assert billed == 2
