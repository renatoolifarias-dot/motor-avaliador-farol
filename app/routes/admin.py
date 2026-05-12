"""Admin de usuários."""
import secrets, string
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.services.auth import (
    exige_admin, hash_senha, csrf_token, csrf_verifica, flash
)
from app.models import Usuario

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")


def _gera_senha_temp() -> str:
    alfa = string.ascii_uppercase
    return (
        "".join(secrets.choice(alfa) for _ in range(4)) + "-" +
        "".join(secrets.choice("0123456789") for _ in range(2)) + "-" +
        "".join(secrets.choice(string.ascii_lowercase) for _ in range(4))
    )


@router.get("/usuarios", response_class=HTMLResponse)
async def usuarios(request: Request, admin=Depends(exige_admin), session: AsyncSession = Depends(get_session)):
    usuarios = (await session.scalars(select(Usuario).order_by(Usuario.criado_em.desc()))).all()
    return templates.TemplateResponse(request, "admin_usuarios.html", {
        "request": request,
        "user": admin,
        "usuarios": usuarios,
        "csrf": csrf_token(request),
    })


@router.post("/usuarios/criar")
async def criar_usuario(
    request: Request,
    username: str = Form(...),
    nome_completo: str = Form(...),
    email: str = Form(...),
    perfil: str = Form(...),
    csrf: str = Form(..., alias='csrf_token'),
    admin=Depends(exige_admin),
    session: AsyncSession = Depends(get_session),
):
    if not csrf_verifica(request, csrf):
        flash(request, "erro", "CSRF inválido")
        return RedirectResponse("/admin/usuarios", status_code=303)
    senha_temp = _gera_senha_temp()
    novo = Usuario(
        username=username.strip().lower(),
        nome_completo=nome_completo.strip(),
        email=email.strip().lower(),
        perfil=perfil if perfil in ("admin", "avaliador") else "avaliador",
        senha_hash=hash_senha(senha_temp),
        ativo=True,
        precisa_trocar_senha=True,
    )
    session.add(novo)
    try:
        await session.commit()
        flash(request, "sucesso", f"Usuário <strong>{novo.username}</strong> criado. Senha temporária: <code>{senha_temp}</code> (informe e ele troca no 1º login).")
    except Exception as e:
        await session.rollback()
        flash(request, "erro", f"Erro ao criar: {e}")
    return RedirectResponse("/admin/usuarios", status_code=303)


@router.post("/usuarios/{uid}/toggle")
async def toggle_ativo(
    uid: int, request: Request, csrf: str = Form(..., alias='csrf_token'),
    admin=Depends(exige_admin), session: AsyncSession = Depends(get_session),
):
    if not csrf_verifica(request, csrf):
        return RedirectResponse("/admin/usuarios", status_code=303)
    user = await session.get(Usuario, uid)
    if user and user.id != admin.id:
        user.ativo = not user.ativo
        await session.commit()
        flash(request, "sucesso", f"Usuário {user.username} {'ativado' if user.ativo else 'desativado'}.")
    return RedirectResponse("/admin/usuarios", status_code=303)


@router.post("/usuarios/{uid}/reset-senha")
async def reset_senha(
    uid: int, request: Request, csrf: str = Form(..., alias='csrf_token'),
    admin=Depends(exige_admin), session: AsyncSession = Depends(get_session),
):
    if not csrf_verifica(request, csrf):
        return RedirectResponse("/admin/usuarios", status_code=303)
    user = await session.get(Usuario, uid)
    if user:
        senha_temp = _gera_senha_temp()
        user.senha_hash = hash_senha(senha_temp)
        user.precisa_trocar_senha = True
        await session.commit()
        flash(request, "sucesso", f"Nova senha para <strong>{user.username}</strong>: <code>{senha_temp}</code>")
    return RedirectResponse("/admin/usuarios", status_code=303)
