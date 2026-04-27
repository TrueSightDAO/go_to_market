#!/usr/bin/env python3
"""
Draft Beer Hall **Message 1** (TLDR) and **Message 2** (Shipped + Community) by feeding
the output of ``generate_beer_hall_preview.py`` to **Anthropic Claude**.

The Beer Hall WhatsApp send has been retired — digests are **archive-only** artifacts
that feed the static ``beer_hall/feed/`` (read by truesight.me) and ``ADVISORY_SNAPSHOT.md``
(read by the oracle at oracle.truesight.me). This drafter replaces the manual/LLM-in-IDE
summarisation step so the daily GitHub Action can run end-to-end.

Writes three files:

* ``--out-msg1``      — Message 1 (TLDR; no URLs)
* ``--out-msg2``      — Message 2 (``Shipped`` bullets with GitHub URLs + optional Community section)
* ``--out-slug``      — short kebab-case slug for the archive filename

Uses the latest 2 Beer Hall archives under
``../ecosystem_change_logs/beer_hall/entries/beer-hall_*.md`` as few-shot style examples
(auto-picked; override with ``--examples-dir``).

Usage (from ``market_research/``)::

    python3 scripts/draft_beer_hall_digest.py \\
      --preview /tmp/beer_hall_preview.md \\
      --out-msg1 /tmp/msg1.txt \\
      --out-msg2 /tmp/msg2.txt \\
      --out-slug /tmp/slug.txt

Requires ``ANTHROPIC_API_KEY`` in env. Default model is **Claude Sonnet 4.6**
(``claude-sonnet-4-6``); override with ``--model``.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent


def _default_examples_dir() -> Path:
    return _REPO.parent / "ecosystem_change_logs" / "beer_hall" / "entries"


def _recent_examples(examples_dir: Path, limit: int = 2) -> list[str]:
    """Return the body text of the most recent N archive ``.md`` files (frontmatter stripped)."""
    if not examples_dir.is_dir():
        return []
    entries = sorted(examples_dir.glob("beer-hall_*.md"), reverse=True)[:limit]
    out: list[str] = []
    for p in entries:
        raw = p.read_text(encoding="utf-8")
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw.strip(), re.DOTALL)
        body = m.group(2) if m else raw
        out.append(f"--- Example archive: {p.name} ---\n{body.strip()}\n")
    return out


_SYSTEM = """You draft the daily **Beer Hall digest** for the TrueSight DAO — a regenerative cacao supply chain DAO. Your audience is DAO contributors, partners, and non-engineer stakeholders (not only developers). The digest publishes daily; the evidence pack you receive may include up to ~7 days of git activity and ~48 h of Telegram community signal because shipped work doesn't perfectly align to the publish cadence — frame Message 1 as **today's update** and let the bullets speak to whatever genuinely shipped or moved since the previous Beer Hall, not "this week".

Output is consumed by the truesight.me static Beer Hall feed and by the oracle.truesight.me Grok advisor. It is NOT broadcast to WhatsApp.

Style rules:

1. Write plain, concrete prose. No marketing fluff.
2. Lead with user-visible outcomes, not technical internals. "81% bars now live in Oscar + Santa Ana" beats "merged PR #65".
3. Highlight DAO-meaningful shipments only: partner-facing features, sales wiring, contributor tools, blog/narrative, incident response. Drop purely internal chore/docs commits.
4. Every GitHub URL must be under `https://github.com/TrueSightDAO/...`. No personal or KrakeIO repos.
5. Group Community (Telegram) signals under a separate "Community" heading inside Message 2 if present — contributor attributions, contested decisions, field notes.
6. Keep Message 1 ~8–12 bullets. Keep Message 2 focused on meaningful work items (not every single PR) with 1–2 URLs per bullet max.
7. Do **not** add a "retired from WhatsApp" opener or any automation-status preamble. The archive-only framing is documented once in `WORKSPACE_CONTEXT.md` and does not need to be repeated in every digest. Start Message 1 directly with the first bullet.

Output format — return **only** these three sections, in order, with the exact markers shown:

===SLUG===
<kebab-case slug, 3–6 words, capturing today's headline>
===MESSAGE_1===
<opener line + TLDR bullets>
===MESSAGE_2===
Shipped

<bulleted list with GitHub URLs>

Community (Telegram log):

<optional: contributor signals if any in evidence>

No commentary before, between, or after the markers."""


_USER_TEMPLATE = """Here is today's evidence pack from generate_beer_hall_preview.py. Synthesise it into Message 1 + Message 2 per the system rules.

The preview's evidence window (`--since-days`, `--telegram-hours`) is wider than 24 h on purpose — DAO work doesn't perfectly chunk into days. Use the wider window as input but write Message 1 as **today's update**, not "this week" — anchor on what genuinely moved since the previous Beer Hall.

{examples_block}

=== TODAY'S EVIDENCE (preview output) ===

{preview}
"""


def _extract_sections(raw: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current = None
    buf: list[str] = []
    for line in raw.splitlines():
        m = re.match(r"^===(SLUG|MESSAGE_1|MESSAGE_2)===\s*$", line.strip())
        if m:
            if current:
                sections[current] = "\n".join(buf).strip()
            current = m.group(1)
            buf = []
        else:
            if current:
                buf.append(line)
    if current:
        sections[current] = "\n".join(buf).strip()
    return sections


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preview", required=True, type=Path, help="Path to generate_beer_hall_preview.py output.")
    ap.add_argument("--out-msg1", required=True, type=Path)
    ap.add_argument("--out-msg2", required=True, type=Path)
    ap.add_argument("--out-slug", required=True, type=Path)
    ap.add_argument("--examples-dir", type=Path, default=None, help="Beer Hall archive dir for few-shot (default: ../ecosystem_change_logs/beer_hall/entries).")
    ap.add_argument("--examples-count", type=int, default=2)
    ap.add_argument("--model", default="claude-sonnet-4-6", help="Anthropic model id (default claude-sonnet-4-6).")
    ap.add_argument("--max-tokens", type=int, default=4000)
    args = ap.parse_args()

    if "ANTHROPIC_API_KEY" not in os.environ:
        sys.stderr.write("ANTHROPIC_API_KEY not set in environment.\n")
        return 2

    try:
        import anthropic  # type: ignore
    except ImportError:
        sys.stderr.write("The 'anthropic' package is required. Install with: pip install anthropic\n")
        return 2

    preview_text = args.preview.read_text(encoding="utf-8")
    examples_dir = args.examples_dir or _default_examples_dir()
    examples = _recent_examples(examples_dir, limit=args.examples_count)
    examples_block = (
        "For style reference, here are the most recent archived digests:\n\n"
        + "\n".join(examples)
        if examples
        else "(No prior archives available for style reference — follow the system rules.)"
    )

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=args.model,
        max_tokens=args.max_tokens,
        system=_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": _USER_TEMPLATE.format(examples_block=examples_block, preview=preview_text),
            }
        ],
    )
    text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text").strip()
    sections = _extract_sections(text)

    for key in ("SLUG", "MESSAGE_1", "MESSAGE_2"):
        if not sections.get(key):
            sys.stderr.write(f"Model response missing section {key}. Full response:\n{text}\n")
            return 1

    args.out_slug.write_text(sections["SLUG"].strip() + "\n", encoding="utf-8")
    args.out_msg1.write_text(sections["MESSAGE_1"].rstrip() + "\n", encoding="utf-8")
    args.out_msg2.write_text(sections["MESSAGE_2"].rstrip() + "\n", encoding="utf-8")
    print(f"slug:    {sections['SLUG'].strip()}", file=sys.stderr)
    print(f"msg1:    {args.out_msg1} ({len(sections['MESSAGE_1'])} chars)", file=sys.stderr)
    print(f"msg2:    {args.out_msg2} ({len(sections['MESSAGE_2'])} chars)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
