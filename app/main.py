from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.admin import admin_router
from app.admin.deps import NotAuthenticatedError
from app.admin.paths import STATIC_DIR
from app.bot_menu import register_bot_commands
from app.config import get_settings
from app.db.session import SessionLocal, init_db
from app.handlers.update_router import UpdateRouter
from app.handlers.webhook import router as webhook_router
from app.logging_setup import setup_logging
from app.max_api.client import MaxApiClient
from app.seed.content_seed import seed_content


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings)
    await init_db()
    async with SessionLocal() as session:
        await seed_content(session)

    api = MaxApiClient(settings)
    async with SessionLocal() as session:
        await register_bot_commands(api, session)
    app.state.api = api
    app.state.update_router = UpdateRouter(api)
    app.state.session_factory = SessionLocal
    try:
        yield
    finally:
        await api.aclose()


app = FastAPI(
    title="Про Финансы Ясно Bot",
    version="1.0.0",
    lifespan=lifespan,
)

_settings = get_settings()
app.add_middleware(
    SessionMiddleware,
    secret_key=_settings.admin_secret_key,
    session_cookie="bot_uv_admin",
    same_site="lax",
    https_only=False,
)

if _settings.admin_enabled:
    Path(STATIC_DIR).mkdir(parents=True, exist_ok=True)
    app.mount(
        "/admin/static",
        StaticFiles(directory=str(STATIC_DIR)),
        name="admin-static",
    )
    app.include_router(admin_router)

    @app.exception_handler(NotAuthenticatedError)
    async def admin_auth_redirect(_, __):
        return RedirectResponse(
            url="/admin/login",
            status_code=303,
        )

app.include_router(webhook_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
async def root():
    if get_settings().admin_enabled:
        return RedirectResponse("/admin/", status_code=302)
    return {"status": "ok", "service": "bot-uv"}
