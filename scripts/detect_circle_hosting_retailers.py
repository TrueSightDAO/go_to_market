#!/usr/bin/env python3
"""
Hit List: detect retailers that **host circles** (women's circles, cacao ceremonies,
sound baths, breathwork, etc.) by crawling their **Website** for high-precision
keywords, AND fast-track those rows through the pipeline.

Why this matters: 2026-04-28 observation — both Way Home Shop (just onboarded) and
Lumin Earth (existing partner) prominently host women's circles. Ceremonial cacao
genuinely lives in that ecosystem, so "hosts circles" is plausibly a leading
indicator of cacao sell-through. This script populates the **Hosts Circles** Hit
List column so we can later cross-reference against ``partners-velocity.json`` once
that has ≥4 weekly refreshes (see ``OPEN_FOLLOWUPS.md`` entry).

Output values written to **Hosts Circles**:
  - ``Yes`` (with matched keyword list, e.g. ``Yes (women's circle, sound bath)``) —
    at least one high-precision keyword matched on at least one fetched page.
  - ``Not detected`` — site fetched OK but no keyword matched. **NOT** equivalent to
    "doesn't host" — many retailers surface circles only on Instagram or newsletter,
    which this crawler does not reach.
  - empty / unset — row had no Website, or all fetches failed (treated as "not yet
    checked" so the next run can retry).

Status promotion (default ON; disable with ``--no-promote``): when a row is
detected as ``Yes``, the script promotes it via the **DApp Remarks** audit
trail. Two cases:

  - **Email already on the row** → ``AI: Warm up prospect`` (skip Enrich
    entirely; warm-up drafter has everything it needs).
  - **Email missing** → ``AI: Enrich with contact`` (Enrich runs to harvest
    the email, then the row promotes to Warm up prospect).

This replaces the old photo+Grok rubric in ``hit_list_research_photo_review``
which used Place Photos to qualify rows. The site crawl is the cheaper +
more direct signal: if the website mentions cacao ceremony / women's circle
/ sound bath / etc., the row is qualified — no need to fetch storefront
photos and run them through a vision rubric to confirm.

Rejection on no signal (default ON; disable with ``--no-reject-no-signal``):
when a row's site is crawled successfully but **no** keyword matches, the
script promotes Status to ``AI: Photo rejected`` with an audit remark
explaining "no site signal". The status name is preserved for back-compat
with downstream filters; under the new model it means "site shows no
qualifying keywords" rather than "photos didn't show fit".

Retroactive rescue (``--rescue-rejected``, default ON): also re-evaluates
``AI: Photo rejected`` rows by crawling their sites and promoting any whose
Hosts Circles comes back as ``Yes``. Default-on so existing photo-rejected
rows (which were never crawled by site keyword) get re-evaluated under the
new criteria. Pass ``--no-rescue-rejected`` to opt out.

Rescue of stuck rows: ``AI: Enrich — manual`` and ``AI: Photo needs review``
rows are also eligible for promotion if their website reveals circle-hosting
signal. These are dead-end states where the row is waiting for human action;
a clear circle keyword on the site is strong enough signal to fast-track them
straight to ``AI: Warm up prospect`` (if email present) or
``AI: Enrich with contact`` (if not).

Idempotent: only writes empty Hosts Circles cells unless ``--force``.

Environment:
  - ``google_credentials.json`` (Sheets editor on the Hit List workbook)
  - No external API keys required.

Usage:
  cd market_research
  python3 scripts/detect_circle_hosting_retailers.py --dry-run --limit 5
  python3 scripts/detect_circle_hosting_retailers.py --limit 200
  python3 scripts/detect_circle_hosting_retailers.py --rescue-rejected --limit 50
  python3 scripts/detect_circle_hosting_retailers.py --no-promote --limit 50
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import gspread
import requests
from google.oauth2.service_account import Credentials
from gspread.utils import rowcol_to_a1

REPO = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from hit_list_dapp_remarks_sheet import append_dapp_remark_and_apply  # noqa: E402

SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
HIT_LIST_WS = "Hit List"
DAPP_REMARKS_WS = "DApp Remarks"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HOSTS_CIRCLES_COL = "Hosts Circles"
SUBMITTED_BY_CIRCLE = "detect_circle_hosting_retailers"
PROMOTABLE_FROM_RESEARCH = "Research"
PROMOTABLE_FROM_REJECTED = "AI: Photo rejected"
# Two promotion targets, picked at runtime based on whether the row has an
# email already — see promote_row_to_enrichment().
PROMOTION_TARGET_STATUS_ENRICH = "AI: Enrich with contact"
PROMOTION_TARGET_STATUS_WARMUP = "AI: Warm up prospect"
# Back-compat alias for the most common case (no email yet).
PROMOTION_TARGET_STATUS = PROMOTION_TARGET_STATUS_ENRICH
PROMOTABLE_FROM_MANUAL = "AI: Enrich — manual"
PROMOTABLE_FROM_NEEDS_REVIEW = "AI: Photo needs review"

KEYWORD_PATTERNS: tuple[tuple[str, str], ...] = (
    # (regex, canonical label written into the cell)
    (r"women'?s?\s+circle", "women's circle"),
    (r"moon\s+circle", "moon circle"),
    (r"new\s+moon\b", "new moon"),
    (r"full\s+moon\b", "full moon"),
    (r"cacao\s+ceremon", "cacao ceremony"),
    (r"cocoa\s+ceremon", "cocoa ceremony"),
    (r"sound\s+bath", "sound bath"),
    (r"sound\s+heal", "sound healing"),
    (r"breath\s*work", "breathwork"),
    (r"sister\s+circle", "sister circle"),
    (r"sacred\s+circle", "sacred circle"),
    (r"ecstatic\s+dance", "ecstatic dance"),
    (r"womb\s+heal", "womb healing"),
    (r"red\s+tent", "red tent"),
)

CRAWL_PATHS = ("/", "/events", "/classes", "/workshops", "/calendar", "/about", "/community")

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (compatible; TrueSight CircleSniffer/0.1; +https://truesight.me)"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
)


def gspread_client() -> gspread.Client:
    creds_path = REPO / "google_credentials.json"
    if not creds_path.is_file():
        raise SystemExit(f"Missing service account JSON: {creds_path}")
    creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
    return gspread.authorize(creds)


def strip_tags(html: str) -> str:
    s = re.sub(r"(?is)<script.*?</script>", " ", html)
    s = re.sub(r"(?is)<style.*?</style>", " ", s)
    s = re.sub(r"(?is)<noscript.*?</noscript>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s)


def crawl_site(website: str, *, sleep_s: float, max_chars: int) -> tuple[bool, list[str]]:
    """Returns (any_page_fetched_ok, ordered_list_of_unique_canonical_keyword_labels)."""
    base = (website or "").strip()
    if not base:
        return False, []
    if not base.lower().startswith(("http://", "https://")):
        base = "https://" + base
    base = base.rstrip("/")

    fetched_ok = False
    found: list[str] = []
    seen: set[str] = set()

    for path in CRAWL_PATHS:
        url = base + "/" if path == "/" else base + path
        try:
            r = SESSION.get(url, timeout=20, allow_redirects=True)
        except requests.RequestException:
            time.sleep(sleep_s)
            continue
        if r.status_code != 200 or not r.text:
            time.sleep(sleep_s)
            continue
        ct = (r.headers.get("Content-Type") or "").lower()
        if "html" not in ct and "text" not in ct and "xml" not in ct:
            time.sleep(sleep_s)
            continue
        fetched_ok = True
        text = strip_tags(r.text)
        if len(text) > max_chars:
            text = text[:max_chars]
        for pat, label in KEYWORD_PATTERNS:
            if label in seen:
                continue
            if re.search(pat, text, flags=re.IGNORECASE):
                seen.add(label)
                found.append(label)
        time.sleep(sleep_s)

    return fetched_ok, found


def reject_row_no_signal(
    ws: gspread.Worksheet,
    remark_ws: gspread.Worksheet,
    rn: int,
    shop: str,
    *,
    dry_run: bool,
) -> bool:
    """Mark ``rn`` as ``AI: Photo rejected`` because a successful site crawl
    found no qualifying circle / ceremony / cacao keywords.

    This replaces the photo+Grok rubric that ``hit_list_research_photo_review``
    used to run for the same purpose. The site crawl is the cheaper, more
    direct signal: if the site doesn't say it hosts circles, photos won't
    confidently say it does either. ``--rescue-rejected`` still re-promotes
    such rows later if the site develops the keywords.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    submitted_at = datetime.now(timezone.utc).strftime("%m/%d/%Y %H:%M:%S")
    remark = (
        f"[circle-detect {stamp}] outcome=reject_research_no_site_signal "
        f"site_crawled_ok matched=none "
        f"(photo+Grok rubric retired; site crawl is canonical qualifier)"
    )

    if dry_run:
        print(
            f"  [dry-run] row {rn} {shop!r}: would reject (no signal) -> AI: Photo rejected",
            flush=True,
        )
        return True

    append_dapp_remark_and_apply(
        ws,
        remark_ws,
        rn,
        shop,
        "AI: Photo rejected",
        remark,
        SUBMITTED_BY_CIRCLE,
        submitted_at,
        str(uuid.uuid4()),
    )
    return True


def promote_row_to_enrichment(
    ws: gspread.Worksheet,
    remark_ws: gspread.Worksheet,
    rn: int,
    shop: str,
    matched: list[str],
    *,
    rescue: bool,
    dry_run: bool,
    has_email: bool = False,
) -> bool:
    """Promote ``rn`` based on Hosts Circles match, via DApp Remarks audit.

    Target status:
      - ``has_email=True``  → ``AI: Warm up prospect`` (skip Enrich entirely;
        the warm-up drafter has the email it needs).
      - ``has_email=False`` → ``AI: Enrich with contact`` (Enrich runs to
        harvest the email, then promotes onward to Warm up prospect).

    ``rescue=True`` indicates we're un-rejecting an AI: Photo rejected row
    by site-crawl signal; the audit text reflects that.
    """
    target = PROMOTION_TARGET_STATUS_WARMUP if has_email else PROMOTION_TARGET_STATUS_ENRICH
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    submitted_at = datetime.now(timezone.utc).strftime("%m/%d/%Y %H:%M:%S")
    matched_str = ", ".join(matched) if matched else "circle keywords"
    skip_note = "skip_enrich=true" if has_email else "skip_enrich=false"
    if rescue:
        remark = (
            f"[circle-detect {stamp}] outcome=rescue_from_photo_rejection "
            f"matched={matched_str} {skip_note}"
        )
    else:
        outcome = (
            "fast_track_research_to_warmup"
            if has_email else "fast_track_research_to_enrich"
        )
        remark = (
            f"[circle-detect {stamp}] outcome={outcome} "
            f"matched={matched_str} {skip_note}"
        )

    if dry_run:
        action = "rescue from AI: Photo rejected" if rescue else "promote from Research"
        print(
            f"  [dry-run] row {rn} {shop!r}: would {action} -> {target}",
            flush=True,
        )
        return True

    append_dapp_remark_and_apply(
        ws,
        remark_ws,
        rn,
        shop,
        target,
        remark,
        SUBMITTED_BY_CIRCLE,
        submitted_at,
        str(uuid.uuid4()),
    )
    return True


def ensure_hosts_circles_column(ws: gspread.Worksheet, header: list[str], dry_run: bool) -> int:
    """Returns 0-based column index of Hosts Circles, adding the header if missing."""
    if HOSTS_CIRCLES_COL in header:
        return header.index(HOSTS_CIRCLES_COL)
    new_idx = len(header)
    if dry_run:
        print(f"[dry-run] would add header {HOSTS_CIRCLES_COL!r} at column {new_idx + 1}", flush=True)
        header.append(HOSTS_CIRCLES_COL)
        return new_idx
    if ws.col_count < new_idx + 1:
        ws.add_cols(new_idx + 1 - ws.col_count)
    ws.update_cell(1, new_idx + 1, HOSTS_CIRCLES_COL)
    header.append(HOSTS_CIRCLES_COL)
    print(f"Added header {HOSTS_CIRCLES_COL!r} at column {new_idx + 1}.", flush=True)
    return new_idx


def main() -> None:
    p = argparse.ArgumentParser(
        description="Detect circle-hosting retailers from their Website and write Hit List Hosts Circles column."
    )
    p.add_argument("--limit", type=int, default=200, help="Max rows to crawl this run (default 200).")
    p.add_argument("--dry-run", action="store_true", help="Print plan only; do not write the sheet.")
    p.add_argument("--force", action="store_true", help="Re-crawl rows whose Hosts Circles is already set.")
    p.add_argument("--sleep", type=float, default=0.4, help="Seconds between HTTP fetches.")
    p.add_argument("--sleep-write", type=float, default=0.3, help="Seconds between Sheets writes.")
    p.add_argument("--max-chars", type=int, default=80000, help="Per-page text truncation cap.")
    p.add_argument(
        "--no-promote",
        action="store_true",
        help="Disable ALL promotion/rescue when Hosts Circles=Yes. Prevents Research → AI: Enrich with contact, and prevents rescue of AI: Photo rejected / AI: Enrich — manual / AI: Photo needs review rows.",
    )
    p.add_argument(
        "--no-rescue-rejected",
        action="store_true",
        help="Disable re-evaluation of AI: Photo rejected rows. Default is to "
        "rescue: crawl their sites and promote any whose Hosts Circles comes "
        "back as Yes. Default-on so existing photo-rejected rows (which were "
        "never crawled by site keyword) get re-evaluated under the new criteria.",
    )
    p.add_argument(
        "--no-reject-no-signal",
        action="store_true",
        help="Disable Research -> AI: Photo rejected when the site crawl "
        "succeeds but finds no qualifying keywords. Default is to reject — "
        "this is the simplification that retires the photo+Grok rubric "
        "(which used to gate Research -> rejected). Pass this flag to keep "
        "no-signal rows in Research for manual triage.",
    )
    args = p.parse_args()

    gc = gspread_client()
    ws = gc.open_by_key(SPREADSHEET_ID).worksheet(HIT_LIST_WS)
    rows = ws.get_all_values()
    if len(rows) < 2:
        print("No data rows.")
        return
    header = [str(x or "").strip() for x in rows[0]]

    def col(name: str) -> int:
        if name not in header:
            raise SystemExit(f"Hit List missing required column {name!r}.")
        return header.index(name)

    i_shop = col("Shop Name")
    i_web = col("Website")
    i_status = col("Status")
    i_email = header.index("Email") if "Email" in header else -1
    i_hc = ensure_hosts_circles_column(ws, header, args.dry_run)
    remark_ws = gc.open_by_key(SPREADSHEET_ID).worksheet(DAPP_REMARKS_WS) if not args.no_promote else None
    rescue_rejected = not args.no_rescue_rejected
    reject_no_signal = not args.no_reject_no_signal

    def row_has_email(cells: list[str]) -> bool:
        if i_email < 0:
            return False
        v = cells[i_email].strip() if i_email < len(cells) else ""
        return bool(v) and "@" in v

    queued: list[int] = []
    for ri, row in enumerate(rows[1:], start=2):
        cells = row + [""] * (len(header) - len(row))
        site = cells[i_web].strip()
        if not site:
            continue
        cur = cells[i_hc].strip() if i_hc < len(cells) else ""
        if cur and not args.force:
            continue
        queued.append(ri)
        if len(queued) >= max(1, args.limit):
            break

    print(
        f"Crawling {len(queued)} row(s). dry_run={args.dry_run} force={args.force}",
        flush=True,
    )

    yes_count = 0
    nd_count = 0
    skip_count = 0
    promote_count = 0
    rescue_count = 0
    reject_count = 0
    for ri in queued:
        cells = rows[ri - 1] + [""] * (len(header) - len(rows[ri - 1]))
        shop = cells[i_shop].strip()
        site = cells[i_web].strip()
        cur_status = cells[i_status].strip()
        has_email = row_has_email(cells)
        ok, hits = crawl_site(site, sleep_s=args.sleep, max_chars=args.max_chars)
        if not ok:
            print(f"  row {ri} {shop!r}: site unreachable — leaving blank for retry", flush=True)
            skip_count += 1
            continue
        if hits:
            value = f"Yes ({', '.join(hits)})"
            yes_count += 1
        else:
            value = "Not detected"
            nd_count += 1
        print(f"  row {ri} {shop!r}: {value}", flush=True)
        if not args.dry_run:
            ws.update(
                range_name=rowcol_to_a1(ri, i_hc + 1),
                values=[[value]],
                value_input_option="USER_ENTERED",
            )
            time.sleep(max(0.0, args.sleep_write))

        if hits and not args.no_promote:
            if cur_status == PROMOTABLE_FROM_RESEARCH:
                promote_row_to_enrichment(
                    ws, remark_ws, ri, shop, hits,
                    rescue=False, dry_run=args.dry_run, has_email=has_email,
                )
                promote_count += 1
                if not args.dry_run:
                    time.sleep(max(0.0, args.sleep_write))
            elif cur_status in (PROMOTABLE_FROM_REJECTED, PROMOTABLE_FROM_MANUAL, PROMOTABLE_FROM_NEEDS_REVIEW):
                # Rescue dead-end rows: photo-rejected, enrichment-gave-up, or
                # photo-needs-review. All three are stuck states where a clear
                # circle-hosting signal on the website is strong enough to
                # fast-track back into the pipeline.
                if cur_status == PROMOTABLE_FROM_REJECTED and not rescue_rejected:
                    pass  # user opted out of rejected rescue
                else:
                    promote_row_to_enrichment(
                        ws, remark_ws, ri, shop, hits,
                        rescue=True, dry_run=args.dry_run, has_email=has_email,
                    )
                    rescue_count += 1
                    if not args.dry_run:
                        time.sleep(max(0.0, args.sleep_write))
        elif not hits and reject_no_signal and cur_status == PROMOTABLE_FROM_RESEARCH and not args.no_promote:
            # Site crawled OK + zero matches → mark as photo-rejected
            # (the status name is preserved for back-compat with downstream
            # filters; meaning under new model is "site shows no qualifying
            # signals," which retires the photo+Grok rubric).
            reject_row_no_signal(ws, remark_ws, ri, shop, dry_run=args.dry_run)
            reject_count += 1
            if not args.dry_run:
                time.sleep(max(0.0, args.sleep_write))

    # Post-crawl sweep: promote any row whose Hosts Circles is already "Yes" but
    # whose Status hasn't been promoted yet (covers rows whose Hosts Circles was set
    # in a prior run before the promotion logic existed, or the --rescue-rejected case).
    swept_promote = 0
    swept_rescue = 0
    if not args.no_promote:
        rows = ws.get_all_values()  # re-read to see fresh writes from this run
        for ri, raw in enumerate(rows[1:], start=2):
            row = list(raw) + [""] * (len(header) - len(raw))
            hc = row[i_hc].strip() if i_hc < len(row) else ""
            if not hc.lower().startswith("yes"):
                continue
            status = row[i_status].strip()
            shop = row[i_shop].strip()
            has_email = row_has_email(row)
            matched = []
            m = re.match(r"^Yes\s*\((.*)\)\s*$", hc, re.IGNORECASE)
            if m:
                matched = [s.strip() for s in m.group(1).split(",") if s.strip()]
            if status == PROMOTABLE_FROM_RESEARCH:
                promote_row_to_enrichment(
                    ws, remark_ws, ri, shop, matched,
                    rescue=False, dry_run=args.dry_run, has_email=has_email,
                )
                swept_promote += 1
                if not args.dry_run:
                    time.sleep(max(0.0, args.sleep_write))
            elif status in (PROMOTABLE_FROM_REJECTED, PROMOTABLE_FROM_MANUAL, PROMOTABLE_FROM_NEEDS_REVIEW):
                if status == PROMOTABLE_FROM_REJECTED and not rescue_rejected:
                    pass
                else:
                    promote_row_to_enrichment(
                        ws, remark_ws, ri, shop, matched,
                        rescue=True, dry_run=args.dry_run, has_email=has_email,
                    )
                    swept_rescue += 1
                    if not args.dry_run:
                        time.sleep(max(0.0, args.sleep_write))

    print(
        f"Done. yes={yes_count} not_detected={nd_count} unreachable_skip={skip_count} "
        f"promote_research={promote_count} rescue_rejected={rescue_count} "
        f"reject_no_signal={reject_count} "
        f"sweep_promote={swept_promote} sweep_rescue={swept_rescue} "
        f"dry_run={args.dry_run} force={args.force} "
        f"rescue_rejected={rescue_rejected} reject_no_signal={reject_no_signal}",
        flush=True,
    )


if __name__ == "__main__":
    main()
