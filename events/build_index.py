#!/usr/bin/env python3
"""Regenerate events/index.json from every events/<slug>/event.json.

A machine-readable index of Agroverse cacao event activations, meant to be
the first file an LLM (or human) reads to understand the event portfolio.

Source of truth = each `events/<slug>/event.json`. This script just
aggregates them (sorted by date) into `events/index.json` — never hand-edit
index.json, edit the per-event file and re-run this.

    python3 build_index.py        # run from anywhere; paths are self-relative

Schema + conventions: agentic_ai_context/EVENTS.md
"""
import datetime
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> None:
    events = []
    for path in sorted(glob.glob(os.path.join(HERE, "*", "event.json"))):
        with open(path, encoding="utf-8") as f:
            ev = json.load(f)
        ev["path"] = os.path.basename(os.path.dirname(path))
        events.append(ev)

    events.sort(key=lambda e: e.get("date") or "9999-12-31")

    index = {
        "schema_version": 1,
        "description": (
            "Index of Agroverse cacao event activations. Source of truth = each "
            "events/<slug>/event.json; regenerate with build_index.py. "
            "Convention doc: agentic_ai_context/EVENTS.md"
        ),
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "generated_by": "build_index.py",
        "count": len(events),
        "events": events,
    }

    out = os.path.join(HERE, "index.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"wrote {out} ({len(events)} events)")


if __name__ == "__main__":
    main()
