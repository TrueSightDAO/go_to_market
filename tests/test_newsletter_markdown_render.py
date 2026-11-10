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


# ------------------------------------------------- house-style wrapper (s.3/8)


def wrap(content="<p>copy</p>", **kw):
    return sn.build_email_html(content, **kw)


def test_wrapper_has_every_ship_checklist_item():
    html = wrap(footer_html="<div>Agroverse</div>")
    required = {
        "doctype": "<!DOCTYPE html>",
        "body bgcolor": 'bgcolor="#FFFFFF"',
        "outer table 100%": 'width="100%"',
        "600px ceiling": "max-width:600px",
        "saffron 3px rule": "border-top:3px solid #C98A2D",
        "font stack": "'Helvetica Neue',Helvetica,Arial,sans-serif",
        "16px body": "font-size:16px",
        "1.6 line-height": "line-height:1.6",
        "body text #222": "#222222",
        "footer rule #DDDDDD": "1px solid #DDDDDD",
        "footer gray #888": "#888888",
    }
    for label, needle in required.items():
        assert needle in html, f"missing {label}"


def test_wrapper_uses_no_stylesheet():
    """Clients strip <head> CSS, so any <style> block would silently do nothing."""
    html = wrap()
    assert "<style" not in html
    assert "stylesheet" not in html


def test_wrapper_tables_are_balanced():
    html = wrap(footer_html="<div>x</div>")
    assert html.count("<table") == html.count("</table>")
    assert html.count("<tr>") == html.count("</tr>")


def test_preheader_is_hidden_and_precedes_content():
    html = wrap(preheader="Eleven days from Ilheus")
    assert "display:none;max-height:0" in html
    # must be the first element inside <body>, before the wrapper table
    assert html.index("Eleven days from Ilheus") < html.index("<table")


def test_preheader_absent_adds_nothing():
    assert "display:none;max-height:0" not in wrap(preheader=None)
    assert "display:none;max-height:0" not in wrap(preheader="   ")


def test_over_long_preheader_is_truncated_to_convention_limit():
    html = wrap(preheader="x" * 200)
    assert "x" * sn.PREHEADER_MAX in html
    assert "x" * (sn.PREHEADER_MAX + 1) not in html


def test_footer_sits_inside_the_wrapper_table():
    html = wrap(footer_html="<div>Agroverse</div>")
    assert "<div>Agroverse</div>" in html
    # footer must close before the closing tables, i.e. it is inside the shell
    assert html.index("Agroverse") < html.rindex("</table>")


def test_content_is_not_altered_by_wrapping():
    content = "<p>a</p><ul><li>b</li></ul><code>x</code>"
    html = wrap(content)
    assert content in html


def test_wrapper_preserves_the_markdown_fixes_end_to_end():
    """The two shipped bug fixes must survive wrapping, not just unit-render."""
    html = wrap(sn.markdown_to_html("see `CP` then\n- one\n- two"))
    assert "`" not in html
    assert "<code" in html
    assert html.count("<li") == 2


def test_wrapper_keeps_real_tracking_pixel_inside_shell():
    footer = sn.build_tracking_pixel_html("mid-1", "a@b.test", "https://e.test")
    html = wrap(footer_html=footer)
    assert "open.gif" in html
    assert html.index("open.gif") < html.rindex("</table>")


# --------------------------------- text/plain path (plain_body = markdown_to_plain(body_md))


def test_plain_part_strips_backticks_from_raw_markdown():
    """plain_body is built from RAW markdown, not from HTML.

    Fixing only markdown_to_html left literal backticks in the text/plain MIME
    part — invisible in the HTML preview, visible to plain-text readers and
    spam heuristics.
    """
    plain = sn.markdown_to_plain("entry type of `Mail - Commercial` here")
    assert "`" not in plain
    assert "Mail - Commercial" in plain


def test_plain_part_strips_code_tags_from_html_input():
    plain = sn.markdown_to_plain("<p>see <code>CP</code> now</p>")
    assert "`" not in plain
    assert "<code" not in plain
    assert "CP" in plain


def test_plain_part_list_handling_diverges_from_html_by_design():
    """The raw-markdown and HTML paths legitimately disagree about bullets.

    `- ` is how a bullet is *rendered* in text/plain, so the raw path keeps the
    dash; the HTML path emits a real <ul>/<li>, so markdown_to_plain only has to
    drop the tags. Asserted here as intended behaviour, not as a bug to fix:
    collapsing both to bare words would make the plain part unreadable.
    """
    from_raw = sn.markdown_to_plain("- alpha\n- beta\n- gamma")
    assert from_raw.count("- ") == 3

    lines = [ln.strip() for ln in from_raw.splitlines() if ln.strip()]
    assert lines == ["- alpha", "- beta", "- gamma"]

    from_html = sn.markdown_to_plain(sn.markdown_to_html("- alpha\n- beta\n- gamma"))
    assert "<li" not in from_html
    assert [ln.strip() for ln in from_html.splitlines() if ln.strip()] == [
        "alpha",
        "beta",
        "gamma",
    ]


class TestHeaderAndInlineImages:
    """Email images: full-bleed header + inline product rows (convention §3/§8).

    Neither MAP nor EMAIL_STYLE_CONVENTION.md specifies sizing for email
    derivatives, so these lock in the choices made here: 600 CSS px header,
    alt text always required, and remote URLs only (never embedded bytes).
    """

    def test_header_renders_full_bleed_under_saffron_rule(self):
        from send_newsletter import build_email_html, build_header_html

        h = build_email_html(
            "<p>x</p>",
            header_html=build_header_html("https://e/x.jpg", "Cargo on the boat"),
        )
        assert h.count("<img") == 1
        # 600 CSS px, fluid, no border artefacts
        assert 'width="600"' in h
        assert "max-width:600px" in h
        assert "display:block" in h
        # saffron rule must precede the image, i.e. header sits below it
        assert h.index("C98A2D") < h.index("<img")

    def test_header_absent_leaves_shell_unchanged(self):
        """Existing sends must stay byte-identical: no header => no <img>."""
        from send_newsletter import build_email_html

        assert build_email_html("<p>x</p>").count("<img") == 0

    def test_header_alt_is_escaped_not_injected(self):
        from send_newsletter import build_header_html

        h = build_header_html("https://e/x.jpg", '"><script>alert(1)</script>')
        assert "<script>" not in h
        assert "&lt;script&gt;" in h or "&quot;" in h

    def test_inline_images_repeat_flag_builds_rows(self):
        from send_newsletter import build_inline_images_html

        h = build_inline_images_html(["https://e/a.jpg", "https://e/b.jpg"])
        assert h.count("<img") == 2
        # product images are capped narrower than the header
        assert 'width="280"' in h

    def test_inline_images_none_is_empty(self):
        from send_newsletter import build_inline_images_html

        assert build_inline_images_html(None) == ""
        assert build_inline_images_html([]) == ""
