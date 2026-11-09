import logging
import math
import time
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import Response

from .config import Settings
from .database import DATABASE_ERRORS, Database, FeedbackQuotaReached

STATIC = Path(__file__).parent / "static"
logger = logging.getLogger("feedback_board")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


class FeedbackInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(min_length=1, max_length=60)
    message: str = Field(min_length=1, max_length=500)


class FeedbackItem(BaseModel):
    id: int
    name: str
    message: str
    created_at: datetime


class FeedbackList(BaseModel):
    total: int
    items: list[FeedbackItem]


class WriteLimiter:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.timestamps: deque[float] = deque()
        self.lock = Lock()

    def retry_after(self) -> int:
        with self.lock:
            now = time.monotonic()
            while self.timestamps and self.timestamps[0] <= now - 60:
                self.timestamps.popleft()
            if len(self.timestamps) >= self.limit:
                return max(1, math.ceil(60 - (now - self.timestamps[0])))
            self.timestamps.append(now)
            return 0


def unavailable() -> JSONResponse:
    return JSONResponse(
        {"detail": "Database is unavailable. Please try again shortly."},
        status_code=503,
        headers={"Retry-After": "10"},
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    database = Database(config)
    limiter = WriteLimiter(config.write_limit)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        try:
            await run_in_threadpool(database.initialize)
        except DATABASE_ERRORS:
            raise RuntimeError(
                "Database setup failed. Check DATABASE_URL and apply schema.sql for cloud use."
            ) from None
        logger.info("application ready database=%s", database.kind)
        yield

    application = FastAPI(
        title="Feedback Board",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    application.state.database = database

    @application.middleware("http")
    async def security_and_logs(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = time.monotonic()
        response = await call_next(request)
        response.headers.update(
            {
                "Content-Security-Policy": (
                    "default-src 'self'; script-src 'self'; style-src 'self'; "
                    "connect-src 'self'; img-src 'self'; object-src 'none'; "
                    "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
                ),
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
                "Cache-Control": "no-store",
            }
        )
        path = request.url.path
        route = path if path in {"/", "/api/feedback", "/health", "/robots.txt"} else "other"
        method = request.method if request.method in {"GET", "POST", "HEAD"} else "OTHER"
        logger.info(
            "request method=%s route=%s status=%s duration_ms=%.1f",
            method,
            route,
            response.status_code,
            (time.monotonic() - started) * 1000,
        )
        return response

    @application.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @application.get("/health")
    def health() -> Response:
        try:
            database.check()
        except DATABASE_ERRORS:
            return unavailable()
        return JSONResponse({"status": "ok", "database": database.kind})

    @application.get("/api/feedback", response_model=FeedbackList)
    def list_feedback() -> FeedbackList | JSONResponse:
        try:
            return FeedbackList.model_validate(database.recent())
        except DATABASE_ERRORS:
            return unavailable()

    @application.post("/api/feedback", response_model=FeedbackItem, status_code=201)
    async def save_feedback(request: Request) -> FeedbackItem | JSONResponse:
        if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            return JSONResponse({"detail": "Send feedback as JSON."}, status_code=415)
        origin = request.headers.get("origin")
        host = request.headers.get("host", "")
        if origin and origin not in {f"https://{host}", f"http://{host}"}:
            return JSONResponse({"detail": "Cross-site submissions are disabled."}, status_code=403)
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 8192:
                return JSONResponse({"detail": "Feedback is too large."}, status_code=413)
            body.extend(chunk)
        try:
            feedback = FeedbackInput.model_validate_json(body)
        except ValidationError:
            return JSONResponse(
                {"detail": "Enter a name (1–60 characters) and a message (1–500 characters)."},
                status_code=422,
            )
        retry = limiter.retry_after()
        if retry:
            return JSONResponse(
                {"detail": "Too many submissions. Please wait a minute and try again."},
                status_code=429,
                headers={"Retry-After": str(retry)},
            )
        try:
            saved = await run_in_threadpool(database.add, feedback.name, feedback.message)
            return FeedbackItem.model_validate(saved)
        except FeedbackQuotaReached:
            return JSONResponse(
                {"detail": "This feedback board has reached its message limit."}, status_code=409
            )
        except DATABASE_ERRORS:
            return unavailable()

    @application.get("/robots.txt", include_in_schema=False)
    def robots() -> PlainTextResponse:
        return PlainTextResponse("User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /health\n")

    application.mount("/static", StaticFiles(directory=STATIC), name="static")
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=config.hosts)
    return application


app = create_app()
