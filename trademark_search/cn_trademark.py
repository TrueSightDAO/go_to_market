"""cn_trademark.py -- check word marks against the China mainland trademark DB.

Source: https://www.chinatrademarkoffice.com  (China Patent & Trademark Office,
Shanghai Sounding IP Agency). Free, English-language, scrapes the public HTML
CNIPA-mirror search. NOT an official CNIPA API -> screening / reference only,
carries no legal effect. Verify anything material with a licensed CN agent.

Usage
-----
  # One-line verdicts (paginates the WHOLE result set before judging):
  python3 cn_trademark.py check "Catonga" "Cabrua" "Itacare"

  # Raw similar marks (JSON):
  python3 cn_trademark.py search "Agroverse" --class 30

  # One record's labelled fields + key dates:
  python3 cn_trademark.py detail "<detail_url>"

Exit code is 0, or 1 when any checked term has an exact hit (CI-friendly).
"""
from __future__ import annotations

import argparse
import html as _html
import json
import re
import sys
import time

import requests

BASE = "https://www.chinatrademarkoffice.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
TIMEOUT = 30
PAGE_SIZE = 20  # the site's `per_page` query param is an OFFSET, not a count


def _sess() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    return s


def _clean(x: str) -> str:
    x = re.sub(r"(?s)<[^>]+>", "", x)
    return re.sub(r"\s+", " ", _html.unescape(x)).strip()


def _parse_rows(h: str) -> list[dict]:
    rows = []
    for blk in re.findall(r'(?s)<h3 class="t">(.*?)</tr>', h):
        link = re.search(r'href="(/search/tmdetails/[^"]+)"', blk)
        if not link:
            continue
        num = re.search(r"Number:\s*(\d+)", blk)
        cls = re.search(r"Class:\s*([\d,\s]+)", blk)
        owner_zh = re.search(r'class="m">([^<]+)<br>', blk)
        owner_en = re.search(r"<br>([^<]+)</a>", blk)
        rows.append({
            "mark": _clean(re.split(r"</h3>", blk)[0]),
            "number": num.group(1) if num else "",
            "class": cls.group(1).strip() if cls else "",
            "owner_zh": _clean(owner_zh.group(1)) if owner_zh else "",
            "owner_en": _clean(owner_en.group(1)) if owner_en else "",
            "detail_url": BASE + _html.unescape(link.group(1)),
        })
    return rows


def search(sess, mark, intcls="", ln="", max_pages=120, pause=0.4):
    """Paginate the CN mainland DB. Returns (total, [row, ...]) over ALL pages."""
    rows, total, offset = [], 0, 0
    for _ in range(max_pages):
        r = sess.get(f"{BASE}/index.php", timeout=TIMEOUT, params={
            "c": "tdsearch", "mark": mark, "IntCls": intcls, "ln": ln,
            "appCode": "", "per_page": offset})
        r.raise_for_status()
        r.encoding = "utf-8"
        h = r.text
        if offset == 0:
            m = re.search(r"Total similar results:\s*<span[^>]*>\s*(\d+)", h)
            total = int(m.group(1)) if m else 0
        page = _parse_rows(h)
        rows += page
        offset += PAGE_SIZE
        if not page or offset >= total:
            break
        time.sleep(pause)
    return total, rows


def check(sess, term, **kw):
    """Verdict for one term over the full result set."""
    total, rows = search(sess, term, **kw)
    tl = term.lower().replace(" ", "")
    exact = [r for r in rows if r["mark"].lower().replace(" ", "") == tl]
    near = [r for r in rows if tl in r["mark"].lower().replace(" ", "") and r not in exact]
    return {"term": term, "total_similar": total, "fetched": len(rows),
            "exact_hits": exact, "near_hits": near,
            "registered": bool(exact), "similar_on_file": bool(near)}


def detail(sess, url):
    """Fetch a detail page -> {label: value} plus 'dates' (app/pub/reg/expiry)."""
    r = sess.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    r.encoding = "utf-8"
    h = r.text
    out = {}
    for lab, val in re.findall(
            r"(?s)<td[^>]*>\s*<span>\s*([^<]+?)\s*</span>\s*</td>"
            r"\s*<td[^>]*>\s*<span>\s*(.*?)\s*</span>", h):
        lab, val = _clean(lab), _clean(val)
        if lab and val and lab not in out:
            out[lab] = val
    dates = re.findall(r'<div class="riqi"[^>]*>\s*([\d-]{8,10})\s*</div>', h)
    if dates:
        out["dates"] = dates[:4]
    return out


def verdict_line(v: dict) -> str:
    if v["exact_hits"]:
        tag = "REGISTERED/FILED (exact)"
    elif v["near_hits"]:
        tag = "SIMILAR MARKS ON FILE"
    else:
        tag = "CLEAR (no exact/near hit)"
    return f"{v['term']:<12} {tag:<26} ({v['total_similar']} similar; {v['fetched']} scanned)"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check marks in the China mainland trademark DB.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("search")
    p.add_argument("mark")
    p.add_argument("--class", dest="intcls", default="")
    p.add_argument("--json", action="store_true")
    c = sub.add_parser("check")
    c.add_argument("terms", nargs="+")
    c.add_argument("--json", action="store_true")
    d = sub.add_parser("detail")
    d.add_argument("url")
    a = ap.parse_args(argv)
    sess = _sess()

    if a.cmd == "detail":
        print(json.dumps(detail(sess, a.url), ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "search":
        total, rows = search(sess, a.mark, a.intcls)
        if a.json:
            print(json.dumps({"total": total, "rows": rows}, ensure_ascii=False, indent=2))
        else:
            print(f"{total} similar results for '{a.mark}':")
            for r in rows:
                print(f"  {r['mark']:<20} {r['number']:<10} cl {r['class']:<8} "
                      f"{r['owner_zh'] or r['owner_en']}")
        return 0

    out, bad = [], False
    for t in a.terms:
        v = check(sess, t)
        out.append(v)
        bad = bad or v["registered"]
        time.sleep(0.5)
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for v in out:
            print(verdict_line(v))
        for v in out:
            if v["exact_hits"]:
                for r in v["exact_hits"]:
                    print(f"  -> {v['term']} = #{r['number']} class {r['class']}: "
                          f"{r['owner_zh'] or r['owner_en']}\n     {r['detail_url']}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
