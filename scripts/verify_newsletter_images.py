#!/usr/bin/env python3
"""Verify that a newsletter's images depict what their captions claim.

`conventions/EMAIL_STYLE_CONVENTION.md` section 4.1 (agentic_ai_context) requires
every image in a public marketing send to be checked against its own alt text
before the campaign is approved. This script automates that row.

It answers three questions per image, by looking at the pixels:
  (1) Is this a photograph, or a map / screenshot / graphic / render?
  (2) What does it actually show, and does that match the claimed subject?
  (3) Are there identifiable people in frame (a consent question)?

Exit code 1 if any image FAILs, so this can gate a send.

Usage:
  python3 scripts/verify_newsletter_images.py \\
      --body-md newsletter_drafts/2026-10-30_freight_landed.md
  python3 scripts/verify_newsletter_images.py --images a.jpg b.jpg \\
      --caption "Paulo's La do Sitio farm, Para"
  python3 scripts/verify_newsletter_images.py --images a.jpg --markdown-report
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

GROK_ENDPOINT = "https://api.x.ai/v1/chat/completions"
DEFAULT_MODEL = "grok-4-1-fast-non-reasoning"
IMAGE_REF_RE = re.compile(r"!\[([^\]]*)\]\(\s*([^)\s]+)")
TIMEOUT = 120

NON_PHOTO_SCENES = {"map", "screenshot", "graphic", "render", "illustration", "chart"}

PROMPT = (
    "You are auditing an image before it is used in a public marketing email. "
    "A caption claims the subject shown below. Answer ONLY with a JSON object, "
    "no prose, no code fences, using exactly these keys:\n"
    '{"scene_type": one of "photo"|"map"|"screenshot"|"graphic"|"render",'
    '"subjects": "short factual description of what is actually visible",'
    '"people_count": integer count of identifiable people,'
    '"depicts_claim": "yes"|"partial"|"no",'
    '"reason": "one sentence explaining the verdict"}\n'
    "Rules: a map pin is a map, not a photograph of a farm. Passenger luggage "
    "is not cargo. Judge only what is visible; do not assume a location.\n\n"
    "CLAIMED SUBJECT: __CLAIM__"
)


def grok_key() -> str:
    key = os.environ.get("GROK_API_KEY", "").strip()
    if not key:
        sys.stderr.write("GROK_API_KEY is not set.\n")
        sys.exit(3)
    return key


def sniff_mime(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return "image/jpeg"


def fetch(image_ref: str, base_dir: Path) -> tuple[bytes, str]:
    """Return (bytes, display_name) for a local path or an https URL."""
    if image_ref.startswith(("http://", "https://")):
        with urllib.request.urlopen(image_ref, timeout=TIMEOUT) as resp:
            return resp.read(), image_ref.rsplit("/", 1)[-1]
    candidates = [
        Path(image_ref),
        base_dir / image_ref,
        base_dir / "assets" / "images" / "newsletter" / Path(image_ref).name,
        Path("assets/images/newsletter") / Path(image_ref).name,
    ]
    for cand in candidates:
        if cand.is_file():
            return cand.read_bytes(), str(cand)
    raise FileNotFoundError(f"image not found: {image_ref}")


def extract_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"no JSON object in model reply: {text[:200]}")
    return json.loads(text[start : end + 1])


def classify(verdict: dict, allow_people: bool) -> tuple[str, list[str]]:
    """Map a model verdict to FAIL/WARN/PASS plus human-readable reasons."""
    reasons: list[str] = []
    scene = str(verdict.get("scene_type", "")).strip().lower()
    depicts = str(verdict.get("depicts_claim", "")).strip().lower()
    try:
        people = int(verdict.get("people_count", 0) or 0)
    except (TypeError, ValueError):
        people = 0

    fail = False
    if scene in NON_PHOTO_SCENES:
        fail = True
        reasons.append(f"not a photograph (scene_type={scene})")
    if depicts == "no":
        fail = True
        reasons.append("does not depict the claimed subject")
    elif depicts == "partial":
        reasons.append("only partially matches the claim")

    if fail:
        return "FAIL", reasons
    if people > 0:
        reasons.append(f"{people} identifiable person(s) — confirm consent")
        return ("WARN" if allow_people else "FAIL"), reasons
    if reasons:
        return "WARN", reasons
    return "PASS", reasons


def audit(
    image_ref: str, claim: str, base_dir: Path, model: str, allow_people: bool
) -> dict:
    data, name = fetch(image_ref, base_dir)
    payload = {
        "model": model,
        "max_tokens": 500,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": PROMPT.replace("__CLAIM__", claim or "(none given)"),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:"
                            + sniff_mime(data)
                            + ";base64,"
                            + base64.b64encode(data).decode(),
                            "detail": "high",
                        },
                    },
                ],
            }
        ],
    }
    req = urllib.request.Request(
        GROK_ENDPOINT,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {grok_key()}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        body = json.load(resp)
    reply = body["choices"][0]["message"]["content"]
    try:
        verdict = extract_json(reply)
    except (ValueError, json.JSONDecodeError) as exc:
        return {
            "image": name,
            "claim": claim,
            "status": "ERROR",
            "reasons": [str(exc)],
            "verdict": {},
        }
    status, reasons = classify(verdict, allow_people)
    return {
        "image": name,
        "claim": claim,
        "status": status,
        "reasons": reasons,
        "verdict": verdict,
    }


def refs_from_markdown(body_md: Path) -> list[tuple[str, str]]:
    text = body_md.read_text(encoding="utf-8")
    return [(alt.strip(), ref) for alt, ref in IMAGE_REF_RE.findall(text)]


def main() -> None:
    p = argparse.ArgumentParser(description="Verify newsletter images vs captions.")
    p.add_argument("--body-md", type=Path, help="Draft whose image refs to audit.")
    p.add_argument(
        "--images",
        nargs="*",
        default=[],
        help="Explicit image paths/URLs (use with --caption).",
    )
    p.add_argument(
        "--caption", default="", help="Claim for --images mode (alt text equivalent)."
    )
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument(
        "--allow-people",
        action="store_true",
        help="Downgrade identifiable-people findings from FAIL to WARN.",
    )
    p.add_argument(
        "--markdown-report",
        action="store_true",
        help="Print the section 4.1 verification table.",
    )
    args = p.parse_args()

    base_dir = args.body_md.parent if args.body_md else Path(".")
    if args.body_md:
        targets = refs_from_markdown(args.body_md)
    elif args.images:
        targets = [(args.caption, ref) for ref in args.images]
    else:
        sys.stderr.write("Pass --body-md or --images.\n")
        sys.exit(2)

    if not targets:
        sys.stderr.write("No image references found. Nothing to verify.\n")
        sys.exit(2)

    results = [
        audit(ref, claim, base_dir, args.model, args.allow_people)
        for claim, ref in targets
    ]

    for row in results:
        print(f"[{row['status']}] {row['image']}")
        print(f"    claim:  {row['claim'] or '(none)'}")
        v = row["verdict"]
        if v:
            print(f"    actual: {v.get('subjects', '?')}")
            print(
                f"    scene:  {v.get('scene_type', '?')} | "
                f"people: {v.get('people_count', '?')} | "
                f"matches: {v.get('depicts_claim', '?')}"
            )
        for reason in row["reasons"]:
            print(f"    -> {reason}")
        print()

    if args.markdown_report:
        print("| filename | claimed | verdict |")
        print("|---|---|---|")
        for row in results:
            claim = (row["claim"] or "(none)").replace("|", "/")
            print(f"| `{row['image']}` | {claim} | {row['status']} |")

    fails = sum(1 for r in results if r["status"] in ("FAIL", "ERROR"))
    warns = sum(1 for r in results if r["status"] == "WARN")
    print(f"IMAGE_CHECK images={len(results)} fail={fails} warn={warns}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
