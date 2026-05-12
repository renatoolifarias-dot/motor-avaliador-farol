"""Rotas de auth."""
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.services.auth import (
    autenticar, hash_senha, verifica_senha,
    csrf_token, csrf_verifica, flash, exige_login
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    return templates.TemplateResponse(request, "login.html", {
        "request": request,
        "csrf": csrf_token(request),
    })


@router.post("/login")
async def login_post(
    request: Request,
    username: str = Form(...),
    senha: str = Form(...),
    csrf: str = Form(..., alias='csrf_token'),
    session: AsyncSession = Depends(get_session),
):
    if not csrf_verifica(request, csrf):
        flash(request, "erro", "Token CSRF inválido. Tente novamente.")
        return RedirectResponse("/login", status_code=303)
    user = await autenticar(session, username.strip(), senha)
    if not user:
        flash(request, "erro", "Usuário ou senha incorretos.")
        return RedirectResponse("/login", status_code=303)
    request.session["user_id"] = user.id
    request.session["csrf"] = ""  # força novo token
    flash(request, "sucesso", f"Bem-vindo, {user.nome_completo}!")
    if user.precisa_trocar_senha:
        return RedirectResponse("/trocar-senha", status_code=303)
    return RedirectResponse("/", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/trocar-senha", response_class=HTMLResponse)
async def trocar_senha_get(request: Request, user=Depends(exige_login)):
    return templates.TemplateResponse(request, "trocar_senha.html", {
        "request": request, "user": user, "csrf": csrf_token(request),
    })


@router.post("/trocar-senha")
async def trocar_senha_post(
    request: Request,
    atual: str = Form(...),
    nova: str = Form(...),
    confirma: str = Form(...),
    csrf: str = Form(..., alias='csrf_token'),
    user=Depends(exige_login),
    session: AsyncSession = Depends(get_session),
):
    if not csrf_verifica(request, csrf):
        flash(request, "erro", "Token CSRF inválido.")
        return RedirectResponse("/trocar-senha", status_code=303)
    if not verifica_senha(atual, user.senha_hash):
        flash(request, "erro", "Senha atual incorreta.")
        return RedirectResponse("/trocar-senha", status_code=303)
    if len(nova) < 8:
        flash(request, "erro", "Nova senha precisa ter no mínimo 8 caracteres.")
        return RedirectResponse("/trocar-senha", status_code=303)
    if nova != confirma:
        flash(request, "erro", "Confirmação não confere.")
        return RedirectResponse("/trocar-senha", status_code=303)
    user.senha_hash = hash_senha(nova)
    user.precisa_trocar_senha = False
    await session.commit()
    flash(request, "sucesso", "Senha alterada com sucesso!")
    return RedirectResponse("/", status_code=303)
