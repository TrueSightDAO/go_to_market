#!/usr/bin/env python3
"""
Expand buyer-intent keyword seeds via DataForSEO (Google Ads keyword ideas API).

Loads DATAFORSEO_LOGIN + DATAFORSEO_PASSWORD from market_research/.env (or env).

Docs: https://docs.dataforseo.com/v3/keywords_data/google_ads/keywords_for_keywords/live/

Usage (from market_research/):
  python3 scripts/dataforseo_buyer_intent_keywords.py
  python3 scripts/dataforseo_buyer_intent_keywords.py --location-name "United States"
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

API_URL = "https://api.dataforseo.com/v3/keywords_data/google_ads/keywords_for_keywords/live"

# US default (DataForSEO location_code for United States)
DEFAULT_LOCATION_CODE = 2840

# Buyer-intent seeds for Agroverse (ceremonial cacao, nibs, Brazil/regenerative story).
DEFAULT_SEEDS = [
    "ceremonial cacao",
    "buy ceremonial cacao",
    "organic cacao nibs",
    "cacao nibs organic",
    "ceremonial grade cacao",
    "bulk cacao nibs",
    "brazilian cacao",
    "single origin cacao",
    "amazon rainforest cacao",
    "fair trade cacao",
    "wholesale cacao",
    "cacao paste ceremonial",
    "regenerative cacao",
]

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent


def load_credentials() -> tuple[str, str]:
    load_dotenv(_REPO_ROOT / ".env", override=False)
    load_dotenv(_REPO_ROOT / ".env.local", override=False)
    login = os.environ.get("DATAFORSEO_LOGIN", "").strip()
    password = os.environ.get("DATAFORSEO_PASSWORD", "").strip()
    if not login or not password:
        sys.exit(
            "Set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD in market_research/.env "
            "(see agentic_ai_context/DATAFORSEO_API_WORKFLOW.md)."
        )
    return login, password


def fetch_keywords_for_keywords(
    login: str,
    password: str,
    keywords: list[str],
    *,
    location_code: int | None,
    location_name: str | None,
    language_code: str,
    sort_by: str,
) -> dict:
    payload: list[dict] = [{}]
    task = payload[0]
    task["keywords"] = keywords[:20]
    task["language_code"] = language_code
    task["sort_by"] = sort_by
    if location_name:
        task["location_name"] = location_name
    elif location_code is not None:
        task["location_code"] = location_code
    resp = requests.post(
        API_URL,
        json=payload,
        auth=(login, password),
        headers={"Content-Type": "application/json"},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def rows_from_response(data: dict) -> list[dict]:
    out: list[dict] = []
    for task in data.get("tasks") or []:
        for block in task.get("result") or []:
            if not isinstance(block, dict):
                continue
            out.append(
                {
                    "keyword": block.get("keyword") or "",
                    "search_volume": block.get("search_volume"),
                    "competition": block.get("competition"),
                    "competition_index": block.get("competition_index"),
                    "cpc": block.get("cpc"),
                    "low_top_of_page_bid": block.get("low_top_of_page_bid"),
                    "high_top_of_page_bid": block.get("high_top_of_page_bid"),
                }
            )
    return out


def dedupe_sort(rows: list[dict]) -> list[dict]:
    by_kw: dict[str, dict] = {}
    for r in rows:
        k = (r.get("keyword") or "").strip().lower()
        if not k:
            continue
        prev = by_kw.get(k)
        if prev is None:
            by_kw[k] = r
            continue
        pv = prev.get("search_volume")
        cv = r.get("search_volume")
        if cv is not None and (pv is None or cv > pv):
            by_kw[k] = r
    def sort_key(r: dict):
        v = r.get("search_volume")
        return (0 if v is not None else 1, -(v or 0))
    return sorted(by_kw.values(), key=sort_key)


def main() -> None:
    p = argparse.ArgumentParser(description="DataForSEO buyer-intent keyword expansion")
    p.add_argument(
        "--location-code",
        type=int,
        default=None,
        help=f"DataForSEO location_code (default: {DEFAULT_LOCATION_CODE} if no --location-name)",
    )
    p.add_argument(
        "--location-name",
        default=None,
        help='e.g. "United States" (overrides location-code)',
    )
    p.add_argument("--language-code", default="en")
    p.add_argument(
        "--sort-by",
        default="search_volume",
        choices=["relevance", "search_volume", "competition_index", "low_top_of_page_bid", "high_top_of_page_bid"],
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=_REPO_ROOT / "output" / "dataforseo",
    )
    args = p.parse_args()

    loc_code = args.location_code
    if args.location_name is None and loc_code is None:
        loc_code = DEFAULT_LOCATION_CODE

    login, password = load_credentials()
    print("Calling DataForSEO keywords_for_keywords (live)…", flush=True)
    data = fetch_keywords_for_keywords(
        login,
        password,
        DEFAULT_SEEDS,
        location_code=loc_code,
        location_name=args.location_name,
        language_code=args.language_code,
        sort_by=args.sort_by,
    )

    code = data.get("status_code")
    if code != 20000:
        sys.exit(f"API error status_code={code} message={data.get('status_message')!r}")

    cost = data.get("cost")
    print(f"API status OK. tasks_cost≈${cost}", flush=True)

    rows = dedupe_sort(rows_from_response(data))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = args.out_dir / f"buyer_intent_keywords_{stamp}.csv"
    fields = [
        "keyword",
        "search_volume",
        "competition",
        "competition_index",
        "cpc",
        "low_top_of_page_bid",
        "high_top_of_page_bid",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(rows)} rows to {out_path}", flush=True)
    print("\nTop 25 by search_volume (preview):", flush=True)
    for r in rows[:25]:
        print(
            f"  {r.get('search_volume')!s:>8}  {r.get('competition')!s:<8}  {r.get('keyword')}",
            flush=True,
        )


if __name__ == "__main__":
    main()
