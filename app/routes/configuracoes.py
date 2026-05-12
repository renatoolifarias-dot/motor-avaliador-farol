"""Tela de configurações (admin only)."""
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.services.auth import exige_admin, csrf_token, csrf_verifica, flash
from app.config import get_settings
from sqlalchemy import text

router = APIRouter(prefix="/configuracoes")
templates = Jinja2Templates(directory="app/templates")


async def get_config(session: AsyncSession, chave: str, default: str = "") -> str:
    r = await session.execute(text("SELECT valor FROM configs WHERE chave=:k"), {"k": chave})
    row = r.first()
    return (row[0] if row else default) or default


async def set_config(session: AsyncSession, chave: str, valor: str) -> None:
    await session.execute(
        text("""
        INSERT INTO configs (chave, valor, atualizado_em) VALUES (:k, :v, now())
        ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor, atualizado_em = now()
        """),
        {"k": chave, "v": valor},
    )
    await session.commit()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, admin=Depends(exige_admin), session: AsyncSession = Depends(get_session)):
    s = get_settings()
    api_key = await get_config(session, "anthropic_api_key", s.anthropic_api_key)
    modelo = await get_config(session, "modelo_padrao", s.anthropic_model_default)
    return templates.TemplateResponse(request, "configuracoes.html", {
        "request": request,
        "user": admin,
        "csrf": csrf_token(request),
        "api_key_configurada": bool(api_key),
        "api_key_prefix": (api_key[:14] + "…" + api_key[-4:]) if api_key else "",
        "modelo_atual": modelo,
        "modelos": [
            ("claude-haiku-4-5-20251001", "Claude Haiku 4.5 (recomendado)"),
            ("claude-sonnet-4-6", "Claude Sonnet 4.6"),
            ("claude-opus-4-6", "Claude Opus 4.6"),
        ],
    })


@router.post("/api-key")
async def salvar_api_key(
    request: Request, api_key: str = Form(...), csrf: str = Form(..., alias='csrf_token'),
    admin=Depends(exige_admin), session: AsyncSession = Depends(get_session),
):
    if not csrf_verifica(request, csrf):
        flash(request, "erro", "CSRF")
        return RedirectResponse("/configuracoes/", status_code=303)
    api_key = api_key.strip()
    if api_key and not api_key.startswith("sk-ant-"):
        flash(request, "erro", "Formato inválido (deve começar com sk-ant-)")
    else:
        await set_config(session, "anthropic_api_key", api_key)
        flash(request, "sucesso", "API key salva." if api_key else "API key removida.")
    return RedirectResponse("/configuracoes/", status_code=303)


@router.post("/modelo")
async def salvar_modelo(
    request: Request, modelo: str = Form(...), csrf: str = Form(..., alias='csrf_token'),
    admin=Depends(exige_admin), session: AsyncSession = Depends(get_session),
):
    if not csrf_verifica(request, csrf):
        flash(request, "erro", "CSRF")
        return RedirectResponse("/configuracoes/", status_code=303)
    await set_config(session, "modelo_padrao", modelo)
    flash(request, "sucesso", f"Modelo definido: {modelo}")
    return RedirectResponse("/configuracoes/", status_code=303)
