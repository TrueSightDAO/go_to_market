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

## Batch 2 — Cabruca / Catongo / Itacare / Bahia (classes 29, 30, 35)

Second request: `cabruca`, `catongo` (albino cacao, Bahia), `itacare`, `bahia`,
scoped to Nice **29** (food), **30** (cacao), **35** (marketing / advertising /
retail). Full result set paginated per (term, class) — no page-1-only blind spot.

| Term | cl 29 | cl 30 | cl 35 | Verdict (our classes) |
|------|------:|------:|------:|-----------------------|
| Cabruca | 0 exact | 0 | 0 | ✅ CLEAR |
| Catongo | 0 exact | 0 | 0 | ✅ CLEAR |
| Itacare | 0 exact | 0 | 0 | ✅ CLEAR (VITACARE near only) |
| **Bahia** | 0 exact | **2 EXACT** | **1 EXACT** | ⚠️ **REGISTERED** |

### Bahia — blocked in the two classes that matter
`BAHIA` is an **exact word mark already on the CN register** in the exact classes
the DAO needs:

| Class | Reg. no. | Owner (as shown) | Dates |
|------:|----------|------------------|-------|
| **30** (cacao/food) | **9841063** | zhe jiang jia xin tou zi fa zhan you xian gong si (Zhejiang Jiaxin Investment) | 2011-08-12 |
| **30** (cacao/food) | **G612817** | B A H L S E N G M B H C O K G (**Madrid** international registration) | 1993-12-07 → 2013-12-07 |
| **35** (marketing/advertising) | **83400642** | guang dong ba yi ya ke ji you xian gong si (Guangdong Bayiya Tech) | 2025-02-11 → registered 2025-05-13, valid to **2035-08-13** |

**Read-out:** "Bahia" cannot be filed as a standalone word mark in class 30 or 35
today — both are occupied, and the class-35 mark is freshly registered (2025) and
runs to 2035. It remains usable **as part of a composite/device mark**
(e.g. *Itacare, Bahia* / a logo lockup), which is the normal workaround. Cabruca,
Catongo and Itacare are clear in our classes.

### Itacare — near marks only
The only close marks in classes 29/35 are the **VITACARE** family (class 29:
jing hua #42007205/#45119373, tian jin kai ji er xin neng yuan #11641814; class 35:
shang hai wei kai #20453960, hai nan he he di yi liao #84944595, wei bao #37292091).
Different word marks sharing the "-acare" phonetic tail — not an exact block.

## Caveat

Reference only — **no legal effect**. The mirror is an English transliteration
view and can miss pure-Chinese marks. Confirm with a licensed CN trademark agent
before filing or committing to a name.
