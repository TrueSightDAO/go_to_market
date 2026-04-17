#!/usr/bin/env python3
"""
Compile **ADVISORY_SNAPSHOT.md** (LLM-oriented DAO state) from real workspace sources.

Writes:
  - ``../agentic_ai_context/ADVISORY_SNAPSHOT.md`` (working copy for Cursor)
  - ``../ecosystem_change_logs/advisory/snapshots/<UTC-date>.md`` (dated archive)
  - ``../ecosystem_change_logs/advisory/index.json`` (manifest for raw-GitHub navigation)

Optional git (opt-in):
  --git-commit   commit only the generated paths in each repo (fails if nothing staged)
  --git-push     push ``origin`` default branch after commit (both repos)

Usage (from ``market_research/``)::

  python3 scripts/generate_advisory_snapshot.py
  python3 scripts/generate_advisory_snapshot.py --since-days 7 --with-sheet-sales
  python3 scripts/generate_advisory_snapshot.py --since-days 7 --git-commit --git-push

No secrets are embedded in the repo. Telegram/DApp helpers are **not** included by default
(use Beer Hall preview for those). Optional **`--with-sheet-sales`** (local only) appends
rollup **`Monthly Statistics`** plus recent **`QR Code Sales`** rows from the canonical
workbooks documented in **`tokenomics/SCHEMA.md`** (requires `market_research/google_credentials.json`).
Default output remains git + context files + Beer Hall archives + notes mtime.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

# Same curated table as ``generate_beer_hall_preview.py`` (local dir, GitHub slug).
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
    ("iching_oracle", "iching_oracle"),
]

# Heuristic: CONTEXT_UPDATES lines mentioning these names (case-insensitive).
ADVISORY_NAMES = (
    "matheus",
    "jedielcio",
    "kirsten",
    "nima",
    "fatima",
)

ADVISORY_KEYWORDS = (
    "waiting",
    "pending",
    "blocked",
    "sent",
    "received",
    "confirmed",
)

# PROJECT_INDEX “pipelines” → local clone dirname under Applications/ (must exist to compare git).
PIPELINE_TO_REPO: dict[str, str] = {
    "go_to_market": "market_research",
    "openclaw": "agentic_ai_context",
    "TrueChain": "TrueChain",
    "oracle": "iching_oracle",
}


def _run(cmd: list[str], *, cwd: Path | None = None) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out


def _parent_apps() -> Path:
    return _REPO.parent


def _git_default_branch(repo: Path) -> str:
    code, out = _run(["git", "symbolic-ref", "refs/remotes/origin/HEAD"], cwd=repo)
    if code == 0 and out.strip():
        return out.strip().split("/")[-1]
    for cand in ("main", "master"):
        code2, _ = _run(["git", "rev-parse", "--verify", f"origin/{cand}"], cwd=repo)
        if code2 == 0:
            return cand
    return "main"


def _git_log_since(repo: Path, since_iso: str, until_iso: str) -> tuple[str, int]:
    """Returns (log text, commit count in window)."""
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
        return f"(git log failed in {repo.name})\n", 0
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    if not lines:
        return f"_(no commits on origin/{br} in window)_\n", 0
    body = "\n".join(lines[:40])
    if len(lines) > 40:
        body += "\n… (truncated)"
    return body + "\n", len(lines)


def _is_truesightdao_clone(repo: Path) -> bool:
    if not (repo / ".git").is_dir():
        return False
    code, u = _run(["git", "remote", "get-url", "origin"], cwd=repo)
    if code != 0:
        return False
    return "truesightdao" in u.lower()


def _parse_context_updates(path: Path, since_d: dt.date) -> tuple[list[str], list[str]]:
    """Return (recent lines, highlighted heuristic lines)."""
    if not path.is_file():
        return [], []
    recent: list[str] = []
    highlights: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or s.startswith("---"):
            continue
        m = re.match(r"^(\d{4}-\d{2}-\d{2})\s*\|\s*", s)
        if not m:
            continue
        try:
            line_d = dt.date.fromisoformat(m.group(1))
        except ValueError:
            continue
        if line_d < since_d:
            continue
        recent.append(s)
        low = s.lower()
        if any(n in low for n in ADVISORY_NAMES) or any(k in low for k in ADVISORY_KEYWORDS):
            highlights.append(s)
    return recent, highlights


def _parse_frontmatter_body(md: str) -> tuple[dict[str, str], str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", md.strip(), re.DOTALL)
    if not m:
        return {}, md
    fm_raw, body = m.group(1), m.group(2)
    meta: dict[str, str] = {}
    for line in fm_raw.splitlines():
        if ":" not in line or line.strip().startswith("#"):
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip().strip("'\"")
        meta[k.strip()] = v
    return meta, body


def _beer_hall_excerpts(ecosystem_repo: Path, n: int = 3) -> list[dict[str, str]]:
    entries_dir = ecosystem_repo / "beer_hall" / "entries"
    if not entries_dir.is_dir():
        return []
    md_files = sorted(entries_dir.glob("beer-hall_*.md"), key=lambda p: p.name, reverse=True)[:n]
    out: list[dict[str, str]] = []
    for p in md_files:
        meta, body = _parse_frontmatter_body(p.read_text(encoding="utf-8"))
        m1_idx = body.find("## Message 1")
        m2_idx = body.find("## Message 2")
        chunk = body
        if m1_idx != -1 and m2_idx != -1 and m2_idx > m1_idx:
            chunk = body[m1_idx:m2_idx]
        chunk = re.sub(r"^## Message 1.*?\n+", "", chunk, flags=re.DOTALL).strip()
        first_lines = "\n".join([ln for ln in chunk.splitlines() if ln.strip()][:2])
        out.append(
            {
                "file": str(p.name),
                "id": meta.get("id", ""),
                "posted_at_utc": meta.get("posted_at_utc", ""),
                "slug": meta.get("slug", ""),
                "excerpt": first_lines or "_(empty)_",
            }
        )
    return out


def _notes_recent(ctx_root: Path, since_ts: float) -> list[str]:
    notes = ctx_root / "notes"
    if not notes.is_dir():
        return []
    found: list[str] = []
    for p in list(notes.rglob("*.md")) + list(notes.rglob("*.txt")):
        if p.name.startswith("."):
            continue
        try:
            if p.stat().st_mtime >= since_ts:
                found.append(str(p.relative_to(ctx_root)))
        except OSError:
            continue
    return sorted(found)


# Main ledger + Telegram/Submissions workbooks — see tokenomics/SCHEMA.md
_MAIN_LEDGER_SPREADSHEET_ID = "1GE7PUq-UT6x2rBN-Q2ksogbWpgyuh2SaxJyG_uEK6PU"
_TELEGRAM_SUBMISSIONS_SPREADSHEET_ID = "1qbZZhf-_7xzmDTriaJVWj6OZshyQsFkdsAV8-pyzASQ"
_MONTHLY_STATISTICS_WS = "Monthly Statistics"
_QR_CODE_SALES_WS = "QR Code Sales"
_SHEETS_SCOPES = (
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
)


def _norm_header_cell(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _header_col_map(header: list[str]) -> dict[str, int]:
    m: dict[str, int] = {}
    for j, raw in enumerate(header):
        k = _norm_header_cell(raw)
        if k and k not in m:
            m[k] = j
    return m


def _find_header_col(m: dict[str, int], *want: str) -> int | None:
    for w in want:
        ww = _norm_header_cell(w)
        if ww in m:
            return m[ww]
    for w in want:
        ww = _norm_header_cell(w)
        for k, j in m.items():
            if ww == k or ww in k or k in ww:
                return j
    return None


def _parse_cell_to_date(raw: str) -> dt.date | None:
    t = (raw or "").strip()
    if not t:
        return None
    if re.fullmatch(r"\d{8}", t):
        try:
            return dt.datetime.strptime(t, "%Y%m%d").date()
        except ValueError:
            return None
    for fmt, n in (("%Y-%m-%d", 10), ("%m/%d/%Y", 10)):
        try:
            return dt.datetime.strptime(t[:n], fmt).date()
        except ValueError:
            continue
    if len(t) >= 19:
        try:
            return dt.datetime.strptime(t[:19], "%Y-%m-%d %H:%M:%S").date()
        except ValueError:
            pass
    if "T" in t:
        try:
            return dt.datetime.fromisoformat(t.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


def _md_cell(val: object, *, max_len: int = 120) -> str:
    s = re.sub(r"[\r\n]+", " ", str(val if val is not None else "")).strip()
    s = s.replace("|", "\\|")
    if len(s) > max_len:
        s = s[: max_len - 1] + "…"
    return s or "—"


def _fetch_sheet_sales_markdown(
    repo_root: Path,
    since_d: dt.date,
    *,
    months_tail: int,
    qr_row_limit: int,
    qr_scan_depth: int,
) -> str:
    """Build markdown for LLM-oriented sales evidence; never raises (skip text on failure)."""
    cred_path = repo_root / "google_credentials.json"
    if not cred_path.is_file():
        return (
            "---\n\n## Sheet evidence (sales)\n\n"
            f"_(Skipped: missing service account file `{cred_path.name}` under `market_research/`.)_\n\n"
        )
    try:
        import gspread
        from google.oauth2.service_account import Credentials as SACredentials
    except ImportError as e:
        return (
            "---\n\n## Sheet evidence (sales)\n\n"
            f"_(Skipped: import error — install deps from `market_research/requirements.txt`: `{e}`.)_\n\n"
        )

    parts: list[str] = []
    parts.append("---\n\n## Sheet evidence (sales)\n\n")
    parts.append(
        "_Canonical layouts: `tokenomics/SCHEMA.md` — **Monthly Statistics** on the main ledger; "
        "**QR Code Sales** on Telegram & Submissions. Figures are copied as-is from Sheets; "
        "verify before financial decisions._\n\n"
    )

    try:
        creds = SACredentials.from_service_account_file(str(cred_path), scopes=_SHEETS_SCOPES)
        gc = gspread.authorize(creds)
    except Exception as e:
        parts.append(f"_(Skipped: could not authorize Google client: `{e}`.)_\n\n")
        return "".join(parts)

    # --- Monthly Statistics (rollup) ---
    try:
        sh_main = gc.open_by_key(_MAIN_LEDGER_SPREADSHEET_ID)
        ws_ms = sh_main.worksheet(_MONTHLY_STATISTICS_WS)
        rows_ms = ws_ms.get_all_values()
    except Exception as e:
        parts.append(f"### `{_MONTHLY_STATISTICS_WS}` _(read failed: {e})_\n\n")
        rows_ms = []

    if rows_ms and len(rows_ms) >= 2:
        hdr = rows_ms[0]
        cmap = _header_col_map(hdr)
        i_ym = _find_header_col(cmap, "year-month", "year month")
        i_vol = _find_header_col(cmap, "monthly sales volume", "monthly sales")
        i_cum = _find_header_col(cmap, "cumulative sales volume", "cumulative sales")
        i_upd = _find_header_col(cmap, "last updated", "updated")
        if i_ym is None or i_vol is None:
            parts.append(
                f"### `{_MONTHLY_STATISTICS_WS}`\n\n"
                f"_(Could not map expected headers; first row: `{_md_cell(', '.join(hdr[:8]), max_len=200)}`.)_\n\n"
            )
        else:
            data = [r for r in rows_ms[1:] if any((c or "").strip() for c in r)]
            tail = data[-max(1, months_tail) :] if months_tail > 0 else data
            parts.append(f"### `{_MONTHLY_STATISTICS_WS}` (last **{len(tail)}** non-empty rows)\n\n")
            parts.append("| Year-Month | Monthly USD | Cumulative USD | Last updated |\n")
            parts.append("|------------|-------------|------------------|---------------|\n")
            mx = max(i_ym, i_vol, i_cum or 0, i_upd or 0)
            for r in tail:
                while len(r) <= mx:
                    r.append("")
                ym = _md_cell(r[i_ym] if i_ym < len(r) else "", max_len=24)
                vol = _md_cell(r[i_vol] if i_vol < len(r) else "", max_len=24)
                cum = _md_cell(r[i_cum] if i_cum is not None and i_cum < len(r) else "", max_len=24)
                upd = _md_cell(r[i_upd] if i_upd is not None and i_upd < len(r) else "", max_len=32)
                parts.append(f"| {ym} | {vol} | {cum} | {upd} |\n")
            parts.append("\n")

    # --- QR Code Sales (line-level, window by Sales Date) ---
    try:
        sh_q = gc.open_by_key(_TELEGRAM_SUBMISSIONS_SPREADSHEET_ID)
        ws_qr = sh_q.worksheet(_QR_CODE_SALES_WS)
        rows_q = ws_qr.get_all_values()
    except Exception as e:
        parts.append(f"### `{_QR_CODE_SALES_WS}` _(read failed: {e})_\n\n")
        return "".join(parts)

    if len(rows_q) < 2:
        parts.append(f"### `{_QR_CODE_SALES_WS}`\n\n_(No data rows.)_\n\n")
        return "".join(parts)

    hdr_q = rows_q[0]
    cmq = _header_col_map(hdr_q)
    i_sd = _find_header_col(cmq, "sales date", "status date")
    i_price = _find_header_col(cmq, "sale price", "price")
    i_cur = _find_header_col(cmq, "currency")
    i_stat = _find_header_col(cmq, "status")
    i_qr = _find_header_col(cmq, "qr code value", "qr code")
    i_rem = _find_header_col(cmq, "remarks", "remark")
    i_stripe = _find_header_col(cmq, "stripe session id", "stripe session")

    if i_sd is None:
        parts.append(
            f"### `{_QR_CODE_SALES_WS}`\n\n"
            f"_(Could not find Sales Date column; headers: `{_md_cell(', '.join(hdr_q[:14]), max_len=220)}`.)_\n\n"
        )
        return "".join(parts)

    need_idx = [i for i in (i_sd, i_price, i_cur, i_stat, i_qr, i_rem, i_stripe) if i is not None]
    max_i = max(need_idx) if need_idx else i_sd
    data_q = rows_q[1:]
    scan = data_q[-max(qr_scan_depth, 1) :] if qr_scan_depth > 0 else data_q

    picked: list[tuple[dt.date, list[str]]] = []
    for r in reversed(scan):
        while len(r) <= max_i:
            r.append("")
        d = _parse_cell_to_date(r[i_sd] if i_sd < len(r) else "")
        if d is None or d < since_d:
            continue
        picked.append((d, r))
        if len(picked) >= qr_row_limit:
            break

    picked.sort(key=lambda t: t[0])
    parts.append(
        f"### `{_QR_CODE_SALES_WS}` (up to **{qr_row_limit}** rows; "
        f"`Sales Date` ≥ `{since_d.isoformat()}`; scanned last **{len(scan)}** data rows)\n\n"
    )
    parts.append(
        "| Sales date | Price | Currency / product | Status | QR (trunc.) | Stripe (suffix) | Remarks (trunc.) |\n"
        "|-------------|-------|--------------------|--------|-------------|-------------------|--------------------|\n"
    )
    if not picked:
        parts.append(
            f"| — | — | — | — | — | — | _No rows in scan window (try larger `--sheet-sales-qr-scan` or `--since-days`)._ |\n"
        )
    else:
        for d, r in picked:
            price = _md_cell(r[i_price] if i_price is not None and i_price < len(r) else "", max_len=16)
            cur = _md_cell(r[i_cur] if i_cur is not None and i_cur < len(r) else "", max_len=40)
            stat = _md_cell(r[i_stat] if i_stat is not None and i_stat < len(r) else "", max_len=20)
            qr_raw = r[i_qr] if i_qr is not None and i_qr < len(r) else ""
            qr = _md_cell(qr_raw, max_len=28)
            stripe_raw = (r[i_stripe] if i_stripe is not None and i_stripe < len(r) else "").strip()
            stripe_sfx = _md_cell(stripe_raw[-12:] if len(stripe_raw) > 12 else stripe_raw, max_len=14)
            rem = _md_cell(r[i_rem] if i_rem is not None and i_rem < len(r) else "", max_len=72)
            parts.append(f"| {d.isoformat()} | {price} | {cur} | {stat} | {qr} | {stripe_sfx} | {rem} |\n")
    parts.append(
        "\n_Source IDs: main ledger `"
        + _MAIN_LEDGER_SPREADSHEET_ID
        + "`, submissions `"
        + _TELEGRAM_SUBMISSIONS_SPREADSHEET_ID
        + "`._\n\n"
    )
    return "".join(parts)


def _pipeline_activity(apps: Path, since_iso: str, until_iso: str) -> list[tuple[str, str, bool]]:
    """(pipeline, mapped_repo, had_activity)."""
    rows: list[tuple[str, str, bool]] = []
    for pipe, dirname in PIPELINE_TO_REPO.items():
        repo = apps / dirname
        active = False
        if _is_truesightdao_clone(repo):
            _, count = _git_log_since(repo, since_iso, until_iso)
            active = count > 0
        rows.append((pipe, dirname, active))
    return rows


def _build_markdown(
    *,
    since_days: int,
    since_d: dt.date,
    since_iso: str,
    until_iso: str,
    apps: Path,
    ctx_root: Path,
    eco_repo: Path,
    sheet_sales_md: str = "",
) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    parts: list[str] = []
    parts.append("# ADVISORY_SNAPSHOT\n\n")
    parts.append("Machine-oriented digest of **recent evidence** for LLM advisors. ")
    parts.append("Git lines are **proxies** for shipped work, not verified outcomes.\n\n")
    parts.append("---\n\n## Meta\n\n")
    parts.append(f"- Generated (UTC): `{now.strftime('%Y-%m-%dT%H:%M:%SZ')}`\n")
    parts.append(f"- Look-back: **{since_days}** calendar days (`{since_d.isoformat()}` → today UTC)\n")
    parts.append(f"- Curated clone set: **{len(REPOS)}** repos (same table as Beer Hall preview)\n\n")

    parts.append("---\n\n## CONTEXT_UPDATES (append-only, heuristic highlights)\n\n")
    cu = ctx_root / "CONTEXT_UPDATES.md"
    recent, highlights = _parse_context_updates(cu, since_d)
    if highlights:
        parts.append("_Lines in window matching configured names or status keywords:_\n\n")
        for ln in highlights[-40:]:
            parts.append(f"- {ln}\n")
        parts.append("\n")
    else:
        parts.append("_No lines matched name/keyword heuristics in this window._\n\n")
    if recent:
        parts.append(f"_All dated lines on/after {since_d.isoformat()}_ ({len(recent)}):\n\n")
        for ln in recent[-60:]:
            parts.append(f"- {ln}\n")
        parts.append("\n")
    else:
        parts.append(f"_(No `YYYY-MM-DD |` lines on/after {since_d.isoformat()} in CONTEXT_UPDATES.md.)_\n\n")

    parts.append("---\n\n## Pipeline activity map (PROJECT_INDEX ↔ git)\n\n")
    parts.append("| Pipeline | Mapped clone | Activity in window |\n")
    parts.append("|----------|----------------|----------------------|\n")
    for pipe, dirname, active in _pipeline_activity(apps, since_iso, until_iso):
        parts.append(f"| `{pipe}` | `{dirname}` | **{'yes' if active else 'no'}** |\n")
    parts.append("\n")

    parts.append("---\n\n## Git log by repo (origin default branch)\n\n")
    for dirname, slug in REPOS:
        repo = apps / dirname
        if not (repo / ".git").is_dir():
            parts.append(f"### `{dirname}` _(no clone)_\n\n")
            continue
        if not _is_truesightdao_clone(repo):
            code, u = _run(["git", "remote", "get-url", "origin"], cwd=repo)
            url = u.strip() if code == 0 else ""
            parts.append(f"### `{dirname}` _(skipped — origin not TrueSightDAO: `{url}`)_\n\n")
            continue
        parts.append(f"### `{dirname}` → `{slug}`\n\n```\n")
        log, _ = _git_log_since(repo, since_iso, until_iso)
        parts.append(log)
        parts.append("```\n\n")

    parts.append("---\n\n## Recent Beer Hall archives (newest entries)\n\n")
    excerpts = _beer_hall_excerpts(eco_repo, n=3)
    if not excerpts:
        parts.append("_(No `beer_hall/entries/beer-hall_*.md` found under ecosystem_change_logs clone.)_\n\n")
    else:
        for ex in excerpts:
            parts.append(f"### `{ex['file']}`\n\n")
            parts.append(f"- **posted_at_utc:** `{ex['posted_at_utc']}`  \n")
            parts.append(f"- **slug:** `{ex['slug']}`  \n")
            parts.append(f"- **Message 1 excerpt (first two non-empty lines):**\n\n")
            for line in ex["excerpt"].splitlines():
                parts.append(f"  {line}\n")
            parts.append("\n")

    if sheet_sales_md:
        parts.append(sheet_sales_md)

    parts.append("---\n\n## Recent agent notes (`agentic_ai_context/notes/`)\n\n")
    since_ts = dt.datetime.combine(since_d, dt.time.min, tzinfo=dt.timezone.utc).timestamp()
    note_paths = _notes_recent(ctx_root, since_ts)
    if not note_paths:
        parts.append("_No `.md` / `.txt` under `notes/` modified in this window._\n\n")
    else:
        for rel in note_paths:
            parts.append(f"- `{rel}`\n")
        parts.append("\n")

    parts.append("---\n\n## Pointers\n\n")
    parts.append(
        "- **Stable orientation:** `ecosystem_change_logs/advisory/BASE.md` (also linked from `advisory/index.json`).\n"
    )
    parts.append(
        "- Dated snapshots + manifest: "
        "[`TrueSightDAO/ecosystem_change_logs`](https://github.com/TrueSightDAO/ecosystem_change_logs) "
        "`advisory/`\n"
    )
    parts.append("- Human / WhatsApp evidence pack: `market_research/scripts/generate_beer_hall_preview.py`\n")
    parts.append("- Sheet layouts / tabs: `tokenomics/SCHEMA.md`\n")

    return "".join(parts)


def _canonical_context_urls() -> list[str]:
    """Stable raw-GitHub URLs for LLM retrieval (agentic_ai_context main)."""
    base = "https://raw.githubusercontent.com/TrueSightDAO/agentic_ai_context/main"
    return [
        f"{base}/WORKSPACE_CONTEXT.md",
        f"{base}/PROJECT_INDEX.md",
        f"{base}/OPENCLAW_WHATSAPP.md",
        f"{base}/GOVERNANCE_SOURCES.md",
        f"{base}/LEDGER_CONVERSION_AND_REPACKAGING.md",
        f"{base}/CONTEXT_UPDATES.md",
    ]


def _write_index_json(advisory_dir: Path, date_str: str, summary: str) -> None:
    snap_dir = advisory_dir / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, object]] = []
    for p in sorted(snap_dir.glob("*.md"), key=lambda x: x.name, reverse=True):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}\.md", p.name):
            continue
        d = p.stem
        text = p.read_text(encoding="utf-8", errors="replace")
        one = re.sub(r"\s+", " ", text.strip())
        summ = one[:200] + ("…" if len(one) > 200 else "")
        entries.append(
            {
                "date": d,
                "markdown": f"advisory/snapshots/{p.name}",
                "summary": summ,
            }
        )
    read_order = ["advisory/BASE.md", "advisory/index.json"]
    if entries:
        read_order.append(str(entries[0]["markdown"]))
    doc: dict[str, object] = {
        "schema_version": 2,
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "latest_date": date_str,
        "base_markdown": "advisory/BASE.md",
        "read_order": read_order,
        "canonical_context_urls": _canonical_context_urls(),
        "snapshots": entries,
    }
    (advisory_dir / "index.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _git_commit_paths(repo: Path, paths: list[str], message: str) -> bool:
    """Stage paths and commit. Returns True if a commit was created."""
    for rel in paths:
        code, out = _run(["git", "add", "--", rel], cwd=repo)
        if code != 0:
            raise SystemExit(f"git add failed in {repo}: {out}")
    code, st = _run(["git", "status", "--porcelain"], cwd=repo)
    if code != 0:
        raise SystemExit(f"git status failed in {repo}: {st}")
    if not st.strip():
        print(f"(skip commit: nothing to commit in {repo})", file=sys.stderr)
        return False
    code, out = _run(["git", "commit", "-m", message], cwd=repo)
    if code != 0:
        raise SystemExit(f"git commit failed in {repo}: {out}")
    print(f"Committed in {repo}: {message}", file=sys.stderr)
    return True


def _git_push_repo(repo: Path) -> None:
    code, out = _run(["git", "push", "origin", "HEAD"], cwd=repo)
    if code != 0:
        raise SystemExit(f"git push failed in {repo}: {out}")
    print(f"Pushed {repo}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since-days", type=int, default=7, help="Calendar-day look-back (default 7).")
    ap.add_argument(
        "--no-stdout",
        action="store_true",
        help="Do not print the full Markdown to stdout (stderr status only).",
    )
    ap.add_argument(
        "--git-commit",
        action="store_true",
        help="Run git commit in agentic_ai_context and ecosystem_change_logs for generated paths only.",
    )
    ap.add_argument(
        "--git-push",
        action="store_true",
        help="After a successful commit, git push origin HEAD (requires --git-commit).",
    )
    ap.add_argument(
        "--with-sheet-sales",
        action="store_true",
        help=(
            "Append **Monthly Statistics** + recent **QR Code Sales** tables from Google Sheets "
            "(needs market_research/google_credentials.json; see tokenomics/SCHEMA.md)."
        ),
    )
    ap.add_argument(
        "--sheet-sales-months",
        type=int,
        default=14,
        help="With --with-sheet-sales: trailing non-empty rows to show from Monthly Statistics (default 14).",
    )
    ap.add_argument(
        "--sheet-sales-qr-rows",
        type=int,
        default=25,
        help="With --with-sheet-sales: max QR Code Sales rows in the look-back window (default 25).",
    )
    ap.add_argument(
        "--sheet-sales-qr-scan",
        type=int,
        default=600,
        help="With --with-sheet-sales: scan the last N data rows from the bottom of QR Code Sales (default 600).",
    )
    args = ap.parse_args()

    if args.git_push and not args.git_commit:
        ap.error("--git-push requires --git-commit")

    apps = _parent_apps()
    ctx_root = apps / "agentic_ai_context"
    eco_repo = apps / "ecosystem_change_logs"

    today = dt.datetime.now(dt.timezone.utc).date()
    since_d = today - dt.timedelta(days=max(1, args.since_days))
    since_iso = f"{since_d.isoformat()} 00:00:00"
    until_iso = f"{(today + dt.timedelta(days=1)).isoformat()} 00:00:00"

    sheet_sales_md = ""
    if args.with_sheet_sales:
        sheet_sales_md = _fetch_sheet_sales_markdown(
            _REPO,
            since_d,
            months_tail=max(1, args.sheet_sales_months),
            qr_row_limit=max(1, args.sheet_sales_qr_rows),
            qr_scan_depth=max(50, args.sheet_sales_qr_scan),
        )

    text = _build_markdown(
        since_days=args.since_days,
        since_d=since_d,
        since_iso=since_iso,
        until_iso=until_iso,
        apps=apps,
        ctx_root=ctx_root,
        eco_repo=eco_repo,
        sheet_sales_md=sheet_sales_md,
    )

    snap_path_ctx = ctx_root / "ADVISORY_SNAPSHOT.md"
    snap_path_ctx.parent.mkdir(parents=True, exist_ok=True)
    snap_path_ctx.write_text(text, encoding="utf-8")

    advisory_dir = eco_repo / "advisory"
    advisory_dir.mkdir(parents=True, exist_ok=True)
    date_str = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    snap_file = advisory_dir / "snapshots" / f"{date_str}.md"
    snap_file.parent.mkdir(parents=True, exist_ok=True)
    snap_file.write_text(text, encoding="utf-8")

    one = re.sub(r"\s+", " ", text.strip())
    summary = one[:220] + ("…" if len(one) > 220 else "")
    _write_index_json(advisory_dir, date_str, summary)

    readme = advisory_dir / "README.md"
    readme_body = (
        "# Advisory corpus (LLMs)\n\n"
        "**Read `BASE.md` first** — stable DAO orientation, ledger map, and canonical URLs. "
        "Then open `index.json` and the latest dated file under `snapshots/`.\n\n"
        "Daily evidence digests are generated by "
        "`market_research/scripts/generate_advisory_snapshot.py` "
        "(git + `CONTEXT_UPDATES` + Beer Hall excerpts; optional `--with-sheet-sales`).\n\n"
        "- `BASE.md` — slow-changing strategic context (not regenerated by the snapshot script).\n"
        "- `snapshots/YYYY-MM-DD.md` — one file per UTC day (last write wins if re-run same day).\n"
        "- `index.json` — schema v2+: `base_markdown`, `read_order`, `canonical_context_urls`, `snapshots`.\n"
        "- Browse: https://github.com/TrueSightDAO/ecosystem_change_logs/tree/main/advisory\n"
    )
    if not readme.is_file() or readme.read_text(encoding="utf-8") != readme_body:
        readme.write_text(readme_body, encoding="utf-8")

    print(f"Written: {snap_path_ctx}\nWritten: {snap_file}\nWritten: {advisory_dir / 'index.json'}\n", file=sys.stderr, flush=True)
    if not args.no_stdout:
        print(text, end="", flush=True)

    if args.git_commit:
        msg_ctx = f"chore(advisory): refresh ADVISORY_SNAPSHOT ({date_str} UTC)"
        _git_commit_paths(ctx_root, ["ADVISORY_SNAPSHOT.md"], msg_ctx)
        eco_paths = [
            "advisory/BASE.md",
            f"advisory/snapshots/{date_str}.md",
            "advisory/index.json",
            "advisory/README.md",
        ]
        _git_commit_paths(eco_repo, eco_paths, f"chore(advisory): snapshot {date_str} UTC")
        if args.git_push:
            _git_push_repo(ctx_root)
            _git_push_repo(eco_repo)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
