"""Tests for billed-vs-free Places accounting.

Context: the 2026-10-26 sweep billed ~112 calls/day and persisted nothing, and
the workflow log could not distinguish a cache HIT (free) from a cache MISS
followed by a live call (billed) -- both were silent. These counters exist so a
run's summary line states the spend outright. The invariant that matters is
that the counters are *honest*: a free hit must never be counted as billed, and
a short-circuited (circuit-broken) call must never be counted at all.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import places_cache as pc


@pytest.fixture(autouse=True)
def _reset():
    pc.reset_call_counters()
    yield
    pc.reset_call_counters()


def _cached_ok(fields):
    return {
        "place_id": "P1",
        "google_status": "OK",
        "fields_requested": list(fields),
        "result": {"name": "Cafe", "place_id": "P1"},
    }


class _FakeResp:
    """Minimal stand-in for a Places Details HTTP response."""

    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


def _live_ok(monkeypatch, result=None):
    """Make the REAL _live_place_details run, so its billed-counter increments."""
    payload = {"status": "OK", "result": result or {"name": "Cafe", "place_id": "P1"}}
    monkeypatch.setattr(pc.requests, "get", lambda *a, **k: _FakeResp(payload))


def test_positive_cache_hit_is_free(monkeypatch):
    monkeypatch.setattr(
        pc, "_fetch_cached_record", lambda pid: (_cached_ok(pc.FULL_FIELDS), "sha1")
    )

    def _boom(*a, **k):
        raise AssertionError("live call must NOT happen on a full cache hit")

    monkeypatch.setattr(pc, "_live_place_details", _boom)

    out = pc.cached_place_details_full("k", "P1")
    assert out["name"] == "Cafe"
    c = pc.get_call_counters()
    assert c["cache_hits"] == 1
    assert c["places_billed"] == 0


def test_partial_cache_hit_is_billed(monkeypatch):
    # Cached record covers only one field -> a live call is genuinely required.
    monkeypatch.setattr(
        pc, "_fetch_cached_record", lambda pid: (_cached_ok(["name"]), "sha1")
    )
    _live_ok(monkeypatch)
    monkeypatch.setattr(pc, "_write_cached_record", lambda *a, **k: True)

    pc.cached_place_details_full("k", "P1")
    c = pc.get_call_counters()
    assert c["places_billed"] == 1
    assert c["cache_hits"] == 0


def test_cache_miss_with_no_write_still_counts_billed(monkeypatch):
    """The 2026-10-26 shape: billed, but persisting failed. Must still be counted."""
    monkeypatch.setattr(pc, "_fetch_cached_record", lambda pid: (None, None))
    _live_ok(monkeypatch)
    # Write-back fails -- the exact condition that silently re-billed every hour.
    monkeypatch.setattr(pc, "_write_cached_record", lambda *a, **k: False)

    pc.cached_place_details_full("k", "P1")
    assert pc.get_call_counters()["places_billed"] == 1


def test_negative_cache_hit_is_free(monkeypatch):
    rec = {"place_id": "P1", "google_status": "NOT_FOUND", "result": None}
    monkeypatch.setattr(pc, "_fetch_cached_record", lambda pid: (rec, "sha1"))
    monkeypatch.setattr(
        pc,
        "_live_place_details",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be billed")),
    )

    assert pc.cached_place_details_full("k", "P1") == {}
    c = pc.get_call_counters()
    assert c["cache_negative_hits"] == 1
    assert c["places_billed"] == 0


def test_circuit_broken_call_is_not_billed(monkeypatch):
    """A rate-limit short-circuit never reaches Google, so it must not count."""
    monkeypatch.setattr(pc, "_fetch_cached_record", lambda pid: (None, None))
    monkeypatch.setattr(pc, "_RATE_LIMITED", True)

    pc.cached_place_details_full("k", "P1")
    assert pc.get_call_counters()["places_billed"] == 0


def test_counters_accumulate_across_calls(monkeypatch):
    monkeypatch.setattr(pc, "_fetch_cached_record", lambda pid: (None, None))
    _live_ok(monkeypatch)
    monkeypatch.setattr(pc, "_write_cached_record", lambda *a, **k: True)

    for _ in range(3):
        pc.cached_place_details_full("k", "P1")
    assert pc.get_call_counters()["places_billed"] == 3

    pc.reset_call_counters()
    assert pc.get_call_counters()["places_billed"] == 0


def test_reset_zeroes_every_counter(monkeypatch):
    monkeypatch.setattr(pc, "_fetch_cached_record", lambda pid: (None, None))
    _live_ok(monkeypatch)
    monkeypatch.setattr(pc, "_write_cached_record", lambda *a, **k: True)
    pc.cached_place_details_full("k", "P1")
    pc.reset_call_counters()
    assert pc.get_call_counters() == {
        "places_billed": 0,
        "cache_hits": 0,
        "cache_negative_hits": 0,
    }
