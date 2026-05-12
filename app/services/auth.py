"""Login, logout, sessões, CSRF, decoradores de proteção."""
import secrets
from datetime import datetime
from typing import Optional
from fastapi import Request, HTTPException, Depends, status
from fastapi.responses import RedirectResponse
import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionFactory, get_session
from app.models import Usuario

# bcrypt direto (passlib 1.7 quebra com bcrypt >=4.1)


def hash_senha(senha: str) -> str:
    # bcrypt limita a 72 bytes; truncamos pra evitar erro
    return bcrypt.hashpw(senha.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verifica_senha(senha: str, hash_: str) -> bool:
    try:
        return bcrypt.checkpw(senha.encode("utf-8")[:72], hash_.encode("utf-8"))
    except Exception:
        return False


# ---------- sessão ----------
async def usuario_atual(request: Request, session: AsyncSession = Depends(get_session)) -> Optional[Usuario]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = await session.get(Usuario, user_id)
    if not user or not user.ativo:
        return None
    return user


async def exige_login(request: Request, session: AsyncSession = Depends(get_session)) -> Usuario:
    user = await usuario_atual(request, session)
    if not user:
        # redirect (Flask-style)
        raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": "/login"})
    return user


async def exige_admin(request: Request, session: AsyncSession = Depends(get_session)) -> Usuario:
    user = await exige_login(request, session)
    if user.perfil != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")
    return user


# ---------- CSRF ----------
def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_hex(16)
        request.session["csrf"] = token
    return token


def csrf_verifica(request: Request, token: str) -> bool:
    saved = request.session.get("csrf")
    return bool(saved) and secrets.compare_digest(saved, token)


# ---------- flash ----------
def flash(request: Request, tipo: str, msg: str) -> None:
    """tipo: 'sucesso' | 'erro' | 'info' | 'aviso'"""
    msgs = request.session.get("_flash", [])
    msgs.append({"tipo": tipo, "msg": msg})
    request.session["_flash"] = msgs


def consome_flash(request: Request) -> list:
    msgs = request.session.get("_flash", [])
    request.session["_flash"] = []
    return msgs


# ---------- helper de login ----------
async def autenticar(session: AsyncSession, username: str, senha: str) -> Optional[Usuario]:
    user = await session.scalar(select(Usuario).where(Usuario.username == username))
    if not user or not user.ativo:
        return None
    if not verifica_senha(senha, user.senha_hash):
        return None
    user.ultimo_login = datetime.utcnow()
    await session.commit()
    return user
