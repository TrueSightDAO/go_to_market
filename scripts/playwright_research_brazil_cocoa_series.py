#!/usr/bin/env python3
"""
SERP-style research for the Agroverse Brazil/Cacao blog series (Playwright).

Tries Bing first, then Yahoo HTML results, with hard timeouts so a single CAPTCHA page
cannot hang the batch.

Usage (from market_research/):
  python3 -m pip install playwright
  python3 -m playwright install chromium
  python3 scripts/playwright_research_brazil_cocoa_series.py

Output:
  data/brazil_cocoa_series_playwright_research.json
"""

from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path
from urllib.parse import quote_plus, urlparse

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

_REPO = Path(__file__).resolve().parent.parent
_DATA = _REPO / "data"
_META = _REPO.parent / "agroverse_shop" / "scripts" / "brazil_cocoa_series" / "meta.json"
OUT_PATH = _DATA / "brazil_cocoa_series_playwright_research.json"

QUERY_SUFFIX = " Brazil cacao"


def _unwrap_bing_redirect(url: str) -> str:
    """Resolve bing.com/ck/a redirects to the destination URL when encoded."""
    if "bing.com/ck/a" not in url:
        return url
    m = re.search(r"[?&]u=a1([^&]+)", url)
    if not m:
        return url
    blob = m.group(1)
    pad = "=" * (-len(blob) % 4)
    try:
        decoded = base64.urlsafe_b64decode(blob + pad)
        return decoded.decode("utf-8", errors="ignore")
    except Exception:
        return url


def _load_posts() -> list[dict]:
    if not _META.is_file():
        raise SystemExit(f"Missing {_META}")
    return json.loads(_META.read_text(encoding="utf-8"))["posts"]


def _normalize(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for r in rows:
        u = r.get("url") or ""
        if not u.startswith("http") or u in seen:
            continue
        seen.add(u)
        out.append(
            {
                "title": (r.get("title") or "").strip(),
                "url": u,
                "snippet": (r.get("snippet") or "")[:500],
            }
        )
    return out[:12]


def _bing(page, q: str, ms: int) -> list[dict]:
    url = f"https://www.bing.com/search?q={quote_plus(q)}"
    page.goto(url, wait_until="domcontentloaded", timeout=ms)
    page.locator("#b_results").wait_for(timeout=min(ms, 12000))
    rows: list[dict] = []
    for li in page.locator("#b_results li.b_algo").all()[:12]:
        try:
            h2a = li.locator("h2 a").first
            if not h2a.count():
                continue
            title = h2a.inner_text().strip()
            href = _unwrap_bing_redirect(h2a.get_attribute("href") or "")
            snippet = ""
            p = li.locator("p").first
            if p.count():
                snippet = p.inner_text().strip()
            rows.append({"title": title, "url": href, "snippet": snippet})
        except Exception:
            continue
    return _normalize(rows)


def _ddg_html(page, q: str, ms: int) -> list[dict]:
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(q)}"
    page.goto(url, wait_until="domcontentloaded", timeout=ms)
    page.locator(".result").first.wait_for(timeout=min(ms, 15000))
    rows: list[dict] = []
    for res in page.locator(".result").all()[:12]:
        try:
            a = res.locator("a.result__a").first
            if not a.count():
                continue
            title = a.inner_text().strip()
            href = a.get_attribute("href") or ""
            snippet = ""
            sn = res.locator(".result__snippet").first
            if sn.count():
                snippet = sn.inner_text().strip()
            rows.append({"title": title, "url": href, "snippet": snippet})
        except Exception:
            continue
    return _normalize(rows)


def _yahoo(page, q: str, ms: int) -> list[dict]:
    url = f"https://search.yahoo.com/search?p={quote_plus(q)}"
    page.goto(url, wait_until="domcontentloaded", timeout=ms)
    page.locator("#web ol.searchCenterMiddle").wait_for(timeout=min(ms, 12000))
    rows: list[dict] = []
    for li in page.locator("#web ol.searchCenterMiddle > li").all()[:14]:
        try:
            a = li.locator("a[data-mboff]").first
            if not a.count():
                a = li.locator("h3 a").first
            if not a.count():
                continue
            title = a.inner_text().strip()
            href = a.get_attribute("href") or ""
            if "yahoo.com/rq" in href or "billing" in href.lower():
                continue
            snippet = ""
            sp = li.locator(".compText, .fc-falcon, .aAbs").first
            if sp.count():
                snippet = sp.inner_text().strip()
            rows.append({"title": title, "url": href, "snippet": snippet})
        except Exception:
            continue
    return _normalize(rows)


def _collect(page, q: str) -> tuple[list[dict], str]:
    ms = 22000
    for engine, fn in (
        ("bing", _bing),
        ("yahoo", _yahoo),
        ("duckduckgo_html", _ddg_html),
    ):
        try:
            rows = fn(page, q, ms)
            if len(rows) >= 3:
                return rows, engine
        except (PWTimeout, Exception):
            continue
    return [], "none"


def run_research(headless: bool = True, delay_s: float = 1.5) -> dict:
    posts = _load_posts()
    by_keyword: dict[str, dict] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)

        for post in posts:
            kw = (post.get("primary_keyword") or "").strip()
            if not kw:
                continue
            q = f"{kw}{QUERY_SUFFIX}"
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                ),
                locale="en-US",
            )
            page = context.new_page()
            page.set_default_timeout(22000)
            try:
                results, engine = _collect(page, q)
                if len(results) < 3:
                    results2, engine2 = _collect(page, kw)
                    if len(results2) > len(results):
                        results, engine = results2, engine2
            finally:
                context.close()

            domains: list[str] = []
            for r in results:
                try:
                    host = urlparse(r["url"]).netloc.lower()
                    if host:
                        domains.append(host)
                except Exception:
                    pass

            by_keyword[kw] = {
                "slug": post["slug"],
                "query": q,
                "engine_used": engine,
                "top_results": results,
                "domains": domains,
            }
            time.sleep(delay_s)

        browser.close()

    return {
        "source": "playwright (bing, yahoo, duckduckgo html)",
        "query_suffix": QUERY_SUFFIX,
        "posts": posts,
        "serp_by_keyword": by_keyword,
    }


def main() -> None:
    _DATA.mkdir(parents=True, exist_ok=True)
    payload = run_research(headless=True, delay_s=1.0)
    OUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    for kw, block in payload["serp_by_keyword"].items():
        eng = block.get("engine_used")
        n = len(block.get("top_results") or [])
        print(f"  {kw}: {n} via {eng}")


if __name__ == "__main__":
    main()
