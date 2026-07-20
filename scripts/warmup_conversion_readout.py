#!/usr/bin/env python3
"""
Reply-rate readout for first-touch warm-up sends, split by **segment**
(`Hosts Circles` yes/no — the 2026-07-18 stats review found this predicts
conversion ~1.8x, see `agentic_ai_context/plans/WARMUP_CONVERSION_IMPROVEMENT_PLAN.md`)
and by **channel** (auto-sent via `send_clean_warmup_drafts.py` vs. human-sent
directly in Gmail).

Why this exists: `WARMUP_AUTOSEND_PLAN.md` §6 promised a 30-day metrics
readout after the auto-send graduation shipped 2026-06-05. It was never run —
a 6-week-old reply-rate collapse (6% -> 0.3%) sat undetected until an
on-demand stats review caught it. This script is the readout, made runnable
on demand and (via the paired GitHub Actions workflow) on a schedule that
can't be silently skipped again.

Read-only: only reads `Hit List` and `Email Agent Drafts` (Sheets API,
service account). No Gmail calls, no writes.

**Engaged** (a warm-up cohort member counts as having produced signal) means
the Hit List row's *current* Status is one of `AI: Prospect replied`,
`Partnered`, `Manager Follow-up`, `Rejected`, `Deferred / Revisit later`, `On
Hold` -- **except** rows parked by the auto-reply-only logic in
`suggest_warmup_prospect_drafts.py` (Notes contains "parked: auto-responder
only"), which are confirmed dead mailboxes, not engagement. This is a
retroactive, best-effort classification against *current* sheet state, not a
point-in-time snapshot -- a row's status can have moved for reasons unrelated
to this specific send (e.g. re-enriched after a bounce). Treat the read as
directional, not exact.

Usage:
  cd market_research
  python3 scripts/warmup_conversion_readout.py
  python3 scripts/warmup_conversion_readout.py --since 2026-06-05
  python3 scripts/warmup_conversion_readout.py --output reports/warmup_conversion_readout_latest.md
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SCRIPTS = _REPO / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import suggest_manager_followup_drafts as smf  # noqa: E402
from suggest_warmup_prospect_drafts import classify_warmup_segment  # noqa: E402

WARMUP_LABEL = "AI/Warm-up"
SENT_STATUS = "sent"
AUTOSEND_MARKER = "auto-sent by send_clean_warmup_drafts"
AUTO_PARK_MARKER = "parked: auto-responder only"

# Auto-send launch date (WARMUP_AUTOSEND_PLAN.md) -- default cutoff so the
# pre-automation, hand-curated era doesn't dilute the read on the automated
# channel's own performance. Override with --since for an all-time view.
DEFAULT_SINCE = "2026-06-05"

ENGAGED_STATUSES = {
    "AI: Prospect replied",
    "Partnered",
    "Manager Follow-up",
    "Rejected",
    "Deferred / Revisit later",
    "On Hold",
}


def _parse_dt(ts: str) -> datetime | None:
    if not ts:
        return None
    ts = ts.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(ts, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _load_hit_list_by_row(ws) -> dict[int, dict]:
    values = ws.get_all_values()
    if not values:
        return {}
    hdr = smf.header_map(values[0])
    status_i = hdr.get("Status")
    shop_type_i = hdr.get("Shop Type")
    hosts_circles_i = hdr.get("Hosts Circles")
    notes_i = hdr.get("Notes")
    out: dict[int, dict] = {}
    for r, row in enumerate(values[1:], start=2):
        out[r] = {
            "status": smf.cell(row, status_i) if status_i is not None else "",
            "shop_type": smf.cell(row, shop_type_i) if shop_type_i is not None else "",
            "hosts_circles": smf.cell(row, hosts_circles_i) if hosts_circles_i is not None else "",
            "notes": smf.cell(row, notes_i) if notes_i is not None else "",
        }
    return out


def _load_sent_warmup_drafts(ws) -> list[dict]:
    values = ws.get_all_values()
    if not values:
        return []
    hdr = smf.header_map(values[0])
    need = ["status", "gmail_label", "created_at_utc", "notes", "hit_list_row", "shop_name"]
    for k in need:
        if k not in hdr:
            sys.stderr.write(f"Email Agent Drafts missing column: {k}\n")
            sys.exit(1)
    out: list[dict] = []
    for row in values[1:]:
        if smf.cell(row, hdr["status"]) != SENT_STATUS:
            continue
        if smf.cell(row, hdr["gmail_label"]) != WARMUP_LABEL:
            continue
        hit_row_raw = smf.cell(row, hdr["hit_list_row"])
        first_row = hit_row_raw.split(",")[0].strip() if hit_row_raw else ""
        out.append({
            "created_at_utc": smf.cell(row, hdr["created_at_utc"]),
            "notes": smf.cell(row, hdr["notes"]),
            "hit_list_row": int(first_row) if first_row.isdigit() else None,
            "shop_name": smf.cell(row, hdr["shop_name"]),
        })
    return out


def _is_engaged(hit: dict | None) -> bool:
    if hit is None:
        return False
    status = hit.get("status", "")
    if status not in ENGAGED_STATUSES:
        return False
    if AUTO_PARK_MARKER in (hit.get("notes") or ""):
        return False
    return True


def _channel(notes: str) -> str:
    return "auto" if AUTOSEND_MARKER in (notes or "") else "human"


def build_readout(since: str) -> tuple[str, dict]:
    sa = smf.get_sheets_client()
    sh = sa.open_by_key(smf.SPREADSHEET_ID)
    hit_ws = sh.worksheet("Hit List")
    drafts_ws = sh.worksheet("Email Agent Drafts")

    hit_by_row = _load_hit_list_by_row(hit_ws)
    sent = _load_sent_warmup_drafts(drafts_ws)

    since_dt = _parse_dt(since) if since else None
    rows = []
    for d in sent:
        dt = _parse_dt(d["created_at_utc"])
        if since_dt and dt and dt < since_dt:
            continue
        hit = hit_by_row.get(d["hit_list_row"]) if d["hit_list_row"] else None
        segment = classify_warmup_segment(
            (hit or {}).get("shop_type", ""), (hit or {}).get("hosts_circles", "")
        )
        rows.append({
            "shop_name": d["shop_name"],
            "segment": segment,
            "channel": _channel(d["notes"]),
            "engaged": _is_engaged(hit),
        })

    def _rate_block(subset: list[dict]) -> dict:
        n = len(subset)
        engaged = sum(1 for r in subset if r["engaged"])
        return {"n": n, "engaged": engaged, "rate": (engaged / n * 100) if n else 0.0}

    by_segment = {
        seg: _rate_block([r for r in rows if r["segment"] == seg])
        for seg in sorted({r["segment"] for r in rows})
    }
    by_channel = {
        ch: _rate_block([r for r in rows if r["channel"] == ch])
        for ch in sorted({r["channel"] for r in rows})
    }
    by_segment_channel = {
        (seg, ch): _rate_block([r for r in rows if r["segment"] == seg and r["channel"] == ch])
        for seg in sorted({r["segment"] for r in rows})
        for ch in sorted({r["channel"] for r in rows})
    }
    overall = _rate_block(rows)

    lines = []
    lines.append("# Warm-up conversion readout")
    lines.append("")
    lines.append(
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | "
        f"cohort: sent `AI/Warm-up` first-touch, since `{since or 'all-time'}`"
    )
    lines.append("")
    lines.append(
        f"**Overall:** {overall['n']} sent, {overall['engaged']} engaged "
        f"({overall['rate']:.1f}%)"
    )
    lines.append("")
    lines.append("## By segment")
    lines.append("")
    lines.append("| Segment | Sent | Engaged | Rate |")
    lines.append("|---|---|---|---|")
    for seg, b in sorted(by_segment.items(), key=lambda kv: -kv[1]["rate"]):
        lines.append(f"| {seg} | {b['n']} | {b['engaged']} | {b['rate']:.1f}% |")
    lines.append("")
    lines.append("## By channel")
    lines.append("")
    lines.append("| Channel | Sent | Engaged | Rate |")
    lines.append("|---|---|---|---|")
    for ch, b in sorted(by_channel.items(), key=lambda kv: -kv[1]["rate"]):
        lines.append(f"| {ch} | {b['n']} | {b['engaged']} | {b['rate']:.1f}% |")
    lines.append("")
    lines.append("## By segment x channel")
    lines.append("")
    lines.append("| Segment | Channel | Sent | Engaged | Rate |")
    lines.append("|---|---|---|---|---|")
    for (seg, ch), b in sorted(by_segment_channel.items(), key=lambda kv: -kv[1]["rate"]):
        if b["n"] == 0:
            continue
        lines.append(f"| {seg} | {ch} | {b['n']} | {b['engaged']} | {b['rate']:.1f}% |")
    lines.append("")
    lines.append(
        "_\"Engaged\" = Hit List row currently in a reply-derived status "
        "(replied / partnered / manager follow-up / rejected / deferred / on-hold), "
        "excluding rows parked as confirmed auto-responder-only dead ends. "
        "Retroactive against current sheet state, not a point-in-time snapshot -- "
        "read directionally, not as an exact per-send outcome._"
    )

    return "\n".join(lines), {
        "overall": overall, "by_segment": by_segment, "by_channel": by_channel,
        "by_segment_channel": by_segment_channel,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--since", default=DEFAULT_SINCE, help=f"ISO date cutoff (default {DEFAULT_SINCE}, auto-send launch). Empty string for all-time.")
    p.add_argument("--output", type=Path, default=None, help="Also write the markdown report to this path.")
    args = p.parse_args(argv)

    report, _stats = build_readout(args.since)
    print(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report + "\n", encoding="utf-8")
        print(f"\nWrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
