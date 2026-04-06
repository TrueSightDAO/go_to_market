"""Extract best-effort plain text from a Gmail API message payload (multipart)."""

from __future__ import annotations

import base64
import re

# Single-message cap when pulling bodies for Sheets / prompts (keep under cell limits).
PLAIN_BODY_MAX_CHARS = 20_000


def decode_gmail_body_data(data: str) -> str:
    if not data:
        return ""
    pad = "=" * ((4 - len(data) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode(data + pad)
        return raw.decode("utf-8", errors="replace")
    except (ValueError, UnicodeError):
        return ""


def html_to_plain(html: str) -> str:
    t = re.sub(r"(?is)<script[^>]*>.*?</script>", "", html)
    t = re.sub(r"(?is)<style[^>]*>.*?</style>", "", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def extract_plain_body_from_payload(
    payload: dict, *, per_part_cap: int = 14_000, max_total: int | None = None
) -> str:
    plain_chunks: list[str] = []
    html_chunks: list[str] = []

    def walk(part: dict) -> None:
        mime = (part.get("mimeType") or "").lower()
        body = part.get("body") or {}
        data = body.get("data")
        if data:
            text = decode_gmail_body_data(data)
            if not text:
                return
            if "text/plain" in mime:
                plain_chunks.append(text[:per_part_cap])
            elif "text/html" in mime:
                html_chunks.append(text[:per_part_cap])
        for p in part.get("parts") or []:
            walk(p)

    walk(payload or {})
    cap = max_total if max_total is not None else PLAIN_BODY_MAX_CHARS
    if plain_chunks:
        return "\n\n".join(plain_chunks).strip()[:cap]
    if html_chunks:
        return html_to_plain("\n\n".join(html_chunks))[:cap]
    return ""
