"""Tests for sha resolution in the places-cache writers.

Context (2026-10-26, quota-exhaustion investigation): the hourly
``hit_list_enrich_contact`` sweep billed ~60-112 Places Details calls/day and
persisted nothing. The write half of that loop was:

    places_cache: write rejected for ChIJ... (422): {"message":"Invalid
    request.\\n\\n\\"sha\\" wasn't supplied."}

Reproduced locally on demand: the Contents API REQUIRES ``sha`` to update an
existing file, but both writers treated it as optional (``if prior_sha:``).
Whenever the sha didn't arrive from the read path -- including every case where
the read itself failed, since that returns ``(None, None)`` -- the PUT went out
sha-less, GitHub rejected it, and a result that had **already been paid for** was
thrown away. The next run then re-paid for the same rows, forever.

Crucially, 422 is a *validation* error: it arrives only after the token was
accepted, so this bug fires even with a perfectly healthy PAT. It is not an auth
problem and must not be conflated with one.

The fix: both writers now resolve the sha themselves via
``_resolve_prior_sha`` / ``_cache_file_sha`` instead of trusting the caller.

Run: python3 -m pytest tests/test_places_cache_write_sha.py -q
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
    "places_cache", SCRIPTS / "places_cache.py"
)
m = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = m
_spec.loader.exec_module(m)

PID = "ChIJu9xT9ayAhYARmBLcnQNOYBo"
RECORD = {"place_id": PID, "name": "Test Cafe"}
SHA = "f49cdad9a64c0e5a"


class FakeResp:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload


class FakeGet:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls: list[str] = []

    def __call__(self, url, headers=None, timeout=None):
        self.urls.append(url)
        if not self.responses:
            raise AssertionError("unexpected extra GET")
        return self.responses.pop(0)


class FakePut:
    def __init__(self, responses):
        self.responses = list(responses)
        self.bodies: list[dict] = []

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.bodies.append(dict(json or {}))
        if not self.responses:
            raise AssertionError("unexpected extra PUT")
        return self.responses.pop(0)


def _install(monkeypatch, gets, puts, token="tok"):
    fg = FakeGet(gets)
    fp = FakePut(puts)
    monkeypatch.setattr(m.requests, "get", fg)
    monkeypatch.setattr(m.requests, "put", fp)
    monkeypatch.setattr(m, "_write_token", lambda: token)
    return fg, fp


# --------------------------------------------------------------- _cache_file_sha


def test_cache_file_sha_returns_sha_on_200(monkeypatch):
    _install(monkeypatch, [FakeResp(200, {"sha": SHA})], [])
    assert m._cache_file_sha(m._cache_path(PID), "tok") == SHA


def test_cache_file_sha_returns_none_on_404(monkeypatch):
    """A genuine absence must be indistinguishable from a create-worthy path."""
    _install(monkeypatch, [FakeResp(404)], [])
    assert m._cache_file_sha(m._cache_path(PID), "tok") is None


def test_cache_file_sha_returns_none_on_403(monkeypatch):
    _install(monkeypatch, [FakeResp(403, text="denied")], [])
    assert m._cache_file_sha(m._cache_path(PID), "tok") is None


def test_cache_file_sha_survives_transport_error(monkeypatch):
    def boom(*a, **k):
        raise m.requests.RequestException("network down")

    monkeypatch.setattr(m.requests, "get", boom)
    assert m._cache_file_sha(m._cache_path(PID), "tok") is None


# ------------------------------------------------------------- _resolve_prior_sha


def test_resolve_short_circuits_when_sha_supplied(monkeypatch):
    """A known sha must cost zero extra requests."""
    fg, _ = _install(monkeypatch, [], [])
    assert m._resolve_prior_sha("places/Ch/x.json", SHA, "tok") == SHA
    assert fg.urls == [], "must not hit the network when sha is already known"


def test_resolve_fetches_when_sha_missing(monkeypatch):
    fg, _ = _install(monkeypatch, [FakeResp(200, {"sha": SHA})], [])
    assert m._resolve_prior_sha("places/Ch/x.json", None, "tok") == SHA
    assert len(fg.urls) == 1


# ------------------------------------- THE REGRESSION: the production 422 bug


def test_write_resolves_sha_and_persists_when_caller_passes_none(monkeypatch, capsys):
    """THE production bug.

    Caller passes prior_sha=None on an EXISTING file (exactly what happened when
    the read path returned ``(None, None)``). Pre-fix this PUT carried no ``sha``
    and got 422. Post-fix the writer resolves the sha and the write succeeds.
    """
    _, fp = _install(
        monkeypatch,
        [FakeResp(200, {"sha": SHA})],
        [FakeResp(200, {"commit": {}})],
    )

    assert m._write_cached_record(PID, RECORD, None) is True
    assert fp.bodies[0]["sha"] == SHA, "PUT must carry the resolved sha"
    assert "write rejected" not in capsys.readouterr().err


def test_write_still_creates_when_file_truly_absent(monkeypatch):
    """The create path must be untouched: no sha in the body, 201 is success."""
    _, fp = _install(monkeypatch, [FakeResp(404)], [FakeResp(201, {})])

    assert m._write_cached_record(PID, RECORD, None) is True
    assert "sha" not in fp.bodies[0], "a create must NOT send a sha"


def test_write_uses_caller_sha_without_extra_get(monkeypatch):
    fg, fp = _install(monkeypatch, [], [FakeResp(200, {})])
    assert m._write_cached_record(PID, RECORD, SHA) is True
    assert fp.bodies[0]["sha"] == SHA
    assert fg.urls == []


def test_unresolvable_sha_fails_loudly(monkeypatch, capsys):
    """If the sha cannot be resolved, do not silently discard a billed result."""
    _install(
        monkeypatch,
        [FakeResp(403, text="denied")],
        [
            FakeResp(
                422,
                text='{"message":"Invalid request.\\n\\n\\"sha\\" wasn\'t supplied."}',
            )
        ],
    )

    assert m._write_cached_record(PID, RECORD, None) is False
    err = capsys.readouterr().err
    assert "422" in err
    assert "NOT persisted" in err, "must say the result was discarded"
    assert "already been billed" in err, "must name the cost implication"


def test_409_retry_uses_freshly_resolved_sha(monkeypatch):
    """Conflict path must retry with the CURRENT sha, not the stale one."""
    _, fp = _install(
        monkeypatch,
        [FakeResp(200, {"sha": "newsha999"})],
        [FakeResp(409, text="conflict"), FakeResp(200, {})],
    )

    assert m._write_cached_record(PID, RECORD, "stalesha111") is True
    assert fp.bodies[0]["sha"] == "stalesha111"
    assert fp.bodies[1]["sha"] == "newsha999", "retry must use the fresh sha"


def test_no_token_skips_write_entirely(monkeypatch):
    fg, fp = _install(monkeypatch, [], [], token=None)
    assert m._write_cached_record(PID, RECORD, None) is False
    assert fg.urls == [] and fp.bodies == []


# ------------------------------------------- coverage writer has the same bug


def test_coverage_write_resolves_sha_when_caller_passes_none(monkeypatch):
    """``_write_coverage_record`` had the identical sha-optional bug."""
    combo = m._coverage_path("cafe", 1.0, 2.0, 500)
    _, fp = _install(
        monkeypatch,
        [FakeResp(200, {"sha": SHA})],
        [FakeResp(200, {})],
    )

    assert m._write_coverage_record(combo, {"results": []}, None) is True
    assert fp.bodies[0]["sha"] == SHA


def test_coverage_write_creates_without_sha(monkeypatch):
    combo = m._coverage_path("cafe", 1.0, 2.0, 500)
    _, fp = _install(monkeypatch, [FakeResp(404)], [FakeResp(201, {})])

    assert m._write_coverage_record(combo, {"results": []}, None) is True
    assert "sha" not in fp.bodies[0]
