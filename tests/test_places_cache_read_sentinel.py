"""Tests for the cache-read outcome sentinel.

Context (2026-10-26 quota exhaustion): 60/60 authenticated cache reads returned
403 and ``_fetch_cached_record`` collapsed that into ``(None, None)`` -- the same
value it returns for a genuine cache miss. Every row therefore looked uncached,
the hourly sweep billed a live Places Details call for each one (~112/day), and
nothing was persisted. The failure was silent: the sweep tallied reads that had
failed as "skipped".

The fix keeps ``_fetch_cached_record``'s 2-tuple contract but adds
``_fetch_cached_record_verbose``, which distinguishes:

    READ_MISS  - 404, genuinely not cached; paying for a live lookup is correct
    READ_ERROR - auth / transport / parse / unexpected status; NOT a miss

and logs the upstream response BODY on an auth failure, because a bare "403" is
ambiguous between a scope problem, an SSO problem and a secondary rate limit.

Run: python3 -m pytest tests/test_places_cache_read_sentinel.py -q
"""

from __future__ import annotations

import base64
import importlib.util
import json
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


def _encoded(rec):
    return base64.b64encode(json.dumps(rec).encode()).decode()


def _ok_payload(rec=RECORD, sha=SHA):
    return {"sha": sha, "content": _encoded(rec)}


def _install(monkeypatch, responses, token="tok"):
    seq = list(responses)
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(headers or {})
        if not seq:
            raise AssertionError("unexpected extra GET")
        r = seq.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(m.requests, "get", fake_get)
    monkeypatch.setattr(m, "_write_token", lambda: token)
    return calls


# ------------------------------------------------------------ the three states


def test_200_decodes_record_and_reports_ok(monkeypatch):
    _install(monkeypatch, [FakeResp(200, _ok_payload())])
    rec, sha, status, detail = m._fetch_cached_record_verbose(PID)
    assert rec == RECORD
    assert sha == SHA
    assert status == m.READ_OK
    assert detail == ""


def test_404_is_a_miss_not_an_error(monkeypatch):
    """A real absence must stay a miss: paying for a live lookup is correct."""
    _install(monkeypatch, [FakeResp(404)])
    rec, sha, status, _ = m._fetch_cached_record_verbose(PID)
    assert (rec, sha) == (None, None)
    assert status == m.READ_MISS


def test_exhausted_403_is_an_error_not_a_miss(monkeypatch):
    """THE regression.

    Both the authenticated and the anonymous retry 403. Pre-fix this was
    indistinguishable from 404, so every row was re-billed forever. It must now
    report READ_ERROR.
    """
    _install(monkeypatch, [FakeResp(403, text="denied"), FakeResp(403, text="denied")])
    rec, sha, status, detail = m._fetch_cached_record_verbose(PID)
    assert (rec, sha) == (None, None)
    assert status == m.READ_ERROR
    assert status != m.READ_MISS, "a permission failure must never look like a miss"
    assert "403" in detail


def test_500_is_an_error(monkeypatch):
    _install(monkeypatch, [FakeResp(500, text="boom")])
    _, _, status, detail = m._fetch_cached_record_verbose(PID)
    assert status == m.READ_ERROR
    assert "500" in detail


def test_transport_error_is_an_error(monkeypatch):
    """A transport failure retries anonymously, then reports READ_ERROR."""
    _install(
        monkeypatch,
        [
            m.requests.RequestException("network down"),
            m.requests.RequestException("still down"),
        ],
    )
    _, _, status, detail = m._fetch_cached_record_verbose(PID)
    assert status == m.READ_ERROR
    assert "transport" in detail


def test_undecodable_record_is_an_error_not_a_miss(monkeypatch):
    _install(monkeypatch, [FakeResp(200, {"sha": SHA, "content": "!!!not-base64!!!"})])
    _, _, status, detail = m._fetch_cached_record_verbose(PID)
    assert status == m.READ_ERROR
    assert "undecodable" in detail


def test_200_with_empty_content_is_an_error(monkeypatch):
    _install(monkeypatch, [FakeResp(200, {"sha": SHA, "content": ""})])
    _, _, status, detail = m._fetch_cached_record_verbose(PID)
    assert status == m.READ_ERROR
    assert "empty content" in detail


# --------------------------------------------- the body must reach the log


def test_auth_failure_logs_the_response_body(monkeypatch, capsys):
    """A bare '403' can't be diagnosed; the BODY is the whole story.

    It was previously truncated to '***' in the logs, which is why this went
    unexplained for months.
    """
    body = '{"message":"Resource not accessible by personal access token"}'
    _install(
        monkeypatch,
        [FakeResp(403, text=body), FakeResp(403, text=body)],
    )
    m._fetch_cached_record_verbose(PID)
    err = capsys.readouterr().err
    assert "403" in err
    assert "Resource not accessible" in err, "the 403 body must be logged"
    assert "retrying anonymously" in err


def test_anonymous_retry_recovers_the_record(monkeypatch):
    _install(monkeypatch, [FakeResp(403, text="denied"), FakeResp(200, _ok_payload())])
    rec, sha, status, _ = m._fetch_cached_record_verbose(PID)
    assert status == m.READ_OK
    assert rec == RECORD
    assert sha == SHA


def test_no_token_makes_exactly_one_request(monkeypatch):
    calls = _install(monkeypatch, [FakeResp(404)], token=None)
    m._fetch_cached_record_verbose(PID)
    assert len(calls) == 1, "no token -> no retry"


# ------------------------------------------- backwards-compatible 2-tuple


def test_wrapper_still_returns_2_tuple_on_hit(monkeypatch):
    _install(monkeypatch, [FakeResp(200, _ok_payload())])
    out = m._fetch_cached_record(PID)
    assert out == (RECORD, SHA)
    assert len(out) == 2


def test_wrapper_still_returns_none_none_on_miss(monkeypatch):
    _install(monkeypatch, [FakeResp(404)])
    assert m._fetch_cached_record(PID) == (None, None)


def test_wrapper_still_returns_none_none_on_error(monkeypatch):
    _install(monkeypatch, [FakeResp(500, text="boom")])
    assert m._fetch_cached_record(PID) == (None, None)
