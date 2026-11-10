"""Per-recipient personalization for the Agroverse newsletter.

Deliberately dependency-free (no gspread / google API imports) so the
substitution rules can be unit-tested without live credentials.

The guiding rule: **never invent a name.** If a recipient has no stored name,
they get a neutral greeting. In particular an email local-part is never mined
for a first name -- "Hi jrunnion1231," is worse than "Hi," on a trust asset.
"""

from __future__ import annotations

import re

GREETING_PLACEHOLDER = "{{greeting}}"
FIRST_NAME_PLACEHOLDER = "{{first_name}}"

# Subscriber-tab column names accepted as a name source, in priority order.
NAME_COLUMN_CANDIDATES = ("Name", "First Name", "Full Name", "Preferred Name")

DEFAULT_FALLBACK_GREETING = "Hi,"


def first_name_from_value(raw: str) -> str:
    """Reduce a stored name value to a greeting-safe first name.

    Returns "" when the value does not look like a person's name, so the
    caller falls back to an unnamed greeting instead of printing something
    wrong (a company, a ledger name, a farm name, an email address).
    """
    v = (raw or "").strip()
    if not v:
        return ""
    if "@" in v:  # never greet by email local-part
        return ""
    if any(ch.isdigit() for ch in v):  # SKUs, ledger ids, dates
        return ""
    v = re.sub(r"^[^A-Za-z\u00c0-\u024f]+", "", v)
    parts = [p for p in re.split(r"[\s,]+", v) if p]
    if not parts:
        return ""
    first = parts[0]
    if len(first) < 2 or not first.isalpha():
        return ""
    return first[:1].upper() + first[1:]


def personalize_text(
    text: str, first_name: str, fallback_greeting: str = DEFAULT_FALLBACK_GREETING
) -> str:
    """Fill `{{greeting}}` / `{{first_name}}` for a single recipient."""
    name = (first_name or "").strip()
    greeting = f"Hi {name}," if name else fallback_greeting
    out = text.replace(GREETING_PLACEHOLDER, greeting)
    out = out.replace(FIRST_NAME_PLACEHOLDER, name)
    return out
