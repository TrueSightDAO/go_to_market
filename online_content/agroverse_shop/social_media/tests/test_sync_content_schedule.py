"""Tests for the Status-dropdown re-application in sync_content_schedule.py.

Regression guard: worksheet.clear() wipes ALL data validation on the target tab,
so the dropdown MUST be re-created after every write. Earlier revisions asserted
the opposite in comments and in a log line, while the live Instagram Content
Schedule tab measured 0 validated cells (2026-11-11).

Heavy third-party imports (pandas / gspread / dotenv) are stubbed ONLY when the
real package is unavailable, so this suite runs on a bare box as well as in CI.
"""

import importlib.util
import pathlib
import sys
import types

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "sync_content_schedule.py"

_STUBBED = ("pandas", "gspread", "dotenv")


def _stub_module(name):
    """A permissive stand-in for a module this script imports at load time."""
    mod = types.ModuleType(name)

    def _getattr(attr):
        # Any imported name becomes a harmless no-op class.
        return type(attr, (), {"__init__": lambda self, *a, **k: None})

    mod.__getattr__ = _getattr
    return mod


def _load_module():
    name = "sync_content_schedule_under_test"
    if name in sys.modules:
        return sys.modules[name]

    for dep in _STUBBED:
        try:
            __import__(dep)
        except Exception:
            sys.modules[dep] = _stub_module(dep)

    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class _FakeWorksheet:
    id = 7


class _FakeSpreadsheet:
    def __init__(self):
        self.requests = None

    def batch_update(self, body):
        self.requests = body


def _syncer_with(spreadsheet):
    mod = _load_module()
    syncer = mod.ContentScheduleSyncer.__new__(mod.ContentScheduleSyncer)
    syncer.spreadsheet = spreadsheet
    return syncer


def test_status_options_match_configuration_vocabulary():
    """Must stay in sync with Configuration!A9:A13 (canonical workbook vocab)."""
    mod = _load_module()
    assert mod.ContentScheduleSyncer.STATUS_OPTIONS == [
        "PLANNED",
        "CRAFTING",
        "SCHEDULED",
        "PUBLISHED",
    ]


def test_validation_targets_status_column_only():
    ss = _FakeSpreadsheet()
    syncer = _syncer_with(ss)
    syncer.apply_status_validation(_FakeWorksheet(), row_count=5)

    req = ss.requests["requests"][0]["setDataValidation"]
    rng = req["range"]

    # Column B only: 0-based index 1..2 (end-exclusive).
    assert rng["startColumnIndex"] == 1
    assert rng["endColumnIndex"] == 2
    # Rows 2..5 => startRowIndex 1, endRowIndex 5.
    assert rng["startRowIndex"] == 1
    assert rng["endRowIndex"] == 5
    assert rng["sheetId"] == 7

    condition = req["rule"]["condition"]
    assert condition["type"] == "ONE_OF_LIST"
    assert [v["userEnteredValue"] for v in condition["values"]] == syncer.STATUS_OPTIONS


def test_validation_is_non_strict_so_existing_text_survives():
    ss = _FakeSpreadsheet()
    syncer = _syncer_with(ss)
    syncer.apply_status_validation(_FakeWorksheet(), row_count=3)

    rule = ss.requests["requests"][0]["setDataValidation"]["rule"]
    assert rule["strict"] is False
    assert rule["showCustomUi"] is True


def test_validation_failure_does_not_abort_sync():
    """The row write already succeeded; a formatting error must not raise."""

    class _Boom:
        def batch_update(self, body):
            raise RuntimeError("api down")

    syncer = _syncer_with(_Boom())
    syncer.apply_status_validation(_FakeWorksheet(), row_count=3)  # must not raise
