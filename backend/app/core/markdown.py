"""
Server-side markdown rendering for proposal bodies.

The same input always produces the same output — this is important because
annotation anchors reference text ranges in the rendered HTML. If rendering
were non-deterministic, anchors would drift.
"""
from markdown_it import MarkdownIt
from mdit_py_plugins.anchors import anchors_plugin
import bleach

_md = (
    MarkdownIt("commonmark", {"breaks": True, "linkify": True, "html": False})
    .enable("table")
    .enable("strikethrough")
    .use(anchors_plugin, min_level=2, max_level=3, slug_func=None, permalink=False)
)

_ALLOWED_TAGS = [
    "p", "br", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "em", "s", "del", "code", "pre",
    "ul", "ol", "li",
    "blockquote",
    "a",
    "table", "thead", "tbody", "tr", "th", "td",
    "span",
]
_ALLOWED_ATTRS = {
    "a": ["href", "title", "rel"],
    "h1": ["id"], "h2": ["id"], "h3": ["id"],
    "h4": ["id"], "h5": ["id"], "h6": ["id"],
    "th": ["align"], "td": ["align"],
    "span": ["class"],
}
_ALLOWED_PROTOCOLS = ["http", "https", "mailto"]


def render_markdown(source: str) -> str:
    """Render markdown → sanitized HTML. Safe for user-submitted input."""
    if not source:
        return ""
    html = _md.render(source)
    cleaned = bleach.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        protocols=_ALLOWED_PROTOCOLS,
        strip=True,
    )
    cleaned = bleach.linkify(
        cleaned,
        callbacks=[
            lambda attrs, new: {**attrs, (None, "rel"): "noopener nofollow ugc"},
        ],
    )
    return cleaned
