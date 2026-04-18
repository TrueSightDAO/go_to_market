#!/usr/bin/env python3
"""
One-off: apply AI/Sent Follow-up or AI/Sent Warm-up to historical sent messages
(messages that went out before the review→sent label-swap was in place).

Matching strategy (per row in Email Agent Follow Up):
  1. Find all Email Agent Suggestions rows with the same to_email.
  2. If all suggestions for that email are one type → apply that type.
  3. If mixed, pick the suggestion with the latest created_at_utc BEFORE the
     sent_at of the follow-up row (closest prior suggestion).
  4. If still ambiguous, fall back to exact subject match.
  5. If no suggestion match at all → skip (unmatched), print for review.

Usage:
  cd market_research
  python3 scripts/label_historical_sent.py --dry-run
  python3 scripts/label_historical_sent.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from googleapiclient.discovery import build

import suggest_manager_followup_drafts as smf
import sync_email_agent_followup as sync

_REPO = Path(__file__).resolve().parent.parent
_GMAIL_TOKEN = _REPO / "credentials" / "gmail" / "token.json"

SPREADSHEET_ID = smf.SPREADSHEET_ID
SUGGESTIONS_WS = smf.SUGGESTIONS_WS
LOG_WS = smf.LOG_WS

SENT_LABEL_FOLLOWUP = sync.SENT_LABEL_FOLLOWUP
SENT_LABEL_WARMUP = sync.SENT_LABEL_WARMUP
GMAIL_SCOPES = smf.GMAIL_SCOPES


def classify(proto: str) -> str:
    return "warmup" if "warmup" in (proto or "").lower() else "followup"


def parse_dt(raw: str) -> datetime | None:
    if not raw:
        return None
    s = raw.strip()
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def load_suggestions(sa) -> dict[str, list[dict]]:
    """Returns {to_email: [{created, subject, kind}]} sorted by created ascending."""
    sh = sa.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(SUGGESTIONS_WS)
    values = ws.get_all_values()
    if len(values) < 2:
        return {}
    hdr = smf.header_map(values[0])
    em_i = hdr.get("to_email")
    subj_i = hdr.get("subject")
    proto_i = hdr.get("protocol_version")
    created_i = hdr.get("created_at_utc")
    if em_i is None:
        return {}
    out: dict[str, list[dict]] = {}
    for row in values[1:]:
        em = smf.normalize_email(smf.cell(row, em_i))
        if not em:
            continue
        proto = smf.cell(row, proto_i) if proto_i is not None else ""
        subject = smf.cell(row, subj_i) if subj_i is not None else ""
        created = parse_dt(smf.cell(row, created_i)) if created_i is not None else None
        out.setdefault(em, []).append(
            {"created": created, "subject": subject, "kind": classify(proto)}
        )
    for em in out:
        out[em].sort(key=lambda x: x["created"] or datetime.min.replace(tzinfo=timezone.utc))
    return out


def load_followup_log(sa) -> list[dict]:
    sh = sa.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(LOG_WS)
    values = ws.get_all_values()
    if len(values) < 2:
        return []
    hdr = smf.header_map(values[0])
    mid_i = hdr.get("gmail_message_id")
    em_i = hdr.get("to_email")
    subj_i = hdr.get("subject")
    sent_i = hdr.get("sent_at")
    if mid_i is None or em_i is None:
        return []
    out = []
    for row in values[1:]:
        mid = smf.cell(row, mid_i)
        em = smf.normalize_email(smf.cell(row, em_i))
        if not mid or not em:
            continue
        out.append({
            "mid": mid,
            "to_email": em,
            "subject": smf.cell(row, subj_i) if subj_i is not None else "",
            "sent_at": parse_dt(smf.cell(row, sent_i)) if sent_i is not None else None,
        })
    return out


def pick_kind(suggestions: list[dict], sent_at: datetime | None, subject: str) -> str | None:
    if not suggestions:
        return None
    kinds = {s["kind"] for s in suggestions}
    if len(kinds) == 1:
        return kinds.pop()
    # Mixed types — try closest prior suggestion by created date.
    if sent_at is not None:
        prior = [s for s in suggestions if s["created"] and s["created"] <= sent_at]
        if prior:
            return prior[-1]["kind"]
    # Fall back to exact subject match.
    for s in suggestions:
        if s["subject"].strip() == subject.strip():
            return s["kind"]
    # Last resort — most recent overall.
    return suggestions[-1]["kind"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Label historical sent messages.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--expected-mailbox", default=smf.EXPECTED_MAILBOX)
    args = parser.parse_args()

    gcreds = smf.load_gmail_user_credentials(_GMAIL_TOKEN, GMAIL_SCOPES)
    gsvc = build("gmail", "v1", credentials=gcreds, cache_discovery=False)
    me = smf.gmail_profile_email(gsvc)
    if me != args.expected_mailbox.strip().lower():
        sys.stderr.write(f"Gmail profile is {me!r}, expected {args.expected_mailbox!r}.\n")
        sys.exit(1)

    sa = smf.get_sheets_client()
    suggestions = load_suggestions(sa)
    log = load_followup_log(sa)
    print(f"Loaded suggestions for {len(suggestions)} distinct emails.")
    print(f"Loaded {len(log)} rows from {LOG_WS!r}.")

    label_map = sync.build_label_id_map(gsvc)
    if args.dry_run:
        fu_id = "(dry-run)"
        wu_id = "(dry-run)"
    else:
        fu_id = sync._get_or_create_label_id(gsvc, SENT_LABEL_FOLLOWUP, label_map)
        wu_id = sync._get_or_create_label_id(gsvc, SENT_LABEL_WARMUP, label_map)

    n_fu = n_wu = n_skip = n_err = n_already = 0
    for row in log:
        sug = suggestions.get(row["to_email"])
        kind = pick_kind(sug or [], row["sent_at"], row["subject"])
        if kind is None:
            n_skip += 1
            continue
        target_name = SENT_LABEL_WARMUP if kind == "warmup" else SENT_LABEL_FOLLOWUP
        target_id = wu_id if kind == "warmup" else fu_id

        if args.dry_run:
            if kind == "warmup":
                n_wu += 1
            else:
                n_fu += 1
            continue

        try:
            meta = gsvc.users().messages().get(
                userId="me", id=row["mid"], format="metadata", metadataHeaders=["Subject"]
            ).execute()
            if target_id in (meta.get("labelIds") or []):
                n_already += 1
                continue
            gsvc.users().messages().modify(
                userId="me",
                id=row["mid"],
                body={"addLabelIds": [target_id]},
            ).execute()
            if kind == "warmup":
                n_wu += 1
            else:
                n_fu += 1
        except Exception as e:
            sys.stderr.write(f"  error on {row['mid'][:16]}… {row['to_email']}: {e}\n")
            n_err += 1

    print(
        f"\nDone. sent_followup={n_fu} sent_warmup={n_wu} already_labeled={n_already} "
        f"unmatched={n_skip} errors={n_err} mode={'dry_run' if args.dry_run else 'live'}"
    )


if __name__ == "__main__":
    main()
