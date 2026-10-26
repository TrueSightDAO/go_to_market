"""Tests for the anonymous-read fallback in places_cache._fetch_cached_record.

Context (2026-10-26, gate-a-quota investigation): the hourly
``hit_list_enrich_contact`` sweep was billed ~112 Places Details calls/day while
filling nothing. Root cause was two independent failures:

1. READ: every authenticated Contents-API read returned **403** (a token that
   authenticates but is denied access to the cache repo), so every row looked
   like a cache miss and fell through to a live Places lookup.
2. WRITE: ``_write_cached_record`` then failed **422 "sha wasn't supplied"**
   (because the 403 read never returned a sha), so the freshly paid-for result
   was never persisted -- guaranteeing the same rows are re-paid every run.

places-cache is a PUBLIC repo, so an anonymous read succeeds regardless of token
health -- and a cache read costs no Places quota. These tests pin the fallback
that breaks the loop. Fix 2 (the 422 write) is tracked separately.

Run: python3 -m pytest tests/test_places_cache_anon_read_fallback.py -q
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

_spec = importlib.util.spec_from_file_location("places_cache", SCRIPTS / "places_cache.py")
m = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = m
_spec.loader.exec_module(m)

PID = "ChIJu9xT9ayAhYARmBLcnQNOYBo"
RECORD = {"place_id": PID, "name": "Test Cafe", "fields_requested": ["name"]}


class FakeResp:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


def _ok_payload(record: dict) -> dict:
    return {
        "sha": "abc123def456",
        "content": base64.b64encode(json.dumps(record).encode()).decode(),
    }


class FakeGet:
    """Records every call; replies from a scripted list of responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, url, headers=None, timeout=None):
        self.calls.append(dict(headers or {}))
        if not self.responses:
            raise AssertionError("unexpected extra GET")
        return self.responses.pop(0)

    @property
    def auth_used(self) -> list[bool]:
        return ["Authorization" in h for h in self.calls]


def _install(monkeypatch, responses, token="tok"):
    fake = FakeGet(responses)
    monkeypatch.setattr(m.requests, "get", fake)
    monkeypatch.setattr(m, "_write_token", lambda: token)
    return fake


def test_403_falls_back_to_anonymous_and_recovers(monkeypatch, capsys):
    """The exact production failure: authenticated read 403 -> anonymous retry."""
    fake = _install(
        monkeypatch,
        [
            FakeResp(403, text='{"message":"Resource not accessible"}'),
            FakeResp(200, _ok_payload(RECORD)),
        ],
    )
    rec, sha = m._fetch_cached_record(PID)

    assert rec == RECORD, "fallback must return the cached record"
    assert sha == "abc123def456", "sha is required for a later write"
    assert fake.auth_used == [True, False], "second attempt must be anonymous"
    assert "retrying anonymously" in capsys.readouterr().err


def test_401_falls_back_to_anonymous_and_recovers(monkeypatch):
    """401 = revoked/expired PAT is the same class of failure as 403."""
    fake = _install(
        monkeypatch,
        [
            FakeResp(401, text='{"message":"Bad credentials"}'),
            FakeResp(200, _ok_payload(RECORD)),
        ],
    )
    rec, sha = m._fetch_cached_record(PID)

    assert rec == RECORD
    assert sha == "abc123def456"
    assert fake.auth_used == [True, False]


def test_404_is_a_real_miss_and_does_not_retry(monkeypatch):
    """A genuine cache miss must stay a miss and cost exactly one request."""
    fake = _install(monkeypatch, [FakeResp(404, text="Not Found")])
    rec, sha = m._fetch_cached_record(PID)

    assert rec is None and sha is None
    assert len(fake.calls) == 1, "404 must not trigger a second request"


def test_200_does_not_retry(monkeypatch):
    """Healthy authenticated reads must be untouched by the fallback."""
    fake = _install(monkeypatch, [FakeResp(200, _ok_payload(RECORD))])
    rec, sha = m._fetch_cached_record(PID)

    assert rec == RECORD
    assert sha == "abc123def456"
    assert len(fake.calls) == 1
    assert fake.auth_used == [True]


def test_anonymous_mode_makes_one_request(monkeypatch):
    """With no token there is nothing to fall back from."""
    fake = _install(monkeypatch, [FakeResp(200, _ok_payload(RECORD))], token=None)
    rec, _ = m._fetch_cached_record(PID)

    assert rec == RECORD
    assert len(fake.calls) == 1
    assert fake.auth_used == [False]


def test_fallback_failure_returns_none_not_raise(monkeypatch):
    """If the anonymous retry also fails we degrade to a miss, never crash."""
    fake = _install(
        monkeypatch,
        [FakeResp(403, text="denied"), FakeResp(403, text="denied again")],
    )
    rec, sha = m._fetch_cached_record(PID)

    assert rec is None and sha is None
    assert len(fake.calls) == 2


def test_network_exception_on_auth_falls_back(monkeypatch):
    """A transport error on the authed attempt should also try anonymous."""
    import requests

    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append("Authorization" in (headers or {}))
        if len(calls) == 1:
            raise requests.RequestException("boom")
        return FakeResp(200, _ok_payload(RECORD))

    monkeypatch.setattr(m.requests, "get", fake_get)
    monkeypatch.setattr(m, "_write_token", lambda: "tok")

    rec, sha = m._fetch_cached_record(PID)
    assert rec == RECORD
    assert sha == "abc123def456"
    assert calls == [True, False]
