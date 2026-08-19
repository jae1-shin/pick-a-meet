from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.database import SessionFactory, engine
from app.routers import admin, auth, host, pages
from app.services.registration_window import load_registration_window


BASE_DIR = Path(__file__).resolve().parent
settings = get_settings()
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.image_storage_path.mkdir(parents=True, exist_ok=True)
    async with SessionFactory() as session:
        await load_registration_window(session)
    yield
    await engine.dispose()


app = FastAPI(title="모임 신청", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key.get_secret_value(),
    max_age=settings.session_timeout_seconds,
    same_site="lax",
    https_only=settings.session_cookie_secure,
    session_cookie="meeting_session",
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(auth.router)
app.include_router(pages.router)
app.include_router(admin.router)
app.include_router(host.router)


@app.get("/")
async def index(request: Request) -> RedirectResponse:
    destination = "/meetings" if request.session.get("member_id") else "/login"
    return RedirectResponse(destination, status_code=303)


@app.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def ready() -> JSONResponse:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready"},
        )
    return JSONResponse(content={"status": "ok"})
