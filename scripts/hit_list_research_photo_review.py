#!/usr/bin/env python3
"""
For holistic wellness Hit List shops: pull Google Places photos, run Grok vision rubric,
append a human-readable **DApp Remarks** row (column **Remarks** uses paragraphs / bullets),
update **Hit List** Status (AI: Shortlisted | AI: Photo rejected | AI: Photo needs review),
append **Sales Process Notes**, and mark the remark processed—same net effect as
`physical_stores/process_dapp_remarks.py` but **one shop at a time** (avoids bulk quota storms).

Default row filter: **Status == Research**. If **--shop** is set, that shop is processed
regardless of status (for retargeting or demos).

Environment:
  - market_research/google_credentials.json (Sheets)
  - GOOGLE_MAPS_API_KEY (or GOOGLE_PLACES_API_KEY) in .env or env
  - GROK_API_KEY in .env or env

Usage:
  cd market_research
  python3 scripts/hit_list_research_photo_review.py --limit 3
  python3 scripts/hit_list_research_photo_review.py --shop \"Naturales Elementa Apothecary\"
  python3 scripts/hit_list_research_photo_review.py --dry-run --limit 1
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import gspread
import requests
from google.oauth2.service_account import Credentials
from gspread.utils import rowcol_to_a1

REPO = Path(__file__).resolve().parents[1]
SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
HIT_LIST = "Hit List"
DAPP_REMARKS = "DApp Remarks"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

GROK_ENDPOINT = "https://api.x.ai/v1/chat/completions"
GROK_MODEL = "grok-4-1-fast-non-reasoning"
SUBMITTED_BY_LABEL = "Grok photo scan (Google Places)"
SUBMITTED_BY_NO_PHOTOS = "Hit List photo automation (no Places images)"
SUBMITTED_BY_ERROR = "Hit List photo automation (run error)"
MAX_PHOTOS_DEFAULT = 5
PLACES_MAX_WIDTH = 1200
SLEEP_BETWEEN_SHOPS_SEC = 3


def load_dotenv_repo() -> None:
    env_path = REPO / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
    except ImportError:
        pass


def maps_api_key() -> str:
    load_dotenv_repo()
    k = os.environ.get("GOOGLE_MAPS_API_KEY") or os.environ.get("GOOGLE_PLACES_API_KEY")
    if not k:
        raise SystemExit(
            "Set GOOGLE_MAPS_API_KEY (or GOOGLE_PLACES_API_KEY) in market_research/.env or the environment."
        )
    return k


def grok_api_key() -> str:
    load_dotenv_repo()
    k = os.environ.get("GROK_API_KEY")
    if not k:
        raise SystemExit("Set GROK_API_KEY in market_research/.env or the environment.")
    return k


def gspread_client() -> gspread.Client:
    creds_path = REPO / "google_credentials.json"
    if not creds_path.is_file():
        raise SystemExit(f"Missing service account JSON: {creds_path}")
    creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
    return gspread.authorize(creds)


def find_place(key: str, text: str, lat: float | None, lng: float | None, radius_m: float) -> dict:
    url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    params: dict[str, Any] = {
        "input": text,
        "inputtype": "textquery",
        "fields": "place_id,name,formatted_address,geometry",
        "key": key,
    }
    if lat is not None and lng is not None:
        params["locationbias"] = f"circle:{int(radius_m)}@{lat},{lng}"
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def place_details(key: str, place_id: str) -> dict:
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    fields = (
        "place_id,name,formatted_address,geometry,photos,"
        "business_status,rating,user_ratings_total,url"
    )
    r = requests.get(
        url, params={"place_id": place_id, "fields": fields, "key": key}, timeout=30
    )
    r.raise_for_status()
    return r.json()


def download_place_photos(key: str, place_id: str, out_dir: Path, max_n: int) -> list[Path]:
    """Download up to max_n Place Photos. Skips failed refs / HTTP errors; returns 0..max_n paths."""
    det = place_details(key, place_id)
    if det.get("status") != "OK":
        raise RuntimeError(det)
    photos = (det.get("result") or {}).get("photos") or []
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    url = "https://maps.googleapis.com/maps/api/place/photo"
    for i, ph in enumerate(photos[:max_n]):
        ref = ph.get("photo_reference")
        if not ref:
            continue
        saved = False
        for maxwidth in (PLACES_MAX_WIDTH, 800, 400):
            try:
                r = requests.get(
                    url,
                    params={"maxwidth": maxwidth, "photo_reference": ref, "key": key},
                    timeout=60,
                    allow_redirects=True,
                )
                r.raise_for_status()
                if len(r.content or b"") < 200:
                    continue
                ext = ".jpg" if "jpeg" in (r.headers.get("Content-Type") or "").lower() else ".bin"
                p = out_dir / f"photo_{len(paths) + 1}{ext}"
                p.write_bytes(r.content)
                paths.append(p)
                saved = True
                break
            except requests.RequestException:
                continue
        if not saved:
            print(
                f"  (warn) Place Photo skip ref …{str(ref)[-8:]} index {i + 1}",
                flush=True,
            )
    return paths


def grok_photo_rubric(
    image_paths: list[Path],
    shop_context: str,
) -> dict[str, Any]:
    """Return parsed JSON with recommended_hit_list_status, confidence, positives, negatives, rationale."""
    api_key = grok_api_key()
    user_parts: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"{shop_context}\n\n"
                "You are scoring Google Maps photos for a holistic wellness / ceremonial cacao "
                "retail partner (Apothecary, bulk herbs, metaphysical-adjacent, health food — "
                "not convenience, liquor-primary, fast food).\n\n"
                "Return ONE JSON object only (no markdown), keys:\n"
                '- recommended_hit_list_status: exactly one of '
                '"AI: Shortlisted" | "AI: Photo rejected" | "AI: Photo needs review"\n'
                "- confidence: number 0.0-1.0\n"
                "- positives: array of short strings\n"
                "- negatives: array of short strings\n"
                "- rationale: one concise paragraph\n\n"
                "If images conflict or are unclear, prefer AI: Photo needs review."
            ),
        }
    ]
    for p in image_paths:
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        user_parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"},
            }
        )

    r = requests.post(
        GROK_ENDPOINT,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": GROK_MODEL,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": "You analyze retail photos. Output valid JSON only."},
                {"role": "user", "content": user_parts},
            ],
        },
        timeout=180,
    )
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"]
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise RuntimeError(f"No JSON in Grok response: {text[:500]}")
    return json.loads(m.group())


def format_remarks_column_d(
    shop_name: str,
    address: str,
    city: str,
    state: str,
    place_id: str,
    photo_count: int,
    grok: dict[str, Any],
) -> str:
    """Human-readable paragraphs for DApp Remarks column (newlines render in Sheets when wrapping is on)."""
    positives = grok.get("positives") or []
    negatives = grok.get("negatives") or []
    rationale = (grok.get("rationale") or "").strip()
    status = (grok.get("recommended_hit_list_status") or "").strip()
    try:
        conf = float(grok.get("confidence", 0))
    except (TypeError, ValueError):
        conf = 0.0

    loc_bits = [shop_name]
    line2 = ", ".join(
        p for p in [address.strip(), " ".join(x for x in [city.strip(), state.strip()] if x)] if p
    )
    if line2:
        loc_bits.append(line2)

    paras: list[str] = []
    paras.append("Location\n" + "\n".join(loc_bits))

    if photo_count == 0:
        paras.append(
            "Google Places review\n"
            f"No usable public listing photos were downloaded from Google Places for place_id {place_id}. "
            "The listing may have no photos, or every photo request failed (quota, key restriction, or transient error). "
            "This run cannot score visual fit without images.\n\n"
            "Use Google Maps or an in-person visit to assess the storefront."
        )
    else:
        paras.append(
            "Google Places review\n"
            f"We reviewed {photo_count} public listing photos from Google Places (max width {PLACES_MAX_WIDTH}px) "
            f"for place_id {place_id}.\n\n"
            "This is an automated visual pass only. It does not replace an in-person visit or a conversation "
            "with the buyer."
        )

    if positives:
        paras.append("What looks like a fit\n" + "\n".join(f"• {p}" for p in positives))

    if negatives:
        paras.append("Watchouts or conflicts\n" + "\n".join(f"• {n}" for n in negatives))

    model_label = (
        "No vision model run (0 images)" if photo_count == 0 else f"Model summary ({GROK_MODEL})"
    )
    paras.append(
        f"{model_label}\n{rationale}\n\n"
        f"Suggested Hit List status: {status} (confidence {conf:.2f}).\n"
        "A teammate should confirm or change status using their own judgment."
    )

    if status == "AI: Photo needs review":
        why_lines: list[str] = []
        if photo_count == 0:
            why_lines.append(
                "• No usable Google Places listing photos in this run, so storefront fit could not be scored from images."
            )
        else:
            why_lines.append(
                f"• After {photo_count} photo(s), the vision model did not confidently shortlist or reject "
                f"(confidence {conf:.2f})."
            )
        if negatives:
            why_lines.append("• Model-flagged watchouts:")
            why_lines.extend(f"  – {n}" for n in negatives)
        elif photo_count > 0:
            why_lines.append(
                "• No watchout bullets were returned; use the model rationale above or review the listing on Google Maps."
            )
        paras.append("Why human review\n" + "\n".join(why_lines))

    return "\n\n".join(paras)


def format_run_error_remarks(
    shop_name: str,
    address: str,
    city: str,
    state: str,
    exc: BaseException,
) -> str:
    msg = str(exc).strip() or exc.__class__.__name__
    if len(msg) > 1200:
        msg = msg[:1200] + "…"
    loc_lines = [shop_name or "(unknown shop)"]
    line2 = ", ".join(
        p for p in [address.strip(), " ".join(x for x in [city.strip(), state.strip()] if x)] if p
    )
    if line2:
        loc_lines.append(line2)
    return (
        "Location\n" + "\n".join(loc_lines) + "\n\n"
        "Automation error\n"
        "The hourly Hit List photo review job hit an exception for this row (Places lookup, "
        "photo download, Grok, or Sheets write). No reliable vision score was produced.\n\n"
        f"Error (trimmed):\n{msg}\n\n"
        "Suggested Hit List status: AI: Photo needs review — retry manually, fix API access, "
        "or disqualify the lead.\n\n"
        "Status was set to AI: Photo needs review so the row does not stay in Research "
        "and repeat on the next run (saves Grok/Places usage).\n\n"
        "Why human review\n"
        "• The automation failed before a vision score could be saved (see Automation error above). "
        "Triage manually: retry this row, fix credentials or quotas, or drop the lead if it is a bad match."
    )


def append_dapp_remark_and_apply(
    hit_ws: gspread.Worksheet,
    remark_ws: gspread.Worksheet,
    sheet_row: int,
    name: str,
    ai_status: str,
    remarks: str,
    submitted_by: str,
    submitted_at: str,
    submission_id: str,
) -> None:
    """Append one DApp Remarks row and sync Status / Sales Process Notes on Hit List."""
    r_headers = remark_ws.row_values(1)
    row_out: list[str] = []
    for h in r_headers:
        if h == "Submission ID":
            row_out.append(submission_id)
        elif h == "Shop Name":
            row_out.append(name)
        elif h == "Status":
            row_out.append(ai_status)
        elif h == "Remarks":
            row_out.append(remarks)
        elif h == "Submitted By":
            row_out.append(submitted_by)
        elif h == "Submitted At":
            row_out.append(submitted_at)
        elif h == "Processed":
            row_out.append("")
        elif h == "Processed At":
            row_out.append("")
        else:
            row_out.append("")
    remark_ws.append_row(row_out, value_input_option="USER_ENTERED")
    time.sleep(1.5)
    apply_remark_to_hit_list(
        hit_ws,
        remark_ws,
        sheet_row,
        submission_id,
        name,
        ai_status,
        remarks,
        submitted_by,
        submitted_at,
    )


def record_run_error(
    hit_ws: gspread.Worksheet,
    remark_ws: gspread.Worksheet,
    sheet_row: int,
    fields: dict[str, Any],
    exc: BaseException,
    dry_run: bool,
) -> None:
    """Set Hit List to AI: Photo needs review and log error to DApp Remarks (unless dry_run)."""
    name = (fields.get("Shop Name") or "").strip() or "(unknown shop)"
    addr = (fields.get("Address") or "").strip()
    city = (fields.get("City") or "").strip()
    state = (fields.get("State") or "").strip()
    remarks = format_run_error_remarks(name, addr, city, state, exc)
    ai_status = "AI: Photo needs review"
    submission_id = str(uuid.uuid4())
    submitted_at = datetime.now(timezone.utc).strftime("%m/%d/%Y %H:%M:%S")
    print(f"[{name}] RUN ERROR -> {ai_status} (failure logged; leaves Research queue)", flush=True)
    if dry_run:
        print("--- Error remarks (preview) ---", flush=True)
        print(remarks, flush=True)
        return
    append_dapp_remark_and_apply(
        hit_ws,
        remark_ws,
        sheet_row,
        name,
        ai_status,
        remarks,
        SUBMITTED_BY_ERROR,
        submitted_at,
        submission_id,
    )


def append_sales_note(existing: str, note_line: str) -> str:
    if not existing or not str(existing).strip():
        return note_line
    return f"{str(existing).strip()}\n\n{note_line}"


def find_remark_row_by_submission(ws: gspread.Worksheet, submission_id: str) -> int | None:
    vals = ws.get_all_values()
    headers = vals[0]
    try:
        sid_idx = headers.index("Submission ID")
    except ValueError:
        return None
    for rn, row in enumerate(vals[1:], start=2):
        if len(row) > sid_idx and row[sid_idx].strip() == submission_id:
            return rn
    return None


def apply_remark_to_hit_list(
    hit_ws: gspread.Worksheet,
    remark_ws: gspread.Worksheet,
    hit_row: int,
    submission_id: str,
    _shop_name: str,
    status: str,
    remarks: str,
    submitted_by: str,
    submitted_at: str,
) -> None:
    hit_vals = hit_ws.get_all_values()
    headers = hit_vals[0]
    hidx = {h: i for i, h in enumerate(headers)}
    for col in ("Status", "Sales Process Notes", "Status Updated By", "Status Updated Date"):
        if col not in hidx:
            raise ValueError(f'Hit List missing column "{col}"')

    now_iso = datetime.now(timezone.utc).isoformat()
    note_prefix = f"[{submitted_at} | {submitted_by}]" if submitted_at else f"[{now_iso} | {submitted_by}]"
    note_line = f"{note_prefix} {remarks}"
    existing_notes = hit_ws.cell(hit_row, hidx["Sales Process Notes"] + 1).value or ""
    new_notes = append_sales_note(str(existing_notes), note_line)

    c_status = hidx["Status"] + 1
    c_notes = hidx["Sales Process Notes"] + 1
    c_by = hidx["Status Updated By"] + 1
    c_dt = hidx["Status Updated Date"] + 1

    hit_ws.batch_update(
        [
            {"range": rowcol_to_a1(hit_row, c_status), "values": [[status]]},
            {"range": rowcol_to_a1(hit_row, c_notes), "values": [[new_notes]]},
            {"range": rowcol_to_a1(hit_row, c_by), "values": [[submitted_by]]},
            {"range": rowcol_to_a1(hit_row, c_dt), "values": [[now_iso]]},
        ],
        value_input_option="USER_ENTERED",
    )

    ridx_row = find_remark_row_by_submission(remark_ws, submission_id)
    if not ridx_row:
        raise RuntimeError(f"Could not find DApp Remarks row for submission {submission_id}")
    r_headers = remark_ws.row_values(1)
    ridx = {h: i for i, h in enumerate(r_headers)}
    remark_ws.batch_update(
        [
            {"range": rowcol_to_a1(ridx_row, ridx["Processed"] + 1), "values": [["Yes"]]},
            {"range": rowcol_to_a1(ridx_row, ridx["Processed At"] + 1), "values": [[now_iso]]},
        ],
        value_input_option="USER_ENTERED",
    )


def collect_target_rows(
    hit_ws: gspread.Worksheet,
    limit: int,
    shop_filter: str | None,
) -> list[tuple[int, dict[str, Any]]]:
    """Return list of (1-based sheet row, fields dict)."""
    rows = hit_ws.get_all_values()
    headers = rows[0]
    idx = {h: i for i, h in enumerate(headers)}
    need = ["Shop Name", "Status", "Address", "City", "State"]
    for n in need:
        if n not in idx:
            raise ValueError(f"Hit List missing column {n}")
    lat_k = "Latitude" if "Latitude" in idx else None
    lng_k = "Longitude" if "Longitude" in idx else None

    out: list[tuple[int, dict[str, Any]]] = []
    sf = (shop_filter or "").strip().lower()

    for rn, row in enumerate(rows[1:], start=2):
        cells = row + [""] * (len(headers) - len(row))
        name = cells[idx["Shop Name"]].strip()
        if not name:
            continue
        status = cells[idx["Status"]].strip()

        if sf:
            if sf not in name.lower() and name.lower() != sf:
                continue
        else:
            if status != "Research":
                continue

        lat_s = cells[idx[lat_k]].strip() if lat_k else ""
        lng_s = cells[idx[lng_k]].strip() if lng_k else ""
        lat: float | None = None
        lng: float | None = None
        if lat_s and lng_s:
            try:
                lat = float(lat_s)
                lng = float(lng_s)
            except ValueError:
                pass

        fields = {
            "Shop Name": name,
            "Status": status,
            "Address": cells[idx["Address"]].strip(),
            "City": cells[idx["City"]].strip(),
            "State": cells[idx["State"]].strip(),
            "lat": lat_s,
            "lng": lng_s,
            "_lat_float": lat,
            "_lng_float": lng,
        }
        out.append((rn, fields))
        if len(out) >= limit:
            break
    return out


def run_one_shop(
    hit_ws: gspread.Worksheet,
    remark_ws: gspread.Worksheet,
    sheet_row: int,
    fields: dict[str, Any],
    max_photos: int,
    dry_run: bool,
) -> None:
    mkey = maps_api_key()
    name = fields["Shop Name"]
    addr = fields["Address"]
    city = fields["City"]
    state = fields["State"]
    lat_f = fields.get("_lat_float")
    lng_f = fields.get("_lng_float")
    query = f"{name} {addr} {city} {state}".strip()

    find_json = find_place(
        mkey,
        query,
        lat_f if isinstance(lat_f, float) else None,
        lng_f if isinstance(lng_f, float) else None,
        500.0,
    )
    st = find_json.get("status")
    if st not in ("OK",):
        raise RuntimeError(f"Places find failed: {find_json}")
    cands = find_json.get("candidates") or []
    if not cands:
        raise RuntimeError(f"No Places candidates for {name!r}")
    place_id = cands[0].get("place_id")
    if not place_id:
        raise RuntimeError("No place_id")

    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_").lower()[:80]
    out_dir = REPO / "data" / "place_photos" / slug
    paths = download_place_photos(mkey, place_id, out_dir, max_photos)

    if paths:
        ctx = f"Shop: {name}. Address: {addr}, {city}, {state}. place_id: {place_id}."
        grok = grok_photo_rubric(paths, ctx)
        ai_status = (grok.get("recommended_hit_list_status") or "").strip()
        if ai_status not in ("AI: Shortlisted", "AI: Photo rejected", "AI: Photo needs review"):
            ai_status = "AI: Photo needs review"
        photo_count = len(paths)
    else:
        grok = {
            "recommended_hit_list_status": "AI: Photo needs review",
            "confidence": 0.0,
            "positives": [],
            "negatives": [
                "No Google Places listing photos were returned, or every photo download failed for this run."
            ],
            "rationale": (
                "Automation could not obtain storefront images from the Places API, so visual fit was not scored. "
                "Confirm on Google Maps or in person."
            ),
        }
        ai_status = "AI: Photo needs review"
        photo_count = 0
        print(f"[{name}] place_id={place_id} photos=0 -> {ai_status} (no images; remarks only)", flush=True)

    remarks = format_remarks_column_d(name, addr, city, state, place_id, photo_count, grok)
    submission_id = str(uuid.uuid4())
    submitted_at = datetime.now(timezone.utc).strftime("%m/%d/%Y %H:%M:%S")
    submitted_by = SUBMITTED_BY_LABEL if paths else SUBMITTED_BY_NO_PHOTOS

    manifest = {
        "submission_id": submission_id,
        "shop": name,
        "hit_list_row": sheet_row,
        "place_id": place_id,
        "photos": [p.name for p in paths],
        "grok": grok,
    }
    (out_dir / "last_run.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if paths:
        print(f"[{name}] place_id={place_id} photos={len(paths)} -> {ai_status}", flush=True)

    if dry_run:
        print("--- Remarks (preview) ---")
        print(remarks)
        return

    append_dapp_remark_and_apply(
        hit_ws,
        remark_ws,
        sheet_row,
        name,
        ai_status,
        remarks,
        submitted_by,
        submitted_at,
        submission_id,
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Hit List Research / targeted shop: Places photos + Grok + DApp Remarks.")
    p.add_argument("--limit", type=int, default=5, help="Max shops per run (default 5).")
    p.add_argument(
        "--shop",
        type=str,
        default=None,
        help="Process this shop name (substring match, case-insensitive). Ignores Research filter.",
    )
    p.add_argument("--max-photos", type=int, default=MAX_PHOTOS_DEFAULT, help="Place photos to fetch (default 5).")
    p.add_argument("--dry-run", action="store_true", help="Do not write Sheets; print remarks preview.")
    p.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop the whole run on the first shop error (default: skip bad rows and continue).",
    )
    p.add_argument(
        "--strict-exit",
        action="store_true",
        help="Exit with code 1 if any shop in the batch raised (for CI alerting). Default: exit 0 so partial success keeps the job green.",
    )
    args = p.parse_args()

    gc = gspread_client()
    sh = gc.open_by_key(SPREADSHEET_ID)
    hit_ws = sh.worksheet(HIT_LIST)
    remark_ws = sh.worksheet(DAPP_REMARKS)

    targets = collect_target_rows(hit_ws, max(1, args.limit), args.shop)
    if not targets:
        print("No matching Hit List rows (Status=Research, or use --shop).")
        return

    failed = 0
    for i, (sheet_row, fields) in enumerate(targets):
        try:
            run_one_shop(hit_ws, remark_ws, sheet_row, fields, args.max_photos, args.dry_run)
        except Exception as exc:
            print(f"ERROR row {sheet_row} {fields.get('Shop Name')!r}: {exc}", flush=True)
            try:
                record_run_error(
                    hit_ws,
                    remark_ws,
                    sheet_row,
                    fields,
                    exc,
                    dry_run=args.dry_run,
                )
            except Exception as rec_exc:
                print(
                    f"Could not persist failure state for row {sheet_row}: {rec_exc}",
                    flush=True,
                )
            failed += 1
            if args.fail_fast:
                raise
            continue
        if i + 1 < len(targets):
            time.sleep(SLEEP_BETWEEN_SHOPS_SEC)

    print(f"Done. Shops in batch: {len(targets)}, failed: {failed}.")
    if failed:
        print(
            f"WARNING: {failed} shop(s) hit errors; others completed. "
            "See ERROR lines above. Use --strict-exit to fail CI on any error.",
            flush=True,
        )
    if args.strict_exit and failed:
        sys.exit(1)


if __name__ == "__main__":
    main()