# Events

Agroverse cacao **event activations** — one folder per event.

## For machines (LLMs): start here
- **[`index.json`](index.json)** — the aggregated, date-sorted index of every event. Read this first; it embeds each event's full metadata (date, venue, host, format, QR codes, status, next milestone, doc paths).

## How it's structured
- Each event lives in `events/<slug>/` (e.g. `sftechfestjune26/`).
- **`<slug>/event.json`** is the per-event source of truth (machine-readable twin of the checklist header).
- **`index.json`** is generated — **never hand-edit it**. Edit the per-event `event.json`, then run:

  ```bash
  python3 events/build_index.py
  ```

Each event folder also holds the human docs: `EXECUTION_CHECKLIST.md` (phased, the working surface), `proposal*.md` (plan-of-record), `implementation_roadmap.md`, and sometimes `field_assets.md` (placard/sticker copy).

## Convention / playbook
The full "how to run a cacao event activation" playbook — `event.json` schema, the phase convention, QR naming (`PREFIX_CC/CT_YYYY → agl4/agl8`), and the Apple Reminder/Calendar check-in convention — lives in **`agentic_ai_context/EVENTS.md`**.
