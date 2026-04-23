import re
from pathlib import Path

import markdown
import structlog
import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sentry_sdk.integrations.fastapi import FastApiIntegration

from app.config import settings
from app.api.v1.router import api_router

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ]
)

log = structlog.get_logger()

if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.05,
        environment="development" if settings.DEBUG else "production",
    )

app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Public deliberation platform: structured discussion → legitimate "
        "collective allocation. No outrage dynamics."
    ),
    version="0.1.0",
    # Disable interactive docs in production — audit surface only via /api/v1/audit
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.error("unhandled_exception", path=request.url.path, error=str(exc))
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(api_router, prefix="/api/v1")

# Serve static assets (CSS, JS)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Jinja2 templates — used only for wiki pages (existing pages use FileResponse)
templates = Jinja2Templates(directory="app/templates")

# ---------------------------------------------------------------------------
# Wiki helpers
# ---------------------------------------------------------------------------

WIKI_CONTENT_DIR = Path("app/wiki_content")

# Reading-order list of all article slugs. The index and prev/next nav follow this order.
WIKI_ARTICLES = [
    {
        "slug": "how-to-read-this",
        "title": "How to Read This",
        "section": "intro",
        "section_label": "",
    },
    {
        "slug": "1-1-how-a-bill-becomes-law",
        "title": "Article 1.1: How a Bill Becomes Law (State Level)",
        "section": "section1",
        "section_label": "Section 1: How Things Work",
    },
    {
        "slug": "1-2-how-lobbying-works",
        "title": "Article 1.2: How Lobbying Works",
        "section": "section1",
        "section_label": "Section 1: How Things Work",
    },
    {
        "slug": "1-3-logic-of-collective-action",
        "title": "Article 1.3: The Logic of Collective Action",
        "section": "section1",
        "section_label": "Section 1: How Things Work",
    },
    {
        "slug": "1-4-institutions-path-dependence",
        "title": "Article 1.4: Institutions, Path Dependence, and Why Change Is Slow",
        "section": "section1",
        "section_label": "Section 1: How Things Work",
    },
    {
        "slug": "1-5-deliberative-democracy",
        "title": "Article 1.5: What Deliberative Democracy Actually Claims (and Doesn't)",
        "section": "section1",
        "section_label": "Section 1: How Things Work",
    },
    {
        "slug": "1-6-democratic-backsliding",
        "title": "Article 1.6: Democratic Backsliding — What the Evidence Shows",
        "section": "section1",
        "section_label": "Section 1: How Things Work",
    },
    {
        "slug": "1-7-501c4-explainer",
        "title": "Article 1.7: What a 501(c)(4) Is and Isn't",
        "section": "section1",
        "section_label": "Section 1: How Things Work",
    },
    {
        "slug": "1-8-how-markets-fail",
        "title": "Article 1.8: How Markets Fail (and Why That Doesn't Mean Markets Are Bad)",
        "section": "section1",
        "section_label": "Section 1: How Things Work",
    },
    {
        "slug": "2-1-coordination-gap",
        "title": "Article 2.1: The Coordination Gap — Our Starting Diagnosis",
        "section": "section2",
        "section_label": "Section 2: Why This Platform Exists",
    },
    {
        "slug": "2-2-what-were-building",
        "title": "Article 2.2: What We're Building and Why We Think It Could Work",
        "section": "section2",
        "section_label": "Section 2: Why This Platform Exists",
    },
    {
        "slug": "2-3-intellectual-influences",
        "title": "Article 2.3: Our Intellectual Influences",
        "section": "section2",
        "section_label": "Section 2: Why This Platform Exists",
    },
    {
        "slug": "2-4-failure-modes",
        "title": "Article 2.4: Failure Modes We're Trying to Avoid",
        "section": "section2",
        "section_label": "Section 2: Why This Platform Exists",
    },
    {
        "slug": "3-1-open-questions",
        "title": "Article 3.1: Questions We Don't Answer For You",
        "section": "section3",
        "section_label": "Section 3: Open Questions",
    },
    {
        "slug": "3-2-worked-examples",
        "title": "Article 3.2: Worked Examples — Empirical vs. Values Distinction",
        "section": "section3",
        "section_label": "Section 3: Open Questions",
    },
    {
        "slug": "fact-check-checklist",
        "title": "Fact-Check Checklist",
        "section": "appendix",
        "section_label": "Appendix",
    },
]

# Build a slug → index map for O(1) prev/next lookup
_SLUG_INDEX = {a["slug"]: i for i, a in enumerate(WIKI_ARTICLES)}


def _slugify_heading(text: str) -> str:
    """Convert heading text to a stable id attribute (slug-cased)."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = text.strip("-")
    return text


def _ensure_heading_ids(html: str) -> str:
    """
    Post-process rendered HTML to add id attributes to every h2 and h3 that
    lacks one. The python-markdown toc extension adds ids automatically, but
    this ensures we never miss one regardless of extension config.
    """
    def add_id(m: re.Match) -> str:
        tag = m.group(1)         # "h2" or "h3"
        attrs = m.group(2)       # existing attributes (may be empty)
        content = m.group(3)     # inner text
        if 'id=' in attrs:
            return m.group(0)    # already has an id
        # Strip inner tags to get plain text for the slug
        plain = re.sub(r"<[^>]+>", "", content)
        slug = _slugify_heading(plain)
        return f"<{tag} id=\"{slug}\"{attrs}>{content}"

    return re.sub(
        r"<(h[23])([^>]*)>(.*?)</h[23]>",
        add_id,
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )


def _render_article(slug: str) -> str | None:
    """
    Read the markdown file for a slug, render to HTML, and post-process
    heading ids. Returns None if the file does not exist.
    """
    path = WIKI_CONTENT_DIR / f"{slug}.md"
    if not path.exists():
        return None

    md_text = path.read_text(encoding="utf-8")
    md = markdown.Markdown(
        extensions=["toc", "tables", "fenced_code", "attr_list"],
        extension_configs={
            "toc": {
                "slugify": lambda value, separator: _slugify_heading(value),
            }
        },
    )
    html = md.convert(md_text)
    html = _ensure_heading_ids(html)
    return html


# ---------------------------------------------------------------------------
# Health and API
# ---------------------------------------------------------------------------

@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


# ---------------------------------------------------------------------------
# Wiki routes (Jinja2 — dynamic rendering only)
# ---------------------------------------------------------------------------

@app.get("/wiki", response_class=HTMLResponse)
async def wiki_index(request: Request) -> HTMLResponse:
    # Render the intro article for the index page header
    intro_html = _render_article("how-to-read-this")
    return templates.TemplateResponse(
        request,
        "wiki_index.html",
        {
            "articles": WIKI_ARTICLES,
            "intro_html": intro_html,
        },
    )


@app.get("/wiki/{slug}", response_class=HTMLResponse)
async def wiki_article(request: Request, slug: str) -> HTMLResponse:
    content_html = _render_article(slug)
    if content_html is None:
        return HTMLResponse(status_code=404, content="<h1>Article not found</h1>")

    idx = _SLUG_INDEX.get(slug)
    prev_article = WIKI_ARTICLES[idx - 1] if idx is not None and idx > 0 else None
    next_article = WIKI_ARTICLES[idx + 1] if idx is not None and idx < len(WIKI_ARTICLES) - 1 else None

    # Find current article metadata
    article_meta = WIKI_ARTICLES[idx] if idx is not None else {"title": slug, "section_label": ""}

    return templates.TemplateResponse(
        request,
        "wiki_article.html",
        {
            "slug": slug,
            "article": article_meta,
            "content_html": content_html,
            "prev_article": prev_article,
            "next_article": next_article,
        },
    )


# ---------------------------------------------------------------------------
# Existing page routes (FileResponse — unchanged)
# ---------------------------------------------------------------------------

@app.get("/")
async def index_page() -> FileResponse:
    return FileResponse("app/templates/index.html")


@app.get("/how-it-works")
async def how_it_works_page() -> FileResponse:
    return FileResponse("app/templates/how-it-works.html")


@app.get("/quiz")
async def quiz_page() -> FileResponse:
    return FileResponse("app/templates/quiz.html")


@app.get("/signin")
async def signin_page() -> FileResponse:
    return FileResponse("app/templates/signin.html")


@app.get("/account")
async def account_page() -> FileResponse:
    return FileResponse("app/templates/account.html")


@app.get("/admin")
async def admin_page() -> FileResponse:
    return FileResponse("app/templates/admin.html")


@app.get("/audit")
async def audit_page() -> FileResponse:
    return FileResponse("app/templates/audit.html")


@app.get("/communities")
async def communities_page() -> FileResponse:
    return FileResponse("app/templates/communities.html")


# ---------------------------------------------------------------------------
# Legacy redirects — old flat URLs forward to community-scoped equivalents
# ---------------------------------------------------------------------------

@app.get("/threads")
async def threads_redirect() -> RedirectResponse:
    return RedirectResponse("/c/test/threads", status_code=302)


@app.get("/new-thread")
async def new_thread_redirect() -> RedirectResponse:
    return RedirectResponse("/c/test/new-thread", status_code=302)


@app.get("/thread/{thread_id}")
async def thread_redirect(thread_id: str) -> RedirectResponse:
    return RedirectResponse(f"/c/test/thread/{thread_id}", status_code=302)


# ---------------------------------------------------------------------------
# Community-scoped page routes
# ---------------------------------------------------------------------------

@app.get("/c/{slug}")
async def community_home_page(slug: str) -> FileResponse:
    return FileResponse("app/templates/community_home.html")


@app.get("/c/{slug}/threads")
async def community_threads_page(slug: str) -> FileResponse:
    return FileResponse("app/templates/threads.html")


@app.get("/c/{slug}/thread/{thread_id}")
async def community_thread_page(slug: str, thread_id: str) -> FileResponse:
    return FileResponse("app/templates/thread.html")


@app.get("/c/{slug}/new-thread")
async def community_new_thread_page(slug: str) -> FileResponse:
    return FileResponse("app/templates/new-thread.html")


@app.get("/c/{slug}/audit")
async def community_audit_page(slug: str) -> FileResponse:
    return FileResponse("app/templates/audit.html")


@app.get("/c/{slug}/members")
async def community_members_page(slug: str) -> FileResponse:
    return FileResponse("app/templates/community_members.html")


@app.get("/c/{slug}/admin")
async def community_admin_page(slug: str) -> FileResponse:
    return FileResponse("app/templates/community_admin.html")
