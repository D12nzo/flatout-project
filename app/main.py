"""
Точка входа FastAPI-приложения FlatOut.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.routers import appointments, auth, barbers, branches, reports, services, users

BASE_DIR = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Схема БД управляется через Alembic — не вызываем create_all в production.
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Веб-платформа барбершопа FlatOut",
    lifespan=lifespan,
)

# Статика и шаблоны.
static_dir = BASE_DIR / "static"
templates_dir = BASE_DIR / "templates"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
templates = Jinja2Templates(directory=str(templates_dir))

# API.
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(branches.router, prefix="/api/branches", tags=["Branches"])
app.include_router(services.router, prefix="/api/services", tags=["Services"])
app.include_router(barbers.router, prefix="/api/barbers", tags=["Barbers"])
app.include_router(appointments.router, prefix="/api/appointments", tags=["Appointments"])
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])


@app.get("/health", tags=["Meta"])
async def healthcheck() -> dict[str, str]:
    return {"status": "healthy", "service": settings.APP_NAME, "version": settings.APP_VERSION}


# HTML-страницы.
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("dashboard.html", {"request": request})
