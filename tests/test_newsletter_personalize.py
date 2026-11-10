"""Unit tests for newsletter per-recipient personalization."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from newsletter_personalize import (
    DEFAULT_FALLBACK_GREETING,
    first_name_from_value,
    personalize_text,
)


def test_first_name_from_full_name():
    assert first_name_from_value("Gary Teh") == "Gary"


def test_first_name_from_single_name():
    assert first_name_from_value("Melinda") == "Melinda"


def test_first_name_is_capitalized():
    assert (
        first_name_from_value("gARY") == "GARY"[:1] + "ARY"
    )  # only first char touched
    assert first_name_from_value("kirsten") == "Kirsten"


def test_first_name_from_comma_form():
    assert first_name_from_value("Teh, Gary") == "Teh"


def test_never_greet_by_email_local_part():
    # Only address-shaped values are rejected here. A bare local-part like
    # "garyjob" is deliberately NOT passed to this function by the caller --
    # with no "@" and no digits it is indistinguishable from a real first name.
    # The module only ever receives values from a name column.
    assert first_name_from_value("jrunnion1231@gmail.com") == ""
    assert first_name_from_value("melinda_larios@hotmail.com") == ""


def test_rejects_ledger_and_sku_values():
    assert first_name_from_value("AGL13") == ""
    assert first_name_from_value("2024") == ""
    assert first_name_from_value("") == ""
    assert first_name_from_value("   ") == ""


def test_rejects_short_or_non_alpha():
    assert first_name_from_value("J") == ""
    assert first_name_from_value("--") == ""


def test_personalize_fills_greeting():
    assert personalize_text("{{greeting}} hello", "Gary") == "Hi Gary, hello"


def test_personalize_falls_back_when_no_name():
    out = personalize_text("{{greeting}} hello", "")
    assert out == f"{DEFAULT_FALLBACK_GREETING} hello"
    assert "{{" not in out


def test_personalize_fills_first_name_placeholder():
    assert personalize_text("Hi {{first_name}}!", "Kirsten") == "Hi Kirsten!"
    assert personalize_text("Hi {{first_name}}!", "") == "Hi !"


def test_personalize_is_noop_without_placeholders():
    body = "Nothing to fill here."
    assert personalize_text(body, "Gary") == body
