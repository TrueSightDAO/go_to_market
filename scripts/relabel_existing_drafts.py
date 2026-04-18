#!/usr/bin/env python3
"""
One-off script: relabel existing Gmail drafts from "Email Agent suggestions"
to "AI/Follow-up" or "AI/Warm-up" based on the Email Agent Suggestions sheet.

Matching logic:
  - protocol_version contains "warmup_intro" → AI/Warm-up
  - otherwise                                → AI/Follow-up
  - drafts with no sheet match → skipped (printed for review)

Usage:
  cd market_research
  python3 scripts/relabel_existing_drafts.py --dry-run
  python3 scripts/relabel_existing_drafts.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from googleapiclient.discovery import build

import suggest_manager_followup_drafts as smf

_REPO = Path(__file__).resolve().parent.parent
_GMAIL_TOKEN = _REPO / "credentials" / "gmail" / "token.json"

OLD_LABEL = "Email Agent suggestions"
FOLLOWUP_LABEL = "AI/Follow-up"
WARMUP_LABEL = "AI/Warm-up"

SPREADSHEET_ID = smf.SPREADSHEET_ID
SUGGESTIONS_WS = smf.SUGGESTIONS_WS
GMAIL_SCOPES = smf.GMAIL_SCOPES


def get_or_create_label(service, name: str) -> str:
    resp = service.users().labels().list(userId="me").execute()
    for lab in resp.get("labels", []):
        if lab.get("name") == name:
            return str(lab["id"])
    body = {"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"}
    created = service.users().labels().create(userId="me", body=body).execute()
    print(f"  Created label: {name!r} → {created['id']}")
    return str(created["id"])


def load_draft_kind_map(sa) -> dict[str, str]:
    """Returns {gmail_draft_id: 'warmup'|'followup'} from the sheet."""
    sh = sa.open_by_key(SPREADSHEET_ID)
    try:
        ws = sh.worksheet(SUGGESTIONS_WS)
    except Exception as e:
        print(f"WARNING: could not open {SUGGESTIONS_WS!r}: {e}")
        return {}
    values = ws.get_all_values()
    if len(values) < 2:
        return {}
    hdr = smf.header_map(values[0])
    draft_i = hdr.get("gmail_draft_id")
    proto_i = hdr.get("protocol_version")
    if draft_i is None:
        print("WARNING: no gmail_draft_id column in sheet — all unmatched drafts will be skipped.")
        return {}
    out: dict[str, str] = {}
    for row in values[1:]:
        did = smf.cell(row, draft_i).strip()
        if not did:
            continue
        proto = smf.cell(row, proto_i).strip() if proto_i is not None else ""
        kind = "warmup" if "warmup" in proto.lower() else "followup"
        out[did] = kind
    return out


def list_all_drafts_with_label(service, label_id: str) -> list[dict]:
    """Fetch all draft resources that have this label on their message."""
    drafts = []
    page_token = None
    while True:
        resp = service.users().drafts().list(
            userId="me", maxResults=50, pageToken=page_token
        ).execute()
        for d in resp.get("drafts") or []:
            did = d.get("id")
            if not did:
                continue
            try:
                dr = service.users().drafts().get(userId="me", id=did, format="metadata").execute()
            except Exception:
                continue
            msg = dr.get("message") or {}
            if label_id in (msg.get("labelIds") or []):
                drafts.append({"draft_id": did, "msg_id": msg.get("id", "")})
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return drafts


def main() -> None:
    parser = argparse.ArgumentParser(description="Relabel existing AI draft emails.")
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
    kind_map = load_draft_kind_map(sa)
    print(f"Sheet draft map: {len(kind_map)} entries ({sum(1 for v in kind_map.values() if v=='warmup')} warmup, "
          f"{sum(1 for v in kind_map.values() if v=='followup')} followup)")

    # Resolve label IDs
    all_labels = gsvc.users().labels().list(userId="me").execute().get("labels", [])
    old_label_id = next((l["id"] for l in all_labels if l["name"] == OLD_LABEL), None)
    if not old_label_id:
        print(f"Label {OLD_LABEL!r} not found in Gmail — nothing to relabel.")
        return

    if args.dry_run:
        followup_id = "(dry-run)"
        warmup_id = "(dry-run)"
    else:
        followup_id = get_or_create_label(gsvc, FOLLOWUP_LABEL)
        warmup_id = get_or_create_label(gsvc, WARMUP_LABEL)

    print(f"Scanning drafts with label {OLD_LABEL!r} (id={old_label_id})…")
    drafts = list_all_drafts_with_label(gsvc, old_label_id)
    print(f"Found {len(drafts)} draft(s) with old label.")

    n_followup = n_warmup = n_unmatched = 0
    for d in drafts:
        did = d["draft_id"]
        mid = d["msg_id"]
        kind = kind_map.get(did)
        if kind is None:
            print(f"  UNMATCHED draft {did!r} (msg {mid!r}) — no sheet row; skipping")
            n_unmatched += 1
            continue
        new_label = WARMUP_LABEL if kind == "warmup" else FOLLOWUP_LABEL
        new_label_id = warmup_id if kind == "warmup" else followup_id
        print(f"  {'[dry-run] ' if args.dry_run else ''}draft {did!r} → {new_label!r}")
        if not args.dry_run and mid:
            gsvc.users().messages().modify(
                userId="me",
                id=mid,
                body={"addLabelIds": [new_label_id], "removeLabelIds": [old_label_id]},
            ).execute()
        if kind == "warmup":
            n_warmup += 1
        else:
            n_followup += 1

    print(
        f"\nDone. followup={n_followup} warmup={n_warmup} unmatched={n_unmatched} "
        f"mode={'dry_run' if args.dry_run else 'live'}"
    )


if __name__ == "__main__":
    main()
