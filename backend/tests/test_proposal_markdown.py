"""
Unit tests for app.core.markdown.render_markdown.

Verifies:
- Markdown elements render to expected HTML
- XSS payloads are stripped
- External links get safe rel attributes
- Empty input returns empty output
"""

import pytest
from app.core.markdown import render_markdown


def test_plain_text_wrapped_in_p():
    result = render_markdown("Hello world")
    assert "<p>Hello world</p>" in result


def test_h2_gets_id_attribute():
    result = render_markdown("## Heading")
    assert 'id="heading"' in result
    assert "<h2" in result
    assert "Heading" in result


def test_h3_gets_id_attribute():
    result = render_markdown("### Sub")
    assert 'id="sub"' in result
    assert "<h3" in result
    assert "Sub" in result


def test_script_tag_not_injected():
    # markdown-it renders html=False, so raw HTML is HTML-escaped, not stripped.
    # The important guarantee is that <script> cannot be injected as a live tag.
    result = render_markdown("<script>alert(1)</script>")
    assert "<script>" not in result  # no executable script element


def test_external_link_gets_safe_rel():
    result = render_markdown("[Click here](https://example.com)")
    assert "noopener" in result
    assert "nofollow" in result
    assert "ugc" in result
    assert "https://example.com" in result


def test_table_renders():
    md = "| A | B |\n|---|---|\n| 1 | 2 |"
    result = render_markdown(md)
    assert "<table>" in result
    assert "<td>" in result


def test_empty_string_returns_empty():
    assert render_markdown("") == ""


def test_strikethrough():
    result = render_markdown("~~deleted~~")
    assert "<s>" in result or "<del>" in result


def test_inline_code_preserved():
    result = render_markdown("`code()`")
    assert "<code>" in result
    assert "code()" in result


def test_html_comment_not_rendered():
    # html=False causes HTML comments to be escaped, not stripped.
    # The important guarantee is that the comment is not rendered as a live HTML node.
    result = render_markdown("<!-- hidden -->visible")
    assert "<!--" not in result  # comment markup not passed through as raw HTML
    assert "visible" in result
