"""Regression tests for the newsletter markdown renderers.

Two production leaks motivated these (found on a live sample 2026-11-10):
a backtick in copy rendered as a literal backtick in the delivered email, and
a `- ` bullet list collapsed into one run-on <p> of literal hyphens. Both are
silent — the send succeeds and the email looks merely "plain" — so they need
explicit coverage rather than a manual eyeball.
"""

import importlib.util
import os
import sys

_SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
# send_newsletter imports sibling modules (gmail_user_credentials, ...) by bare
# name, so scripts/ must be importable before we exec it.
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_SPEC = importlib.util.spec_from_file_location(
    "send_newsletter_under_test",
    os.path.join(_SCRIPTS_DIR, "send_newsletter.py"),
)
sn = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sn)


def render(md):
    return sn.markdown_to_html(md)


# ---------------------------------------------------------------- code spans


def test_code_span_does_not_leak_backticks():
    html = render("a tracking number starting with `CP`, then customs.")
    assert "`" not in html, "backticks must never reach the delivered HTML"
    assert "<code" in html
    assert "CP" in html


def test_code_span_carries_inline_style_not_a_stylesheet():
    html = render("`047-3175-3223`")
    assert "style=" in html, "clients strip <head> CSS; style must be inline"
    assert "monospace" in html


def test_code_span_survives_markdown_to_plain():
    html = render("entry type of `Mail - Commercial` here")
    plain = sn.markdown_to_plain(html)
    assert "`" not in plain
    assert "Mail - Commercial" in plain


# -------------------------------------------------------------------- bullets


def test_bullet_list_renders_real_list_markup():
    html = render("- one\n- two\n- three")
    assert "<ul" in html
    assert html.count("<li") == 3
    assert " - two" not in html, "hyphens must become list items, not stay literal"


def test_bullet_list_items_are_not_run_together():
    html = render("- Ceremonial cacao\n- Cacao nibs\n- 81% bar")
    assert html.count("<p>") == 0, "a pure list must not also emit a paragraph"


def test_bullet_list_plain_text_puts_one_item_per_line():
    plain = sn.markdown_to_plain(render("- alpha\n- beta"))
    lines = [ln.strip() for ln in plain.splitlines() if ln.strip()]
    assert lines == ["alpha", "beta"]


def test_list_interrupts_and_resumes_surrounding_paragraphs():
    html = render("intro line\n- item\nclosing line")
    assert html.count("<p>") == 2
    assert "<ul" in html


def test_bullet_with_inline_markup_still_formats():
    html = render("- **Ceremonial cacao** — Paulo's farm")
    assert "<li" in html
    assert "<strong>Ceremonial cacao</strong>" in html


# ------------------------------------------------- preserved inline features


def test_bold_italic_and_links_unchanged():
    html = render("as **mail** and *Commercial* see [prod](https://x.test/p)")
    assert "<strong>mail</strong>" in html
    assert "<em>Commercial</em>" in html
    assert '<a href="https://x.test/p">prod</a>' in html


def test_image_is_an_img_not_an_anchor():
    html = render("![logo](https://x.test/l.png)")
    assert "<img" in html
    assert "<a href" not in html


def test_link_transform_still_applied():
    html = sn.markdown_to_html(
        "[a](https://x.test/p)", link_transform=lambda u: u + "?mid=1"
    )
    assert "?mid=1" in html


# ------------------------------------------- documented gaps (characterization)


def test_unsupported_markdown_passes_through_literally():
    """Headings and blockquotes are NOT rendered as HTML by design today.

    This is a characterization test documenting a known gap, not an endorsement:
    if support is added later this test should be updated deliberately rather
    than rediscovered on a delivered email.
    """
    html = render("## Shipping\n> quoted line")
    assert "<h" not in html
    assert "<blockquote" not in html
    assert "## Shipping" in html
    assert "&gt;" not in html and "> quoted" in html
