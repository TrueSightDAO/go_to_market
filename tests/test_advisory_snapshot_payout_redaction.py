"""Public-surface privacy guard for ADVISORY_SNAPSHOT.md (CRF plan SS11.4).

`ADVISORY_SNAPSHOT.md` is committed to the PUBLIC `agentic_ai_context` repo and
re-derived on a schedule. Its "Recent ecosystem activity (Telegram Chat Logs)"
section renders the last ~50 rows of the canonical `Telegram Chat Logs` workbook
-- the SAME workbook Edgar writes every signed event into, including
`[PAYOUT REGISTRATION]`, whose body carries a raw PIX key (often a CPF).

SS11.4 requires that all three public-cache generators exclude this event; the
other two (sync_sunmint_signatures.py / ledger_emit.py) are already done, so this
test pins the third: the snapshot renderer must never emit a `[PAYOUT REGISTRATION]`
body -- not into the tag rollup, not into the latest-entries excerpt.

Run: python3 -m pytest tests/test_advisory_snapshot_payout_redaction.py -q
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "generate_advisory_snapshot.py"

RAW_PIX = "123.456.789-01"
SAMPLE = """[PAYOUT REGISTRATION]
- Planting identity (pk_hash): pk-abcdefghijkl
- Program: crf-anapu
- PIX key type: CPF
- PIX key: {pix}
--------""".format(pix=RAW_PIX)


def _load():
    spec = importlib.util.spec_from_file_location("gas_mod", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_marker_helper_recognises_tag_first_line_only():
    mod = _load()
    assert mod._is_public_excluded_event(SAMPLE) is True
    # a bare mention deeper in a body is NOT an event
    assert (
        mod._is_public_excluded_event("hello\n[PAYOUT REGISTRATION] mention") is False
    )
    # an ordinary event is untouched
    assert mod._is_public_excluded_event("[CONTRIBUTION EVENT]\n- Type: Time") is False


def test_redact_drops_only_excluded_rows():
    mod = _load()
    rows = [
        ["1", "c", "n", "m", "reporter", "", SAMPLE],  # excluded
        ["2", "c", "n", "m", "reporter", "", "[CONTRIBUTION EVENT]\nx"],  # kept
    ]
    out = mod._redact_excluded_rows(rows)
    assert len(out) == 1
    assert out[0][0] == "2"


def test_payout_body_never_appears_in_render():
    """Drive the real renderer with a fake worksheet; assert the raw PIX is absent."""
    mod = _load()
    header = [
        "Update ID",
        "Chatroom ID",
        "Chatroom Name",
        "Message ID",
        "Reporter",
        "",
        "Message",
    ]
    rows = [header] + [
        [
            "1",
            "-",
            "capoeira",
            "m1",
            "Alice",
            "",
            "[CONTRIBUTION EVENT]\n- Type: Time\n- Amount: 30",
        ],
        ["2", "-", "cfr", "m2", "Bob", "", SAMPLE],
        ["3", "-", "cfr", "m3", "Bob", "", "[PRACTICE EVENT]\n- Practice Type: oracle"],
    ]

    class _WS:
        def __init__(self):
            self.row_count = len(rows)

        def get(self, _rng):
            return rows

        def __getattr__(self, _n):
            return lambda *a, **k: None

    class _SH:
        def worksheet(self, _name):
            return _WS()

    class _GC:
        def open_by_key(self, _key):
            return _SH()

    # Inject fake gspread + creds that authenticate to our stub.
    import sys
    import types

    fake_gspread = types.ModuleType("gspread")
    fake_gspread.authorize = lambda _creds: _GC()
    sys.modules["gspread"] = fake_gspread

    fake_sa = types.ModuleType("google.oauth2.service_account")

    class _Creds:
        @staticmethod
        def from_service_account_file(*_a, **_k):
            return object()

    fake_sa.Credentials = _Creds
    sys.modules.setdefault("google", types.ModuleType("google"))
    sys.modules.setdefault("google.oauth2", types.ModuleType("google.oauth2"))
    sys.modules["google.oauth2.service_account"] = fake_sa

    # Point the cred path at a stub file so the early-return guard passes.
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        cred = Path(d) / "google_credentials.json"
        cred.write_text("{}")
        out = mod._fetch_telegram_recent_activity_markdown(Path(d))

    assert RAW_PIX not in out, "raw PIX leaked into the public snapshot render!"
    assert "123.456.789" not in out
    assert "PAYOUT REGISTRATION" not in out, "excluded event surfaced in the rollup"
    # the ordinary events DO render (we redact, not blank the section)
    assert "CONTRIBUTION EVENT" in out
    assert "PRACTICE EVENT" in out
