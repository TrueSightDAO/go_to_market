"""
Optional open tracking for Email Agent Gmail drafts.

Embeds a 1×1 image pointing at **Edgar** (or another HTTPS host) so a future endpoint can
record opens. The URL carries ``tid=<suggestion_id>`` (same UUID written to **Email Agent Drafts**).

**Follow Up sheet** columns **Open** / **Click through** (see ``sync_email_agent_followup.py``) are
intended to be updated by that endpoint (or a small relay) once a matching **sent** row exists.
At draft time there is no ``gmail_message_id`` yet, so the pixel cannot target column L/M directly
until Edgar correlates ``tid`` → ``gmail_message_id`` after ``sync_email_agent_followup.py`` runs.

Environment / CLI
-------------------
- ``EMAIL_AGENT_TRACKING_BASE_URL`` — default ``https://edgar.truesight.me`` (no trailing slash required).
- Draft scripts: ``--track-opens`` to attach the HTML part + pixel (plain part stays for clients that
  prefer text).

**Clicks** are not rewritten here; reserve **Click through** (column M) for a future Edgar
``/email_agent/click`` redirector similar to ``send_newsletter.py``.
"""

from __future__ import annotations

import html
import urllib.parse


def build_open_pixel_html(base_url: str, suggestion_id: str) -> str:
    tid = urllib.parse.quote((suggestion_id or "").strip(), safe="")
    url = f"{base_url.rstrip('/')}/email_agent/open.gif?tid={tid}"
    return (
        f'<img src="{url}" alt="" width="1" height="1" '
        'style="display:block;border:0;width:1px;height:1px;" />'
    )


def plain_text_to_html_with_open_pixel(plain: str, base_url: str, suggestion_id: str) -> str:
    """Wrap plain text as HTML and append the tracking pixel (multipart/alternative HTML half)."""
    body = html.escape(plain or "", quote=False)
    wrapped = (
        '<div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;'
        'font-size:15px;line-height:1.45;white-space:pre-wrap;">'
        f"{body}</div>"
    )
    return wrapped + build_open_pixel_html(base_url, suggestion_id)
