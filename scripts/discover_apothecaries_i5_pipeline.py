#!/usr/bin/env python3
"""
Run I-5 corridor (San Diego → Seattle) Places discovery, then Instagram backfill.

Discovery: ``discover_apothecaries_la_hit_list.py --region <preset>`` (default ``i5_corridor``;
use ``i5_sd_portland`` for San Diego–Portland only). Same dedupe,
Research rows, Notes with place_id). Instagram: ``backfill_instagram_la_discovery.py``
for rows whose Notes contain "Auto-discovered (Google Places Nearby" and empty Instagram.

This is not Google "Places AI" — it uses standard Places Nearby + Details APIs; optional
DuckDuckGo HTML in the backfill step can help find handles when the storefront site omits them.

Examples:
  cd market_research
  python3 scripts/discover_apothecaries_i5_pipeline.py --dry-run
  python3 scripts/discover_apothecaries_i5_pipeline.py --max-new 400 --instagram-limit 150
  python3 scripts/discover_apothecaries_i5_pipeline.py --instagram-ddg
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def run(argv: list[str]) -> int:
    r = subprocess.run(argv, cwd=str(REPO))
    return r.returncode


def main() -> None:
    p = argparse.ArgumentParser(
        description="I-5 corridor: append Research apothecaries, then fill Instagram where empty."
    )
    p.add_argument(
        "--region",
        default="i5_corridor",
        metavar="KEY",
        help=(
            "Discovery preset: i5_corridor, i5_sd_portland, ca_hwy_101, ca_i280, la, sf_bay, …"
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Pass through to discovery only; skip Instagram step.",
    )
    p.add_argument(
        "--max-new",
        type=int,
        default=400,
        help="Max new Hit List rows for discovery (default 400).",
    )
    p.add_argument(
        "--keyword",
        default="apothecary",
        help='Nearby Search keyword (default "apothecary").',
    )
    p.add_argument(
        "--shop-type",
        default="Metaphysical/Spiritual",
        help='Shop Type for new rows (default "Metaphysical/Spiritual").',
    )
    p.add_argument(
        "--skip-instagram",
        action="store_true",
        help="Only run discovery.",
    )
    p.add_argument(
        "--instagram-limit",
        type=int,
        default=0,
        metavar="N",
        help="Max Instagram backfill rows (0 = all qualifying empty-IG discovery rows).",
    )
    p.add_argument(
        "--instagram-ddg",
        action="store_true",
        help="Pass --ddg to Instagram backfill (slower; tries DuckDuckGo if site has no link).",
    )
    p.add_argument(
        "--instagram-sleep",
        type=float,
        default=0.35,
        help="HTTP delay for Instagram backfill (default 0.35).",
    )
    args = p.parse_args()

    py = sys.executable
    discover = [
        py,
        str(REPO / "scripts" / "discover_apothecaries_la_hit_list.py"),
        "--region",
        args.region,
        "--max-new",
        str(args.max_new),
        "--keyword",
        args.keyword,
        "--shop-type",
        args.shop_type,
    ]
    if args.dry_run:
        discover.append("--dry-run")

    print(f"--- Step 1: discovery ({args.region}) ---", flush=True)
    if run(discover) != 0:
        raise SystemExit(1)

    if args.dry_run or args.skip_instagram:
        print("Skipping Instagram step.", flush=True)
        return

    backfill: list[str] = [
        py,
        str(REPO / "scripts" / "backfill_instagram_la_discovery.py"),
        "--sleep",
        str(args.instagram_sleep),
    ]
    if args.instagram_limit > 0:
        backfill.extend(["--limit", str(args.instagram_limit)])
    if args.instagram_ddg:
        backfill.append("--ddg")

    print("--- Step 2: Instagram backfill (discovery notes, empty IG) ---", flush=True)
    if run(backfill) != 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
