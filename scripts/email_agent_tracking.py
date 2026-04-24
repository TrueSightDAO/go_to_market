"""
Optional open / click tracking for Email Agent Gmail drafts.

Embeds a 1×1 image pointing at **Edgar** (or another HTTPS host) so an endpoint can
record opens. The URL carries ``tid=<suggestion_id>`` (same UUID written to **Email Agent Drafts**).

**Email Agent Drafts** has **Open** / **Click through** (defaults ``0``). Edgar should increment
those when the pixel or click redirect fires before the **Email Agent Follow Up** row exists.
``sync_email_agent_followup.py`` copies ``suggestion_id``, **Open**, and **Click through** from the
matched draft row when appending a Follow Up row (see ``HIT_LIST_CREDENTIALS.md``).

Environment / CLI
-------------------
- ``EMAIL_AGENT_TRACKING_BASE_URL`` — default ``https://edgar.truesight.me`` (no trailing slash required).
- Draft scripts: ``--track-opens`` for multipart HTML + open pixel; ``--track-clicks`` rewrites
  ``http(s):`` URLs in the **HTML** half through ``GET /email_agent/click?tid=…&r=…&to=…`` (same idea
  as ``send_newsletter.py`` / ``newsletter/click``). Plain part is unchanged.

Edgar must implement ``GET /email_agent/open.gif`` and ``GET /email_agent/click`` (redirect) if you use these flags.
"""

from __future__ import annotations

import base64
import html
import re
import urllib.parse

_AGENT_URL_RE = re.compile(r"https?://[^\s<>\"'()\[\]{}]+", re.IGNORECASE)


def _b64url(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii").rstrip("=")


def build_open_pixel_html(base_url: str, suggestion_id: str) -> str:
    tid = urllib.parse.quote((suggestion_id or "").strip(), safe="")
    url = f"{base_url.rstrip('/')}/email_agent/open.gif?tid={tid}"
    return (
        f'<img src="{url}" alt="" width="1" height="1" '
        'style="display:block;border:0;width:1px;height:1px;" />'
    )


def build_email_agent_tracked_link(
    original_url: str, base_url: str, suggestion_id: str, recipient: str
) -> str:
    """Wrap ``http(s)`` URLs for Edgar click logging; other schemes left unchanged."""
    ou = (original_url or "").strip()
    if not ou.lower().startswith(("http://", "https://")):
        return ou
    tid = urllib.parse.quote((suggestion_id or "").strip(), safe="")
    r = _b64url(recipient or "")
    to = _b64url(ou)
    return f"{base_url.rstrip('/')}/email_agent/click?tid={tid}&r={r}&to={to}"


def _html_body_preplain(
    plain: str,
    base_url: str,
    suggestion_id: str,
    recipient_email: str,
    *,
    track_clicks: bool,
) -> str:
    s = plain or ""
    if not track_clicks:
        body = html.escape(s, quote=False)
    else:
        chunks: list[str] = []
        pos = 0
        for m in _AGENT_URL_RE.finditer(s):
            chunks.append(html.escape(s[pos : m.start()], quote=False))
            raw_url = m.group(0)
            href = build_email_agent_tracked_link(raw_url, base_url, suggestion_id, recipient_email)
            chunks.append(
                f'<a href="{html.escape(href, quote=True)}">{html.escape(raw_url, quote=False)}</a>'
            )
            pos = m.end()
        chunks.append(html.escape(s[pos:], quote=False))
        body = "".join(chunks)
    return (
        '<div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;'
        'font-size:15px;line-height:1.45;white-space:pre-wrap;">'
        f"{body}</div>"
    )


def plain_text_to_html_for_email_agent(
    plain: str,
    base_url: str,
    suggestion_id: str,
    recipient_email: str,
    *,
    track_opens: bool = False,
    track_clicks: bool = False,
) -> str | None:
    """Build the HTML alternative for Gmail multipart; ``None`` if no tracking requested."""
    if not track_opens and not track_clicks:
        return None
    inner = _html_body_preplain(
        plain,
        base_url,
        suggestion_id,
        recipient_email,
        track_clicks=track_clicks,
    )
    if track_opens:
        return inner + build_open_pixel_html(base_url, suggestion_id)
    return inner


def plain_text_to_html_with_open_pixel(plain: str, base_url: str, suggestion_id: str) -> str:
    """Wrap plain text as HTML and append the tracking pixel (multipart/alternative HTML half)."""
    out = plain_text_to_html_for_email_agent(
        plain,
        base_url,
        suggestion_id,
        "",
        track_opens=True,
        track_clicks=False,
    )
    return out or ""
