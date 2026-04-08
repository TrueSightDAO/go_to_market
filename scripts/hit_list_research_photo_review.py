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
    det = place_details(key, place_id)
    if det.get("status") != "OK":
        raise RuntimeError(det)
    photos = (det.get("result") or {}).get("photos") or []
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    url = "https://maps.googleapis.com/maps/api/place/photo"
    for i, ph in enumerate(photos[:max_n]):
        ref = ph["photo_reference"]
        r = requests.get(
            url,
            params={"maxwidth": PLACES_MAX_WIDTH, "photo_reference": ref, "key": key},
            timeout=60,
            allow_redirects=True,
        )
        r.raise_for_status()
        ext = ".jpg" if "jpeg" in (r.headers.get("Content-Type") or "").lower() else ".bin"
        p = out_dir / f"photo_{i + 1}{ext}"
        p.write_bytes(r.content)
        paths.append(p)
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

    paras.append(
        f"Model summary ({GROK_MODEL})\n{rationale}\n\n"
        f"Suggested Hit List status: {status} (confidence {conf:.2f}).\n"
        "A teammate should confirm or change status using their own judgment."
    )

    return "\n\n".join(paras)


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
    if not paths:
        raise RuntimeError("No photos downloaded")

    ctx = f"Shop: {name}. Address: {addr}, {city}, {state}. place_id: {place_id}."
    grok = grok_photo_rubric(paths, ctx)
    ai_status = (grok.get("recommended_hit_list_status") or "").strip()
    if ai_status not in ("AI: Shortlisted", "AI: Photo rejected", "AI: Photo needs review"):
        ai_status = "AI: Photo needs review"

    remarks = format_remarks_column_d(name, addr, city, state, place_id, len(paths), grok)
    submission_id = str(uuid.uuid4())
    submitted_at = datetime.now(timezone.utc).strftime("%m/%d/%Y %H:%M:%S")

    manifest = {
        "submission_id": submission_id,
        "shop": name,
        "hit_list_row": sheet_row,
        "place_id": place_id,
        "photos": [p.name for p in paths],
        "grok": grok,
    }
    (out_dir / "last_run.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"[{name}] place_id={place_id} photos={len(paths)} -> {ai_status}")

    if dry_run:
        print("--- Remarks (preview) ---")
        print(remarks)
        return

    r_headers = remark_ws.row_values(1)
    row_out = []
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
            row_out.append(SUBMITTED_BY_LABEL)
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
        SUBMITTED_BY_LABEL,
        submitted_at,
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
    args = p.parse_args()

    gc = gspread_client()
    sh = gc.open_by_key(SPREADSHEET_ID)
    hit_ws = sh.worksheet(HIT_LIST)
    remark_ws = sh.worksheet(DAPP_REMARKS)

    targets = collect_target_rows(hit_ws, max(1, args.limit), args.shop)
    if not targets:
        print("No matching Hit List rows (Status=Research, or use --shop).")
        return

    for i, (sheet_row, fields) in enumerate(targets):
        try:
            run_one_shop(hit_ws, remark_ws, sheet_row, fields, args.max_photos, args.dry_run)
        except Exception as exc:
            print(f"ERROR row {sheet_row} {fields.get('Shop Name')!r}: {exc}", flush=True)
            raise
        if i + 1 < len(targets):
            time.sleep(SLEEP_BETWEEN_SHOPS_SEC)

    print("Done.")


if __name__ == "__main__":
    main()