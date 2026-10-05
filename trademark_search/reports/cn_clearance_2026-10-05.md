# China mainland trademark clearance — Catonga / Cabrua / Itacare (Bahia)

**Date:** 2026-10-05 · **Tool:** `trademark_search/cn_trademark.py` ·
**Source:** chinatrademarkoffice.com (China mainland DB mirror)

Method: paginated each result set in full (~20 rows/page) before judging, so an
exact hit cannot hide on a later page. `exact` = identical mark string;
`near` = query is a substring of the result mark.

| Term | Similar results scanned | Exact | Near | Verdict |
|------|------------------------:|------:|-----:|---------|
| **Catonga** | 495 | 0 | 0 | CLEAR |
| **Cabrua** | 558 | 0 | 0 | CLEAR |
| **Itacare** | 1,005 | **1** | 50 | **ITACARE already FILED (pending)** |
| Agroverse (context) | 144 | 0 | 0 | CLEAR |

## The one hit — ITACARE

- **Mark:** ITACARE
- **Application no.:** 93301527
- **Nice class:** 5 (pharmaceuticals / health preparations)
- **Owner:** 北京两个陆食品科技有限公司 — Beijing Liangge Lu Food Technology Co., Ltd.
- **Status:** **application filed 2026-08-03**, no registration number yet (pending)
- **Detail:** https://www.chinatrademarkoffice.com/search/tmdetails/5/93301527.html

Near matches (50) are the **VITACARE / PITACARE** family (classes 3, 5, 9, 10,
26, 29, 35, 38, 44 …) — different marks, but same phonetic tail.

## Read-out

- **Catonga** and **Cabrua** are clear in the China mainland DB.
- **Itacare** collides with a **pending** class-5 filing (health/pharma). If we want
  Itacare for cacao/food (likely classes 29/30/35), the class-5 filing does **not**
  block food classes — but a fresh CN filing is advisable before using it, and the
  near VITACARE/PITACARE family raises the similarity-search bar.

## Sanity check

The exact-match path was validated against a known registration:
`AEROVERSE` → #70070835, class 9 (Chengdu Chengdian Guangxin Technology) —
correctly surfaced as exact.

## Class-scoped read-out (classes 29 / 30 / 35 = food, cacao, retail)

A mark is only a problem in the classes you actually use, so each term was
re-checked scoped to Nice classes 29/30/35:

| Term | Class 29 | Class 30 | Class 35 | Verdict (our classes) |
|------|---------:|---------:|---------:|-----------------------|
| Catonga | 0 exact | 0 | 0 | CLEAR |
| Cabrua | 0 | 0 | 0 | CLEAR |
| Itacare | 0 | 0 | 0 | CLEAR |

**Itacare's only exact hit (#93301527, filed 2026-08-03) is in class 5 (pharma),
not our food/cacao/retail classes** — it does not block 29/30/35. The near marks
in our classes are the VITACARE family (phonetic tail only).

## Caveat

Reference only — **no legal effect**. The mirror is an English transliteration
view and can miss pure-Chinese marks. Confirm with a licensed CN trademark agent
before filing or committing to a name.
