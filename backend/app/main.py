import structlog
import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
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


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


# Page routes
@app.get("/")
async def index_page() -> FileResponse:
    return FileResponse("app/templates/index.html")


@app.get("/how-it-works")
async def how_it_works_page() -> FileResponse:
    return FileResponse("app/templates/how-it-works.html")


@app.get("/quiz")
async def quiz_page() -> FileResponse:
    return FileResponse("app/templates/quiz.html")


@app.get("/threads")
async def threads_page() -> FileResponse:
    return FileResponse("app/templates/threads.html")


@app.get("/thread/{thread_id}")
async def thread_page(thread_id: str) -> FileResponse:
    return FileResponse("app/templates/thread.html")


@app.get("/signin")
async def signin_page() -> FileResponse:
    return FileResponse("app/templates/signin.html")


@app.get("/account")
async def account_page() -> FileResponse:
    return FileResponse("app/templates/account.html")


@app.get("/new-thread")
async def new_thread_page() -> FileResponse:
    return FileResponse("app/templates/new-thread.html")


@app.get("/admin")
async def admin_page() -> FileResponse:
    return FileResponse("app/templates/admin.html")
