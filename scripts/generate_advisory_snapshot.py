#!/usr/bin/env python3
"""
Compile **ADVISORY_SNAPSHOT.md** (LLM-oriented DAO state) from real workspace sources.

Writes:
  - ``../agentic_ai_context/ADVISORY_SNAPSHOT.md`` (Cursor mirror; raw GitHub after push:
    ``https://raw.githubusercontent.com/TrueSightDAO/agentic_ai_context/main/ADVISORY_SNAPSHOT.md``)
  - ``../ecosystem_change_logs/advisory/snapshots/<UTC-date>.md`` (**canonical** dated digest
    for ``advisory/index.json`` / ``ADVISORY_MOBILE_START.md``; raw GitHub after push under
    ``TrueSightDAO/ecosystem_change_logs``)
  - ``../ecosystem_change_logs/advisory/index.json`` (manifest — includes **absolute raw-GitHub URLs**
    so fetchers do not have to guess ``main`` paths)

Optional git (opt-in — **required** for GitHub to match disk unless using API publish):
  --git-commit   commit only the generated paths in each repo (fails if nothing staged)
  --git-push     push ``origin`` default branch after commit (both repos)
  --git-publish  shorthand for ``--git-commit --git-push`` (publish to GitHub ``origin``)
  --github-api-publish  update ``TrueSightDAO/agentic_ai_context`` + ``TrueSightDAO/ecosystem_change_logs``
    via **GitHub Contents API** (``PUT /repos/.../contents/...``) — no ``git push`` in those clones.
    Token: env ``TRUESIGHT_DAO_ORACLE_ADVISORY_PAT``, ``GITHUB_TOKEN``, or ``GH_TOKEN`` (needs **contents:write**).
    Mutually exclusive with ``--git-commit`` / ``--git-push`` / ``--git-publish``.

Usage (from ``market_research/``)::

  python3 scripts/generate_advisory_snapshot.py
  python3 scripts/generate_advisory_snapshot.py --since-days 7 --with-sheet-sales
  python3 scripts/generate_advisory_snapshot.py --since-days 7 --with-rem
  python3 scripts/generate_advisory_snapshot.py --since-days 7 --git-publish
  python3 scripts/generate_advisory_snapshot.py --since-days 7 --github-api-publish

No secrets are embedded in the repo. Telegram/DApp helpers are **not** included by default
(use Beer Hall preview for those). Optional **`--with-sheet-sales`** (local only) appends
rollup **`Monthly Statistics`** plus recent **`QR Code Sales`** rows from the canonical
workbooks documented in **`tokenomics/SCHEMA.md`** (requires `market_research/google_credentials.json`).

Optional **`--with-rem`** (macOS only) runs the **`rem`** CLI against Reminders.app and appends
**open** reminders as JSON-backed tables plus short **suggestion seeds** for the oracle
advisor (use ``rem list --incomplete -o json``; global flag ``-o`` / ``--output``, not ``--json``).

Optional **`--reminders-json PATH`** (CI / Linux) loads a JSON array (``rem list -o json`` shape). **Done**
rows are **dropped** so advisors only see actionable items — still prefer exporting with
``rem list --incomplete -o json`` or ``scripts/export_advisory_reminders_json.sh``.
Mutually exclusive with **`--with-rem`**.

Default output remains git + context files + Beer Hall archives + notes mtime.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

# Raw ``main`` URLs LLMs and ``ADVISORY_MOBILE_START.md`` resolve after ``git push``.
_RAW_ECO_BASE = "https://raw.githubusercontent.com/TrueSightDAO/ecosystem_change_logs/main"
_RAW_CTX_BASE = "https://raw.githubusercontent.com/TrueSightDAO/agentic_ai_context/main"

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
    ("iching_oracle", "oracle"),
    ("Cypher-Defense", "Cypher-Defense"),
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


_OPERATOR_BLOCK_PLACEHOLDER_RE = re.compile(r"<!--\s*TODO", re.IGNORECASE)

_GROWTH_GOALS_FILENAME = "GROWTH_GOALS.json"

_US_STATES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming", "district of columbia",
    "usa", "united states", "u.s.", "u.s.a.",
}

_US_STATE_ABBR = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id",
    "il", "in", "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms",
    "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok",
    "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv",
    "wi", "wy", "dc",
}


def _us_region_match(location: object) -> bool:
    """Last comma-separated token is a US state name or 2-letter code, or the
    whole string explicitly names the USA. Designed for `Agroverse Partners.location`
    values like ``Los Angeles, California`` (US) vs ``Bahia, Brazil`` (non-US).
    """
    s = str(location or "").strip()
    if not s:
        return False
    s_low = s.lower()
    for marker in ("usa", "united states", "u.s.a.", "u.s."):
        if s_low == marker or s_low.endswith(", " + marker):
            return True
    parts = [p.strip().lower() for p in s.split(",") if p.strip()]
    if not parts:
        return False
    last = parts[-1]
    if last in _US_STATES:
        return True
    if len(last) == 2 and last in _US_STATE_ABBR:
        return True
    return False


def _coerce_number(raw: object) -> float | None:
    """Parse a sheet cell as a number, tolerating ``$``, ``,`` and whitespace."""
    if raw is None:
        return None
    s = str(raw).strip().replace("$", "").replace(",", "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _load_growth_goals(ctx_root: Path) -> list[dict] | None:
    """Load ``GROWTH_GOALS.json`` from agentic_ai_context. Returns None on any failure."""
    path = ctx_root / _GROWTH_GOALS_FILENAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    goals = data.get("goals") if isinstance(data, dict) else None
    if not isinstance(goals, list):
        return None
    return goals


def _fetch_goal_actual(gc, goal: dict) -> tuple[float | None, str]:
    """Query the configured sheet source. Returns (actual, note). actual is None on failure."""
    src = goal.get("source") or {}
    sheet_id = (src.get("sheet_id") or "").strip()
    tab = (src.get("tab") or "").strip()
    column_name = (src.get("column") or "").strip()
    aggregation = (src.get("aggregation") or "").strip()
    if not (sheet_id and tab and column_name and aggregation):
        return None, "missing source fields"
    try:
        ws = gc.open_by_key(sheet_id).worksheet(tab)
        rows = ws.get_all_values()
    except Exception as e:
        return None, f"read failed: {e}"
    if not rows or len(rows) < 2:
        return None, "sheet empty"
    hdr = rows[0]
    cmap = _header_col_map(hdr)
    ci = cmap.get(_norm_header_cell(column_name))
    if ci is None:
        return None, f"column {column_name!r} not in header"
    data = rows[1:]
    filt = src.get("filter") or None
    if filt:
        fcol = (filt.get("column") or "").strip()
        predicate = (filt.get("predicate") or "").strip()
        value = str(filt.get("value") or "").strip()
        fci = cmap.get(_norm_header_cell(fcol)) if fcol else None
        if fci is None:
            return None, f"filter column {fcol!r} not in header"
        if predicate == "us_region":
            data = [r for r in data if fci < len(r) and _us_region_match(r[fci])]
        elif predicate == "starts_with":
            if not value:
                return None, "filter predicate 'starts_with' requires a value"
            data = [r for r in data if fci < len(r) and str(r[fci] or "").strip().startswith(value)]
        else:
            return None, f"unsupported predicate: {predicate!r}"
    values = [r[ci] if ci < len(r) else "" for r in data]
    if aggregation == "count_nonempty":
        return float(sum(1 for v in values if (v or "").strip())), "count of non-empty rows"
    if aggregation == "last_nonempty":
        for v in reversed(values):
            n = _coerce_number(v)
            if n is not None:
                return n, "last numeric non-empty row"
        return None, "no numeric non-empty rows"
    if aggregation == "sum":
        nums = [n for n in (_coerce_number(v) for v in values) if n is not None]
        return float(sum(nums)), f"sum of {len(nums)} numeric rows"
    return None, f"unsupported aggregation: {aggregation!r}"


def _fmt_goal_number(v: float | None, unit: str) -> str:
    if v is None:
        return "—"
    u = unit.lower().strip()
    if u in ("usd", "$"):
        return f"${v:,.0f}"
    if float(v).is_integer():
        return f"{int(v):,}"
    return f"{v:,.2f}"


def _render_goal_progress_block(ctx_root: Path, cred_path: Path) -> str:
    """Render ``## Growth goals`` with live sheet numbers and pace signal."""
    parts: list[str] = ["---\n\n## Growth goals (year / quarter)\n\n"]
    goals = _load_growth_goals(ctx_root)
    if not goals:
        parts.append(
            f"_Not yet configured. Add `{_GROWTH_GOALS_FILENAME}` at `{ctx_root}` "
            "with a `{\"goals\": [...]}` object to surface progress here._\n\n"
        )
        return "".join(parts)

    gc = None
    auth_note = ""
    if cred_path.is_file():
        try:
            import gspread
            from google.oauth2.service_account import Credentials as SACredentials
            creds = SACredentials.from_service_account_file(str(cred_path), scopes=_SHEETS_SCOPES)
            gc = gspread.authorize(creds)
        except Exception as e:
            auth_note = f" (live fetch skipped: `{e}`)"
    else:
        auth_note = f" (live fetch skipped: missing `{cred_path.name}`)"

    today = dt.datetime.now(dt.timezone.utc).date()
    parts.append("| Goal | Target | Actual | % | Deadline | Days left | Pace |\n")
    parts.append("|------|--------|--------|---|----------|-----------|------|\n")
    for g in goals:
        name = str(g.get("name") or "—")
        target = _coerce_number(g.get("target"))
        unit = str(g.get("unit") or "").strip()
        deadline = _parse_cell_to_date(str(g.get("deadline") or ""))
        actual, _ = (None, "")
        if gc is not None:
            actual, _ = _fetch_goal_actual(gc, g)
        pct_str = "—"
        if target and actual is not None:
            pct_str = f"{(actual / target) * 100:.0f}%"
        days_left_str = "—"
        pace_str = "—"
        if deadline is not None:
            days_left = (deadline - today).days
            days_left_str = str(days_left)
            if actual is not None and target:
                period_start = deadline.replace(month=1, day=1)
                total_days = max(1, (deadline - period_start).days)
                elapsed = max(0, min(total_days, (today - period_start).days))
                elapsed_pct = elapsed / total_days
                goal_pct = actual / target
                if goal_pct >= elapsed_pct + 0.05:
                    pace_str = "**ahead**"
                elif goal_pct <= elapsed_pct - 0.05:
                    pace_str = "**behind**"
                else:
                    pace_str = "on track"
        parts.append(
            f"| {name} | {_fmt_goal_number(target, unit)} "
            f"| {_fmt_goal_number(actual, unit)} | {pct_str} "
            f"| `{deadline.isoformat() if deadline else '—'}` | {days_left_str} | {pace_str} |\n"
        )
    parts.append("\n")
    if auth_note:
        parts.append(f"_Notes:{auth_note}_\n\n")
    return "".join(parts)



def _read_operator_block(path: Path, heading: str, purpose: str) -> str:
    """Render an operator-curated markdown file as a snapshot section.

    These are strategic inputs (goals, constraints, metrics) that cannot be
    derived from git or sheets. If the file is missing or only contains a TODO
    placeholder, we still emit a visible block with a prompt so the operator
    sees exactly where to edit. The LLM advisor reads the same block.
    """
    parts = [f"---\n\n{heading}\n\n"]
    rel = path.name
    if not path.is_file():
        parts.append(f"_Not yet created. Add `{rel}` at `{path}` to surface this here._\n")
        parts.append(f"_Purpose: {purpose}_\n\n")
        return "".join(parts)
    try:
        body = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        parts.append(f"_Could not read `{rel}`._\n\n")
        return "".join(parts)
    stripped_body = body.strip()
    only_placeholder = (not stripped_body) or _OPERATOR_BLOCK_PLACEHOLDER_RE.search(stripped_body) and not any(
        line.strip() and not line.lstrip().startswith("<!--") and not line.lstrip().startswith("_") and not line.startswith("#")
        for line in stripped_body.splitlines()
    )
    if only_placeholder:
        parts.append(f"_`{rel}` exists but is empty / placeholder. Edit it at `{path}`._\n")
        parts.append(f"_Purpose: {purpose}_\n\n")
        return "".join(parts)
    # Strip a leading top-level heading if the operator file uses one — the
    # advisory snapshot already provides the heading for this section.
    rendered = re.sub(r"\A# [^\n]*\n+", "", stripped_body, count=1)
    parts.append(rendered.rstrip())
    parts.append("\n\n")
    return "".join(parts)


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


def _rem_parse_due_date(raw: object) -> dt.date | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _rem_filter_list(rows: list[dict[str, object]], list_name: str | None) -> list[dict[str, object]]:
    if not list_name or not list_name.strip():
        return rows
    want = list_name.strip().lower()
    return [r for r in rows if str(r.get("list_name") or "").strip().lower() == want]


def _rem_item_is_done(item: dict[str, object]) -> bool:
    """Treat a reminder row as **done** so it is excluded from LLM action-item lists."""
    c = item.get("completed")
    if c is True or c == 1:
        return True
    if isinstance(c, str) and c.strip().lower() in ("true", "1", "yes"):
        return True
    st = str(item.get("status") or "").strip().lower()
    if st in ("done", "completed", "complete", "cancelled", "canceled"):
        return True
    return False


def _rem_rows_open_for_advisor(data: object) -> list[dict[str, object]]:
    """Keep only **open** reminders (not done) for advisor prioritization — safe even if JSON mixed done/open."""
    rows_raw: list[dict[str, object]] = []
    if not isinstance(data, list):
        return rows_raw
    for item in data:
        if not isinstance(item, dict):
            continue
        if _rem_item_is_done(item):
            continue
        rows_raw.append(item)
    return rows_raw


def _rem_render_section(
    rows_raw: list[dict[str, object]],
    *,
    limit: int,
    list_name: str | None,
    heading: str,
    intro: str,
) -> str:
    today = dt.datetime.now(dt.timezone.utc).date()

    def _sort_key(d: dict[str, object]) -> tuple:
        due = _rem_parse_due_date(d.get("due_date"))
        overdue = 0 if (due is not None and due < today) else 1
        flagged = 0 if d.get("flagged") is True else 1
        due_sort = due if due is not None else dt.date(9999, 12, 31)
        return (overdue, flagged, due_sort, str(d.get("name") or "").lower())

    rows = list(rows_raw)
    rows.sort(key=_sort_key)
    cap = max(1, limit)
    picked = rows[:cap]

    parts: list[str] = []
    parts.append(f"---\n\n{heading}\n\n")
    parts.append(intro)
    if list_name:
        parts.append(f"\n_Filtered to list:_ `{_md_cell(list_name, max_len=64)}`\n\n")
    else:
        parts.append("\n")

    if not picked:
        parts.append("_No open (not done) reminders in this source._\n\n")
        return "".join(parts)

    parts.append(f"_Showing **{len(picked)}** of **{len(rows)}** open reminders (cap `--rem-limit`)._\n\n")
    parts.append("| Title | List | Due (date) | Flagged | Notes (trunc.) |\n")
    parts.append("|-------|------|------------|---------|------------------|\n")
    for d in picked:
        title = _md_cell(d.get("name"), max_len=72)
        lst = _md_cell(d.get("list_name"), max_len=20)
        due_d = _rem_parse_due_date(d.get("due_date"))
        due_s = due_d.isoformat() if due_d else "—"
        flg = "**yes**" if d.get("flagged") is True else "—"
        body = d.get("body")
        notes = _md_cell(body if body is not None else "", max_len=96)
        parts.append(f"| {title} | {lst} | `{due_s}` | {flg} | {notes} |\n")

    parts.append("\n### Suggestion seeds (titles only)\n\n")
    for d in picked[: min(24, len(picked))]:
        t = re.sub(r"[\r\n]+", " ", str(d.get("name") or "")).strip()
        if t:
            parts.append(f"- {t}\n")
    parts.append("\n")

    if len(rows) > cap:
        parts.append(f"_… **{len(rows) - cap}** more open reminders not shown (raise `--rem-limit`)._\n\n")

    return "".join(parts)


def _rem_collect_open_rows(
    *,
    list_name: str | None,
    reminders_json: Path | None,
) -> list[dict[str, object]] | None:
    """Return open (not-done) reminders as a filtered list, or None on any failure.

    Used to both feed the markdown section and write reminders/current.json to
    ecosystem_change_logs so the iching_oracle GAS backend can fetch them directly.
    """
    if reminders_json is not None:
        try:
            raw = reminders_json.read_text(encoding="utf-8", errors="replace")
            data = json.loads(raw.strip() or "[]")
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, list):
            return None
        return _rem_filter_list(_rem_rows_open_for_advisor(data), list_name)

    rem_bin = shutil.which("rem")
    if not rem_bin:
        return None
    cmd: list[str] = [rem_bin, "list", "--incomplete", "-o", "json"]
    if list_name:
        cmd.extend(["-l", list_name])
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        out = (p.stdout or "") + (p.stderr or "")
        if p.returncode != 0:
            return None
    except (OSError, subprocess.TimeoutExpired):
        return None
    try:
        data = json.loads(out.strip() or "[]")
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    return _rem_filter_list(_rem_rows_open_for_advisor(data), list_name)


def _write_reminders_json(eco_repo: Path, rows: list[dict[str, object]], date_str: str) -> None:
    """Write open reminders to ecosystem_change_logs/reminders/current.json + dated archive.

    The stable URL ``reminders/current.json`` is fetched by the iching_oracle GAS backend
    so Grok has the operator's current open intentions as context for every hexagram reading.
    Dated archives allow historical review. Only open (not-done) rows are written.
    """
    rem_dir = eco_repo / "reminders"
    rem_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": date_str,
        "source": "rem list --incomplete -o json (macOS Reminders via rem CLI)",
        "count": len(rows),
        "reminders": rows,
    }
    content = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    (rem_dir / "current.json").write_text(content, encoding="utf-8")
    (rem_dir / f"{date_str}.json").write_text(content, encoding="utf-8")
    print(
        f"Written: {rem_dir / 'current.json'}\nWritten: {rem_dir / f'{date_str}.json'}",
        file=sys.stderr,
    )


def _rem_outstanding_markdown(
    *,
    limit: int,
    list_name: str | None,
    reminders_json: Path | None,
) -> str:
    """Open reminders only (never **done**): macOS ``rem`` CLI, or JSON (``rem list -o json`` shape).

    Rows are filtered with ``_rem_rows_open_for_advisor`` so mixed exports still omit completed items.
    """
    if reminders_json is not None:
        try:
            raw = reminders_json.read_text(encoding="utf-8", errors="replace")
            data = json.loads(raw.strip() or "[]")
        except (OSError, json.JSONDecodeError) as e:
            return (
                "---\n\n## Open reminders (cached JSON)\n\n"
                f"_(Skipped: could not read `{reminders_json}`: `{e}`.)_\n\n"
            )
        if not isinstance(data, list):
            return (
                "---\n\n## Open reminders (cached JSON)\n\n"
                f"_(Skipped: expected a JSON array in `{reminders_json}`, got `{type(data).__name__}`.)_\n\n"
            )
        rows_raw = _rem_filter_list(_rem_rows_open_for_advisor(data), list_name)
        src = f"`{reminders_json}`"
        return _rem_render_section(
            rows_raw,
            limit=limit,
            list_name=list_name,
            heading="## Open reminders (cached JSON — action items)",
            intro=(
                f"_Open (not done) items loaded from {src}; export with `rem list --incomplete -o json` or "
                "`scripts/export_advisory_reminders_json.sh` so **done** rows are never written. "
                "Refresh from a Mac when you want CI to mirror actionable tasks. "
                "When the user asks for **oracle response options**, propose **1–3** concrete next steps that honestly "
                "connect the hexagram reading to these open items where it fits; do **not** invent due dates or "
                "claim items are done._"
            ),
        )

    rem_bin = shutil.which("rem")
    if not rem_bin:
        return (
            "---\n\n## Open reminders (macOS `rem`)\n\n"
            "_(Skipped: `rem` not on `PATH` — install from https://rem.sidv.dev/ .)_\n\n"
        )

    cmd: list[str] = [rem_bin, "list", "--incomplete", "-o", "json"]
    if list_name:
        cmd.extend(["-l", list_name])

    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        out = (p.stdout or "") + (p.stderr or "")
        if p.returncode != 0:
            return (
                "---\n\n## Open reminders (macOS `rem`)\n\n"
                f"_(Skipped: `{' '.join(cmd)}` exited {p.returncode}: `{_md_cell(out, max_len=240)}`.)_\n\n"
            )
    except (OSError, subprocess.TimeoutExpired) as e:
        return (
            "---\n\n## Open reminders (macOS `rem`)\n\n"
            f"_(Skipped: could not run `rem`: `{e}`.)_\n\n"
        )

    try:
        data = json.loads(out.strip() or "[]")
    except json.JSONDecodeError as e:
        return (
            "---\n\n## Open reminders (macOS `rem`)\n\n"
            f"_(Skipped: JSON parse error from `rem list`: `{e}`.)_\n\n"
        )

    if not isinstance(data, list):
        return (
            "---\n\n## Open reminders (macOS `rem`)\n\n"
            f"_(Skipped: expected JSON array from `rem list`, got `{type(data).__name__}`.)_\n\n"
        )

    rows_raw = _rem_filter_list(_rem_rows_open_for_advisor(data), list_name)

    return _rem_render_section(
        rows_raw,
        limit=limit,
        list_name=list_name,
        heading="## Open reminders (macOS `rem` — action items)",
        intro=(
            "_Open (not done) items from Reminders.app (`rem list --incomplete -o json`). "
            "When the user asks for **oracle response options**, propose **1–3** concrete next steps "
            "that honestly connect the hexagram reading to these **actionable** items where it fits; "
            "do **not** invent due dates or claim items are done._"
        ),
    )


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
    rem_md: str = "",
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

    # Operator-curated strategic frame. Placed before evidence so the LLM reads
    # goals / constraints / metrics *first*, then interprets the activity below.
    # Growth goals are auto-computed against live sheet data (GROWTH_GOALS.json).
    parts.append(_render_goal_progress_block(ctx_root, _REPO / "google_credentials.json"))
    parts.append(_read_operator_block(
        ctx_root / "CONSTRAINTS.md",
        "## Constraints / risks this week",
        "Current bottlenecks (capital, inventory, fulfilment, capacity, distribution).",
    ))
    parts.append(_read_operator_block(
        ctx_root / "METRICS_WEEKLY.md",
        "## Operator metrics (manual, 7-day)",
        "Numbers that cannot be auto-derived from sheets. Complements --with-sheet-sales.",
    ))

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

    if rem_md:
        parts.append(rem_md)

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
    """Stable raw-GitHub URLs for LLM retrieval (agentic_ai_context ``main``)."""
    return [
        f"{_RAW_CTX_BASE}/WORKSPACE_CONTEXT.md",
        f"{_RAW_CTX_BASE}/PROJECT_INDEX.md",
        f"{_RAW_CTX_BASE}/OPENCLAW_WHATSAPP.md",
        f"{_RAW_CTX_BASE}/GOVERNANCE_SOURCES.md",
        f"{_RAW_CTX_BASE}/LEDGER_CONVERSION_AND_REPACKAGING.md",
        f"{_RAW_CTX_BASE}/CONTEXT_UPDATES.md",
        f"{_RAW_CTX_BASE}/ADVISORY_SNAPSHOT.md",
        f"{_RAW_ECO_BASE}/reminders/current.json",
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
    latest_rel: str | None = None
    if entries:
        latest_rel = str(entries[0]["markdown"])
        read_order.append(latest_rel)
    latest_raw = f"{_RAW_ECO_BASE}/{latest_rel}" if latest_rel else ""
    doc: dict[str, object] = {
        "schema_version": 2,
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "latest_date": date_str,
        "base_markdown": "advisory/BASE.md",
        "read_order": read_order,
        "canonical_context_urls": _canonical_context_urls(),
        "raw_github": {
            "ecosystem_change_logs_tree": "https://github.com/TrueSightDAO/ecosystem_change_logs/tree/main/advisory",
            "ecosystem_change_logs_raw_base": _RAW_ECO_BASE,
            "agentic_ai_context_raw_base": _RAW_CTX_BASE,
            "latest_advisory_snapshot_raw_url": latest_raw,
            "advisory_snapshot_cursor_mirror_raw_url": f"{_RAW_CTX_BASE}/ADVISORY_SNAPSHOT.md",
        },
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


_GH_API_VERSION = "2022-11-28"


def _github_token_from_env() -> str:
    for key in ("TRUESIGHT_DAO_ORACLE_ADVISORY_PAT", "GITHUB_TOKEN", "GH_TOKEN"):
        v = (os.environ.get(key) or "").strip()
        if v:
            return v
    raise SystemExit(
        "GitHub Contents API publish requires a token in env "
        "`TRUESIGHT_DAO_ORACLE_ADVISORY_PAT`, `GITHUB_TOKEN`, or `GH_TOKEN`."
    )


def _github_request_json(
    method: str,
    url: str,
    *,
    token: str,
    data: dict[str, object] | None = None,
) -> object:
    body_bytes = None if data is None else json.dumps(data).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": _GH_API_VERSION,
        "User-Agent": "generate_advisory_snapshot.py",
    }
    if body_bytes is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"GitHub API HTTP {e.code} for {url}: {err_body[:2000]}") from e


def _github_repo_default_branch(owner: str, repo: str, token: str) -> str:
    info = _github_request_json("GET", f"https://api.github.com/repos/{owner}/{repo}", token=token)
    if isinstance(info, dict):
        br = str(info.get("default_branch") or "").strip()
        if br:
            return br
    return "main"


def _github_contents_sha(owner: str, repo: str, path: str, branch: str, token: str) -> str | None:
    enc = urllib.parse.quote(path, safe="/")
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{enc}?ref={urllib.parse.quote(branch)}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": _GH_API_VERSION,
        "User-Agent": "generate_advisory_snapshot.py",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            cur = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        err_body = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"GitHub API HTTP {e.code} for {url}: {err_body[:2000]}") from e
    if isinstance(cur, dict) and cur.get("type") == "file" and isinstance(cur.get("sha"), str):
        return str(cur["sha"])
    return None


def _github_put_text_file(
    owner: str,
    repo: str,
    path: str,
    *,
    branch: str,
    token: str,
    content: str,
    message: str,
) -> None:
    sha = _github_contents_sha(owner, repo, path, branch, token)
    enc = urllib.parse.quote(path, safe="/")
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{enc}"
    payload: dict[str, object] = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha
    _github_request_json("PUT", url, token=token, data=payload)
    print(f"GitHub API updated {owner}/{repo}:{path} @ {branch}", file=sys.stderr)


def _github_api_publish_advisory(
    *,
    owner: str,
    ctx_repo: str,
    eco_repo: str,
    branch_ctx: str,
    branch_eco: str,
    token: str,
    date_str: str,
    snap_path_ctx: Path,
    snap_file: Path,
    index_path: Path,
    readme_path: Path,
    beer_preview: Path | None,
) -> None:
    """Push generated advisory artifacts via GitHub Contents API (one commit per file on GitHub)."""
    _github_put_text_file(
        owner,
        ctx_repo,
        "ADVISORY_SNAPSHOT.md",
        branch=branch_ctx,
        token=token,
        content=snap_path_ctx.read_text(encoding="utf-8", errors="strict"),
        message=f"chore(advisory): refresh ADVISORY_SNAPSHOT ({date_str} UTC)",
    )
    if beer_preview is not None and beer_preview.is_file():
        _github_put_text_file(
            owner,
            ctx_repo,
            "previews/beer_hall_preview_latest.md",
            branch=branch_ctx,
            token=token,
            content=beer_preview.read_text(encoding="utf-8", errors="strict"),
            message=f"chore(previews): refresh Beer Hall preview ({date_str} UTC)",
        )
    _github_put_text_file(
        owner,
        eco_repo,
        f"advisory/snapshots/{date_str}.md",
        branch=branch_eco,
        token=token,
        content=snap_file.read_text(encoding="utf-8", errors="strict"),
        message=f"chore(advisory): snapshot {date_str} UTC",
    )
    _github_put_text_file(
        owner,
        eco_repo,
        "advisory/index.json",
        branch=branch_eco,
        token=token,
        content=index_path.read_text(encoding="utf-8", errors="strict"),
        message=f"chore(advisory): refresh index.json ({date_str} UTC)",
    )
    if readme_path.is_file():
        _github_put_text_file(
            owner,
            eco_repo,
            "advisory/README.md",
            branch=branch_eco,
            token=token,
            content=readme_path.read_text(encoding="utf-8", errors="strict"),
            message=f"chore(advisory): refresh README ({date_str} UTC)",
        )


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
        "--git-publish",
        action="store_true",
        help="Shorthand for --git-commit --git-push (publish generated files to GitHub origin).",
    )
    ap.add_argument(
        "--github-api-publish",
        action="store_true",
        help=(
            "Publish generated files via GitHub **Contents API** (no git commit/push in clones). "
            "Token: env TRUESIGHT_DAO_ORACLE_ADVISORY_PAT, GITHUB_TOKEN, or GH_TOKEN (contents:write on both repos)."
        ),
    )
    ap.add_argument(
        "--github-api-owner",
        type=str,
        default="TrueSightDAO",
        help="With --github-api-publish: GitHub org or user (default TrueSightDAO).",
    )
    ap.add_argument(
        "--github-api-branch",
        type=str,
        default="",
        help=(
            "With --github-api-publish: branch to update in both repos (default: each repo's GitHub default_branch)."
        ),
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
    ap.add_argument(
        "--with-rem",
        action="store_true",
        help=(
            "Append **open** (not done) macOS Reminders via `rem list --incomplete -o json` "
            "(plus server-side drop of any done-shaped rows). macOS + `rem` on PATH only. "
            "**Warning:** titles/notes are personal — avoid `--git-commit` into a public repo if sensitive."
        ),
    )
    ap.add_argument(
        "--rem-limit",
        type=int,
        default=60,
        help="With --with-rem: max reminders to include in the snapshot tables (default 60).",
    )
    ap.add_argument(
        "--rem-list",
        type=str,
        default="",
        help="With --with-rem: optional Reminders list name passed to `rem list -l` (default: all lists).",
    )
    ap.add_argument(
        "--reminders-json",
        type=str,
        default="",
        help=(
            "Append **open** reminders from JSON (`rem list -o json` shape); **done** rows are ignored. "
            "For GitHub Actions / Linux; mutually exclusive with --with-rem."
        ),
    )
    args = ap.parse_args()

    if args.git_publish:
        args.git_commit = True
        args.git_push = True

    if args.github_api_publish and (args.git_commit or args.git_push or args.git_publish):
        ap.error("use either --github-api-publish or git-based flags (--git-commit/--git-push/--git-publish), not both")

    if args.git_push and not args.git_commit:
        ap.error("--git-push requires --git-commit")

    if args.with_rem and (args.reminders_json or "").strip():
        ap.error("use either --with-rem or --reminders-json, not both")

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

    rem_md = ""
    open_rem_rows: list[dict[str, object]] | None = None
    rj = (args.reminders_json or "").strip()
    if rj:
        _rj_path = Path(rj).expanduser().resolve()
        open_rem_rows = _rem_collect_open_rows(
            list_name=(args.rem_list.strip() or None),
            reminders_json=_rj_path,
        )
        rem_md = _rem_outstanding_markdown(
            limit=max(1, args.rem_limit),
            list_name=(args.rem_list.strip() or None),
            reminders_json=_rj_path,
        )
    elif args.with_rem:
        open_rem_rows = _rem_collect_open_rows(
            list_name=(args.rem_list.strip() or None),
            reminders_json=None,
        )
        rem_md = _rem_outstanding_markdown(
            limit=max(1, args.rem_limit),
            list_name=(args.rem_list.strip() or None),
            reminders_json=None,
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
        rem_md=rem_md,
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

    if open_rem_rows is not None:
        _write_reminders_json(eco_repo, open_rem_rows, date_str)

    readme = advisory_dir / "README.md"
    readme_body = (
        "# Advisory corpus (LLMs)\n\n"
        "**Read `BASE.md` first** — stable DAO orientation, ledger map, and canonical URLs. "
        "Then open `index.json` and the latest dated file under `snapshots/`.\n\n"
        "Daily evidence digests are generated by "
        "`market_research/scripts/generate_advisory_snapshot.py` "
        "(git + `CONTEXT_UPDATES` + Beer Hall excerpts; optional `--with-sheet-sales`, `--with-rem`, `--reminders-json`).\n\n"
        "- `BASE.md` — slow-changing strategic context (not regenerated by the snapshot script).\n"
        "- `snapshots/YYYY-MM-DD.md` — one file per UTC day (last write wins if re-run same day).\n"
        "- `index.json` — schema v2+: `base_markdown`, `read_order`, `canonical_context_urls`, `raw_github`, `snapshots`.\n"
        "- Browse: https://github.com/TrueSightDAO/ecosystem_change_logs/tree/main/advisory\n"
    )
    if not readme.is_file() or readme.read_text(encoding="utf-8") != readme_body:
        readme.write_text(readme_body, encoding="utf-8")

    print(f"Written: {snap_path_ctx}\nWritten: {snap_file}\nWritten: {advisory_dir / 'index.json'}\n", file=sys.stderr, flush=True)
    print(
        "LLM raw targets (GitHub default branch after publish):",
        f"{_RAW_ECO_BASE}/advisory/snapshots/{date_str}.md",
        f"{_RAW_CTX_BASE}/ADVISORY_SNAPSHOT.md",
        sep="\n  ",
        file=sys.stderr,
        flush=True,
    )
    print("", file=sys.stderr, flush=True)
    if not args.no_stdout:
        print(text, end="", flush=True)

    if args.github_api_publish:
        token = _github_token_from_env()
        owner = (args.github_api_owner or "TrueSightDAO").strip()
        br_opt = (args.github_api_branch or "").strip()
        branch_ctx = br_opt or _github_repo_default_branch(owner, "agentic_ai_context", token)
        branch_eco = br_opt or _github_repo_default_branch(owner, "ecosystem_change_logs", token)
        beer_preview_path = ctx_root / "previews" / "beer_hall_preview_latest.md"
        beer_opt: Path | None = beer_preview_path if beer_preview_path.is_file() else None
        _github_api_publish_advisory(
            owner=owner,
            ctx_repo="agentic_ai_context",
            eco_repo="ecosystem_change_logs",
            branch_ctx=branch_ctx,
            branch_eco=branch_eco,
            token=token,
            date_str=date_str,
            snap_path_ctx=snap_path_ctx,
            snap_file=snap_file,
            index_path=advisory_dir / "index.json",
            readme_path=readme,
            beer_preview=beer_opt,
        )
        if open_rem_rows is not None:
            rem_content = (eco_repo / "reminders" / "current.json").read_text(encoding="utf-8")
            _github_put_text_file(
                owner, "ecosystem_change_logs", "reminders/current.json",
                branch=branch_eco, token=token, content=rem_content,
                message=f"chore(reminders): sync open reminders ({date_str} UTC)",
            )
            _github_put_text_file(
                owner, "ecosystem_change_logs", f"reminders/{date_str}.json",
                branch=branch_eco, token=token, content=rem_content,
                message=f"chore(reminders): archive {date_str} UTC",
            )
        print("Published advisory artifacts via GitHub Contents API.", file=sys.stderr, flush=True)
    elif args.git_commit:
        msg_ctx = f"chore(advisory): refresh ADVISORY_SNAPSHOT ({date_str} UTC)"
        ctx_paths = ["ADVISORY_SNAPSHOT.md"]
        beer_preview = ctx_root / "previews" / "beer_hall_preview_latest.md"
        if beer_preview.is_file():
            ctx_paths.append("previews/beer_hall_preview_latest.md")
        _git_commit_paths(ctx_root, ctx_paths, msg_ctx)
        eco_paths = [
            "advisory/BASE.md",
            f"advisory/snapshots/{date_str}.md",
            "advisory/index.json",
            "advisory/README.md",
        ]
        if open_rem_rows is not None:
            eco_paths += [f"reminders/current.json", f"reminders/{date_str}.json"]
        _git_commit_paths(eco_repo, eco_paths, f"chore(advisory): snapshot {date_str} UTC")
        if args.git_push:
            _git_push_repo(ctx_root)
            _git_push_repo(eco_repo)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
