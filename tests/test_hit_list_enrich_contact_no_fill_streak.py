"""Tests for the fill-gap sweep's consecutive-no-fill breaker.

Context (2026-10, gate-a-quota investigation): ``hit_list_enrich_contact.py``
charges one Places Details call per gappy row at ``place_details_full()``
*before* it can know whether the result fills anything. The only bail condition
was ``is_rate_limited()``, so when the places-cache write-back silently fails
(401/403 -> ``_write_cached_record`` returns False, no raise) every scheduled run
re-paid for the same rows forever. Observed in run 40254784478:

    Fill-gap sweep: cap=20 (attempt-cap=60)
    Fill-gap sweep done. filled=0 skipped=61

60 billed calls, 0 fills, ~112/day. These tests pin the breaker that stops it.

Run: python3 -m pytest tests/test_hit_list_enrich_contact_no_fill_streak.py -q
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

SCRIPT = SCRIPTS / "hit_list_enrich_contact.py"
_spec = importlib.util.spec_from_file_location("hit_list_enrich_contact", SCRIPT)
m = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = m
_spec.loader.exec_module(m)

should_bail_no_fill = m.should_bail_no_fill


def _simulate_lookups(outcomes, max_streak, attempt_cap):
    """Mirror the sweep loop's counter/bail semantics.

    Returns (lookups_charged, filled, bailed_on_streak). ``outcomes`` is one bool
    per row: True = the row got a writable update, False = lookup produced nothing.
    """
    fill_done = 0
    streak = 0
    charged = 0
    bailed = False
    for i, updated in enumerate(outcomes, start=1):
        if should_bail_no_fill(streak, max_streak):
            bailed = True
            break
        if i > attempt_cap:
            break
        charged = i  # the Places call happens here, unconditionally
        if updated:
            fill_done += 1
            streak = 0
        else:
            streak += 1
    return charged, fill_done, bailed


def test_breaker_triggers_exactly_at_threshold():
    assert should_bail_no_fill(0, 10) is False
    assert should_bail_no_fill(9, 10) is False
    assert should_bail_no_fill(10, 10) is True
    assert should_bail_no_fill(11, 10) is True


def test_breaker_is_disabled_for_non_positive_caps():
    # 0 / negative must NOT be read as "already at the cap" -- that would bail
    # before a single row and silently disable the sweep.
    assert should_bail_no_fill(0, 0) is False
    assert should_bail_no_fill(1000, 0) is False
    assert should_bail_no_fill(1000, -5) is False


def test_all_empty_lookups_stop_at_ten_instead_of_burning_sixty():
    """The exact runaway from run 40254784478: 60 charged, 0 filled."""
    charged, filled, bailed = _simulate_lookups(
        [False] * 60, max_streak=10, attempt_cap=60
    )
    assert bailed is True
    assert charged == 10, f"expected 10 billed calls, got {charged}"
    assert filled == 0


def test_breaker_disabled_reproduces_old_runaway():
    """Regression guard: with the breaker off the old 60-call behaviour is intact."""
    charged, filled, bailed = _simulate_lookups(
        [False] * 60, max_streak=0, attempt_cap=60
    )
    assert bailed is False
    assert charged == 60
    assert filled == 0


def test_streak_resets_after_a_success():
    """A success must not be punished by earlier misses: 9 misses, 1 hit, 9 misses,
    then it bails on the 10th of the second run -- 20 charges, 1 fill."""
    outcomes = [False] * 9 + [True] + [False] * 30
    charged, filled, bailed = _simulate_lookups(outcomes, max_streak=10, attempt_cap=60)
    assert bailed is True
    assert filled == 1
    assert charged == 20


def test_productive_sweep_never_trips_breaker():
    """A healthy run fills every row and is unaffected."""
    charged, filled, bailed = _simulate_lookups(
        [True] * 20, max_streak=10, attempt_cap=60
    )
    assert bailed is False
    assert filled == 20
    assert charged == 20


def test_flag_and_helper_are_wired_into_the_script():
    """Cheap smoke guard against the flag/helper being dropped in a later refactor."""
    src = inspect.getsource(m.main)
    assert "--max-no-fill-streak" in src
    assert "should_bail_no_fill" in src
    assert "no_fill_streak" in src
