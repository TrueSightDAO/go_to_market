#!/usr/bin/env python3
"""Filter DataForSEO buyer-intent CSV rows whose keywords match brand/retailer blocklist."""

from __future__ import annotations

import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BLOCKLIST = ROOT / "output" / "dataforseo" / "brand_keyword_blocklist.txt"


def load_blocklist(path: Path) -> list[str]:
    phrases: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        phrases.append(s.lower())
    return phrases


def is_blocked(keyword: str, phrases: list[str]) -> bool:
    k = keyword.lower()
    return any(p in k for p in phrases)


def main() -> None:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument(
        "csv",
        type=Path,
        nargs="?",
        default=None,
        help="Input buyer_intent CSV (default: latest in output/dataforseo/)",
    )
    p.add_argument(
        "-o",
        "--out",
        type=Path,
        default=None,
        help="Output path for non-brand CSV",
    )
    args = p.parse_args()

    out_dir = ROOT / "output" / "dataforseo"
    if args.csv is None:
        files = sorted(out_dir.glob("buyer_intent_keywords_*.csv"))
        if not files:
            raise SystemExit(f"No buyer_intent_keywords_*.csv in {out_dir}")
        in_path = files[-1]
    else:
        in_path = args.csv.resolve()

    phrases = load_blocklist(BLOCKLIST)
    out_path = args.out or out_dir / f"{in_path.stem}_nonbrand{in_path.suffix}"
    excl_path = out_dir / f"{in_path.stem}_excluded_brands{in_path.suffix}"

    kept: list[dict] = []
    excluded: list[dict] = []

    with in_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        if not fieldnames:
            raise SystemExit("Empty CSV")
        for row in reader:
            kw = (row.get("keyword") or "").strip()
            if not kw or kw.replace(",", "").isdigit():
                continue
            if is_blocked(kw, phrases):
                excluded.append(row)
            else:
                kept.append(row)

    def sort_key(r: dict) -> tuple:
        v = r.get("search_volume") or "0"
        try:
            return (-int(v), r.get("keyword") or "")
        except ValueError:
            return (0, r.get("keyword") or "")

    kept.sort(key=sort_key)
    excluded.sort(key=sort_key)

    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(kept)

    with excl_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(excluded)

    print(f"Input:  {in_path}")
    print(f"Blocklist phrases: {len(phrases)}")
    print(f"Kept:   {len(kept)} -> {out_path}")
    print(f"Drop:   {len(excluded)} -> {excl_path}")


if __name__ == "__main__":
    main()
