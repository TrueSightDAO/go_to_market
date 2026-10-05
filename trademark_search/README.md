# China mainland trademark checker

`cn_trademark.py` checks word marks against the **China mainland trademark
database** so we can clear names (e.g. Brazil-origin place names) before using
them on packaging/marketing in China.

## Why not the official sources

- **CNIPA** (`wcjs.sbj.cnipa.gov.cn`) — foreign-IP gated; returns `403` from our hosts.
- **WIPO Global Brand DB** — CAPTCHA (AltCha) + partner-only API.
- **TMview** (EUIPO aggregator, includes CN) — `www.tmdn.org` was unreachable from our box (timeout).

So this wraps the free, English-language mirror **chinatrademarkoffice.com**
(Shanghai Sounding IP Agency). It is a **pragmatic aggregator, not an official
CNIPA API** — screening / reference only, **no legal effect**. Confirm anything
material with a licensed Chinese trademark agent.

## Install

```bash
pip install requests
```

## Usage

```bash
# Verdicts over the FULL result set (slow for common strings; ~20 rows/page):
python3 cn_trademark.py check "Catonga" "Cabrua" "Itacare"

# Machine-readable:
python3 cn_trademark.py check "Itacare" --json

# Raw similar marks, optionally filtered by Nice class:
python3 cn_trademark.py search "Agroverse" --class 30 --json

# One record's labelled fields + application/publication/registration/expiry dates:
python3 cn_trademark.py detail "https://www.chinatrademarkoffice.com/search/tmdetails/5/93301527.html?ln=&vcode=0234"
```

`check` exits **1** if any term has an exact hit (CI-friendly); **0** otherwise.

## How it decides

- **exact** = the result mark string equals the query (case/spacing-insensitive).
- **near** = the query is a substring of the result mark (e.g. `ITACARE` inside `VITACARE`).
- A term is judged only after paginating the **entire** result set, because an
exact registration can fall on any page (it is *not* ranked first).

## Gotchas

- The site's `per_page` query param is really an **offset**, not a page size —
  the tool uses it as an offset and always steps 20 rows at a time.
- The DB is an English transliteration view: a pure-Chinese mark may only surface
  via its pinyin/English form. Absence of an exact hit is *not* proof the mark is free.
- Detail-page fields (owner address, agent, status) are often behind a login.

## Report

First clearance run: [`reports/cn_clearance_2026-10-05.md`](reports/cn_clearance_2026-10-05.md).
