"""FastAPI entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.services.auth import consome_flash
from app.services.bootstrap import bootstrap_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    print(f"🚀 {settings.app_name} ({settings.app_env}) iniciando…")
    try:
        await bootstrap_db()
    except Exception as e:
        print(f"⚠ bootstrap falhou: {e}")
    yield
    print("👋 Encerrando.")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", debug=settings.debug, lifespan=lifespan)

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        max_age=8 * 3600, https_only=False, same_site="lax",
    )

    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    # Jinja globals
    templates = Jinja2Templates(directory="app/templates")
    @app.middleware("http")
    async def inject_flash(request: Request, call_next):
        # disponibiliza função flash() no template
        request.state.consome_flash = consome_flash
        return await call_next(request)

    # Handler de redirect (a partir de exige_login)
    @app.exception_handler(StarletteHTTPException)
    async def http_exc_handler(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 307 and "Location" in (exc.headers or {}):
            return RedirectResponse(exc.headers["Location"], status_code=303)
        # Fallback simples pra 4xx/5xx
        from fastapi.responses import HTMLResponse
        return HTMLResponse(f"<h1>Erro {exc.status_code}</h1><p>{exc.detail}</p>", status_code=exc.status_code)

    # Rotas
    from app.routes import health, auth, avaliacoes, admin, configuracoes
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(avaliacoes.router)
    app.include_router(admin.router)
    app.include_router(configuracoes.router)
    return app


app = create_app()
