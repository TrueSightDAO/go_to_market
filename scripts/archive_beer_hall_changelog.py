#!/usr/bin/env python3
"""
Write one Beer Hall archive file (Markdown + YAML frontmatter) into the
**ecosystem_change_logs** repo for git review and future truesight.me surfacing.

Structured fields live in YAML; long WhatsApp copy lives in Markdown sections
below the frontmatter (avoids YAML escaping pain for multiline TLDR/Shipped).

Usage (from market_research/):
  python3 scripts/archive_beer_hall_changelog.py \\
    --repo ../ecosystem_change_logs \\
    --slug inventory-publish \\
    --tldr-file /tmp/beer_hall_msg1.txt \\
    --message2-file /tmp/beer_hall_msg2.txt \\
    --links 'https://docs.google.com/...' \\
    --pr-commit-links 'https://github.com/TrueSightDAO/...' \\
    --openclaw-message-id 'msg1=...; msg2=...' \\
    --notes 'optional'

Then: git -C ../ecosystem_change_logs add beer_hall/entries && git commit && gh pr create ...
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _yaml_single_quoted(s: str) -> str:
    """YAML single-quoted scalar (escape ' as '')."""
    t = (s or "").replace("'", "''")
    return f"'{t}'"


def _split_urls(blob: str) -> list[str]:
    parts = re.split(r"[\s\n]+", (blob or "").strip())
    return [p for p in parts if p.startswith("http")]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--repo",
        type=Path,
        default=_REPO.parent / "ecosystem_change_logs",
        help="Path to ecosystem_change_logs git checkout (default: sibling of market_research)",
    )
    p.add_argument("--slug", default="update", help="Short filename hint (letters, numbers, hyphen).")
    p.add_argument("--posted-at-utc", default="", dest="posted_at_utc", help="ISO UTC; default now()")
    p.add_argument("--tldr-file", type=Path, required=True, dest="tldr_file")
    p.add_argument("--message2-file", type=Path, required=True, dest="message2_file")
    p.add_argument("--links", default="", help="Space/newline separated URLs (sheet, etc.)")
    p.add_argument("--pr-commit-links", default="", dest="pr_commit_links")
    p.add_argument("--openclaw-message-id", default="", dest="openclaw_message_id")
    p.add_argument("--notes", default="")
    p.add_argument(
        "--sheet-log",
        default="OpenClaw Beer Hall updates",
        dest="sheet_log",
        help="Sheet tab name for the closed-loop row",
    )
    p.add_argument("--dry-run", action="store_true", help="Print path + body only; do not write.")
    args = p.parse_args()

    repo: Path = args.repo.resolve()
    entries = repo / "beer_hall" / "entries"
    if not args.dry_run:
        entries.mkdir(parents=True, exist_ok=True)

    posted = (args.posted_at_utc or "").strip()
    if not posted:
        posted = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Filename prefix: strip : for filesystem safety on some OSes
    posted_compact = posted.replace(":", "").replace("+00:00", "Z")
    if not posted_compact.endswith("Z") and "T" in posted_compact:
        posted_compact = posted_compact + "Z" if posted_compact[-1] != "Z" else posted_compact
    slug = re.sub(r"[^a-zA-Z0-9-]+", "-", args.slug.strip() or "update").strip("-").lower() or "update"
    fname = f"beer-hall_{posted_compact}_{slug}.md"
    out = entries / fname

    tldr = _read_text(args.tldr_file)
    shipped = _read_text(args.message2_file)
    links = _split_urls(args.links)
    prs = _split_urls(args.pr_commit_links)

    id_base = posted.replace(":", "").replace("+00:00", "Z")
    entry_id = f"beer-hall-{id_base}"

    def _list_yaml(key: str, items: list[str]) -> str:
        if not items:
            return f"{key}: []\n"
        lines = [f"{key}:"]
        for u in items:
            lines.append(f"  - {_yaml_single_quoted(u)}")
        return "\n".join(lines) + "\n"

    fm = []
    fm.append("---\n")
    fm.append(f"id: {_yaml_single_quoted(entry_id)}\n")
    fm.append("channel: beer_hall\n")
    fm.append(f"posted_at_utc: {_yaml_single_quoted(posted)}\n")
    fm.append(f"slug: {_yaml_single_quoted(slug)}\n")
    fm.append(f"sheet_log: {_yaml_single_quoted(args.sheet_log)}\n")
    if args.openclaw_message_id.strip():
        fm.append(f"openclaw_message_id: {_yaml_single_quoted(args.openclaw_message_id.strip())}\n")
    fm.append(_list_yaml("links", links))
    fm.append(_list_yaml("pr_commit_links", prs))
    if args.notes.strip():
        fm.append(f"notes: {_yaml_single_quoted(args.notes.strip())}\n")
    fm.append("---\n\n")

    body = []
    body.append("## Message 1 (TLDR)\n\n")
    body.append(tldr + "\n\n")
    body.append("## Message 2 (Shipped + community)\n\n")
    body.append(shipped + "\n")

    text = "".join(fm) + "".join(body)

    if args.dry_run:
        print(f"Would write: {out}\n", file=sys.stderr)
        print(text)
        return 0

    out.write_text(text, encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
