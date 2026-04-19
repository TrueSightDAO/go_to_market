#!/usr/bin/env python3
"""
Generate a **Beer Hall–style preview** (Message 1 + Message 2) for operator review **without**
sending WhatsApp or appending the OpenClaw log sheet.

Follows the same evidence steps as **`agentic_ai_context/OPENCLAW_WHATSAPP.md`**:
  - **§ Gathering what merged** — `git fetch` + `git log` on `origin/<default>` for each clone
  - **Merged PRs** — `gh pr list -R TrueSightDAO/<repo> --state merged` (optional if `gh` missing)
  - **§ Gathering Telegram Chat Logs** — `list_recent_telegram_chat_logs_for_digest.py`
  - **§ DApp Remarks (Hit List)** — `list_recent_dapp_remarks_for_digest.py` (offline / field human notes)

Output is Markdown (for reading in Cursor / Git). Paste into WhatsApp manually if desired;
use WhatsApp formatting rules from **`OPENCLAW_WHATSAPP.md`** (no `**bold**` in the bubble).

Usage (from `market_research/`):
  python3 scripts/generate_beer_hall_preview.py
  python3 scripts/generate_beer_hall_preview.py --since-days 3 --telegram-hours 48
  python3 scripts/generate_beer_hall_preview.py --dapp-include-automation
  python3 scripts/generate_beer_hall_preview.py --output /path/to/preview.md

Default output: **`agentic_ai_context/previews/beer_hall_preview_latest.md`** when that
directory exists next to `market_research/` under the same parent (`Applications/`).

**Console:** The full Markdown is **always printed to stdout** (for terminals and for agents
capturing command output). A one-line **“Written to: …”** message goes to **stderr** so
`> file.md` still captures only the digest.
"""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent


def _default_output_path() -> Path:
    cand = _REPO.parent / "agentic_ai_context" / "previews" / "beer_hall_preview_latest.md"
    cand.parent.mkdir(parents=True, exist_ok=True)
    return cand


# Local clone folder name under the parent of `market_research` (usually ~/Applications)
# and matching GitHub repo slug for `gh pr list -R TrueSightDAO/<slug>`.
REPOS: list[tuple[str, str]] = [
    ("truesight_me", "truesight_me_beta"),
    ("market_research", "go_to_market"),
    ("agentic_ai_context", "agentic_ai_context"),
    ("tokenomics", "tokenomics"),
    ("dapp", "dapp"),
    ("TrueChain", "TrueChain"),
    ("qr_codes", "qr_codes"),
    ("proposals", "proposals"),
    ("agroverse-inventory", "agroverse-inventory"),
    ("agroverse_shop", "agroverse_shop_beta"),
    ("iching_oracle", "oracle"),
    ("Cypher-Defense", "Cypher-Defense"),
]


def _run(cmd: list[str], *, cwd: Path | None = None) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out


def _parent_apps() -> Path:
    return _REPO.parent


def _git_default_branch(repo: Path) -> str:
    code, out = _run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
        cwd=repo,
    )
    if code == 0 and out.strip():
        return out.strip().split("/")[-1]
    for cand in ("main", "master"):
        if (repo / ".git" / "refs" / "remotes" / "origin" / cand).exists() or code == 0:
            code2, _ = _run(["git", "rev-parse", "--verify", f"origin/{cand}"], cwd=repo)
            if code2 == 0:
                return cand
    return "main"


def _git_log_since(repo: Path, since_iso: str, until_iso: str) -> str:
    br = _git_default_branch(repo)
    _run(["git", "fetch", "origin"], cwd=repo)
    code, out = _run(
        [
            "git",
            "log",
            f"origin/{br}",
            f"--since={since_iso}",
            f"--until={until_iso}",
            "--pretty=format:%h | %ci | %s",
        ],
        cwd=repo,
    )
    if code != 0:
        return f"(git log failed in {repo.name})\n"
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    if not lines:
        return f"_(no commits on origin/{br} in window)_\n"
    body = "\n".join(lines[:25])
    if len(lines) > 25:
        body += "\n… (truncated)"
    return body + "\n"


def _gh_merged(since_date: str, slug: str) -> str:
    code, out = _run(
        [
            "gh",
            "pr",
            "list",
            "-R",
            f"TrueSightDAO/{slug}",
            "--state",
            "merged",
            "-L",
            "30",
            "--json",
            "number,title,mergedAt,url",
        ]
    )
    if code != 0:
        return ""
    try:
        import json

        rows = json.loads(out or "[]")
    except Exception:
        return ""
    picked: list[str] = []
    for r in rows:
        ma = (r.get("mergedAt") or "")[:10]
        if ma >= since_date:
            picked.append(
                f"- PR #{r.get('number')}: {r.get('title')} — {r.get('url')} _(merged {ma})_"
            )
    return "\n".join(picked[:20]) + ("\n" if picked else "")


def _telegram_block(hours: int) -> str:
    script = _REPO / "scripts" / "list_recent_telegram_chat_logs_for_digest.py"
    if not script.is_file():
        return "_(telegram helper script missing)_\n"
    code, out = _run([sys.executable, str(script), "--hours", str(hours)], cwd=_REPO)
    if code != 0:
        return f"_(telegram helper exit {code})_\n```\n{out[:4000]}\n```\n"
    return "```\n" + out.strip() + "\n```\n"


def _dapp_remarks_block(hours: int, *, include_automation: bool) -> str:
    script = _REPO / "scripts" / "list_recent_dapp_remarks_for_digest.py"
    if not script.is_file():
        return "_(DApp Remarks helper script missing)_\n"
    cmd = [sys.executable, str(script), "--hours", str(float(hours))]
    if include_automation:
        cmd.append("--include-automation")
    code, out = _run(cmd, cwd=_REPO)
    if code != 0:
        return f"_(DApp Remarks helper exit {code})_\n```\n{out[:4000]}\n```\n"
    return "```\n" + out.strip() + "\n```\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Beer Hall digest preview (no WhatsApp send).")
    ap.add_argument("--since-days", type=int, default=7, help="Look-back for git log / gh (calendar days).")
    ap.add_argument("--telegram-hours", type=int, default=48, help="Passed to list_recent_telegram_chat_logs_for_digest.py.")
    ap.add_argument(
        "--dapp-include-automation",
        action="store_true",
        help="Pass --include-automation to list_recent_dapp_remarks_for_digest.py (default: human-oriented rows only).",
    )
    ap.add_argument("--output", type=Path, default=None, help="Markdown output path.")
    ap.add_argument(
        "--no-stdout",
        action="store_true",
        help="Do not print the full Markdown to stdout (file write only). Default is to always print.",
    )
    args = ap.parse_args()

    out_path = Path(args.output) if args.output else _default_output_path()
    apps = _parent_apps()
    today = dt.datetime.now(dt.timezone.utc).date()
    since_d = today - dt.timedelta(days=max(1, args.since_days))
    since_iso = f"{since_d.isoformat()} 00:00:00"
    until_iso = f"{(today + dt.timedelta(days=1)).isoformat()} 00:00:00"

    parts: list[str] = []
    parts.append(f"# Beer Hall digest — **PREVIEW** (no OpenClaw send)\n")
    parts.append(f"- Generated: **{dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}**\n")
    parts.append(f"- Git window: `{since_iso}` → `{until_iso}` (local clone `origin` default branch)\n")
    parts.append(
        f"- Telegram + DApp Remarks helper look-back: **{args.telegram_hours}h** "
        f"(same window for both; DApp default excludes script submitters unless "
        f"`--dapp-include-automation`)\n"
    )
    parts.append("\n---\n\n## Message 1 (TLDR only — WhatsApp paste)\n\n")
    parts.append(
        "_Draft manually from the evidence below. No GitHub URLs in Message 1. "
        "Opener line (required when posting for real):_\n\n"
        "*OpenClaw × Cursor — daily state of the DAO (not a manual post from Gary)*\n\n"
        "_TLDR bullets (plain language, DAO-relevant):_\n\n"
        "- …\n"
    )
    parts.append("\n---\n\n## Message 2 (Shipped + links — WhatsApp paste)\n\n")
    parts.append(
        "_Use `*Shipped*` then bullets. **Only** `https://github.com/TrueSightDAO/...` for GitHub. "
        "Optional: **Community (Telegram log):** and/or **Community (DApp Remarks / field):** after bullets._\n\n"
        "*Shipped*\n\n"
        "- …\n"
    )
    parts.append("\n---\n\n## Evidence — `git log` by repo\n\n")
    for dirname, slug in REPOS:
        repo = apps / dirname
        if not (repo / ".git").is_dir():
            parts.append(f"### `{dirname}` _(no clone at {repo})_\n\n")
            continue
        url = ""
        try:
            code, u = _run(["git", "remote", "get-url", "origin"], cwd=repo)
            if code == 0:
                url = u.strip()
        except Exception:
            url = ""
        if "TrueSightDAO" not in url and "truesightdao" not in url.lower():
            parts.append(f"### `{dirname}` _(skipped — origin not TrueSightDAO: `{url}`)_\n\n")
            continue
        parts.append(f"### `{dirname}` → `{slug}`\n\n")
        parts.append("```\n")
        parts.append(_git_log_since(repo, since_iso, until_iso))
        parts.append("```\n\n")

    parts.append("---\n\n## Evidence — merged PRs (`gh`)\n\n")
    parts.append("_If `gh` is missing or unauthorized, this section may be empty._\n\n")
    for dirname, slug in REPOS:
        repo = apps / dirname
        if not (repo / ".git").is_dir():
            continue
        code, u = _run(["git", "remote", "get-url", "origin"], cwd=repo)
        if code != 0 or ("TrueSightDAO" not in u and "truesightdao" not in u.lower()):
            continue
        block = _gh_merged(since_d.isoformat(), slug)
        if not block.strip():
            continue
        parts.append(f"### TrueSightDAO/{slug}\n\n")
        parts.append(block + "\n")

    parts.append("---\n\n## Evidence — Telegram Chat Logs helper output\n\n")
    parts.append(_telegram_block(args.telegram_hours))

    parts.append("---\n\n## Evidence — DApp Remarks (Hit List) helper output\n\n")
    parts.append(_dapp_remarks_block(args.telegram_hours, include_automation=args.dapp_include_automation))

    parts.append(
        "\n---\n\n## Operator checklist for this Beer Hall digest\n\n"
        "WhatsApp posting via OpenClaw has been retired. This digest is now an archive-only\n"
        "artifact: it goes to the static feed (`beer_hall/entries/`) and feeds Grok context\n"
        "via the advisory snapshot, but is **not** broadcast to The Beer Hall WhatsApp group.\n\n"
        "1. Edit **Message 1** / **Message 2** above into plain-language digest text.\n"
        "2. Archive to `ecosystem_change_logs/beer_hall/entries/` via\n"
        "   `ecosystem_change_logs/scripts/archive_beer_hall_changelog.py`.\n"
        "3. Refresh advisory snapshot so Grok sees it:\n"
        "   `python3 scripts/generate_advisory_snapshot.py --git-publish`\n"
        "   (add `--with-rem` when running end-of-day locally).\n"
    )

    text = "".join(parts)
    out_path.write_text(text, encoding="utf-8")
    print(f"Written to: {out_path}\n", file=sys.stderr, flush=True)
    if not args.no_stdout:
        print(text, end="", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
