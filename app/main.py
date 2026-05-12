"""FastAPI entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    settings = get_settings()
    print(f"🚀 {settings.app_name} ({settings.app_env}) iniciando…")
    yield
    # shutdown
    print("👋 Encerrando.")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        debug=settings.debug,
        lifespan=lifespan,
    )

    # Sessões (cookies HTTP-only assinados)
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, max_age=8 * 3600, https_only=False)

    # Static files (CSS, JS, imagens)
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    # Rotas
    from app.routes import health, auth, dashboard
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(dashboard.router)

    return app


app = create_app()
