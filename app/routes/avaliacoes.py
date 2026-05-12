"""Avaliações: listagem, criação."""
import re
from datetime import datetime
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.services.auth import (
    exige_login, csrf_token, csrf_verifica, flash
)
from app.models import Avaliacao, AvaliacaoItem, Indicador, Usuario

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def slug_cidade(nome: str) -> str:
    """Slug sem acentos, lowercase, com hífens."""
    de = "áàãâäåéèêëíìîïóòõôöúùûüçñÁÀÃÂÄÅÉÈÊËÍÌÎÏÓÒÕÔÖÚÙÛÜÇÑ"
    para = "aaaaaaeeeeiiiiooooouuuucnAAAAAAEEEEIIIIOOOOOUUUUCN"
    tabela = str.maketrans(de, para)
    s = nome.translate(tabela).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, user=Depends(exige_login), session: AsyncSession = Depends(get_session)):
    # Estatísticas pro dashboard
    total_aval = await session.scalar(select(func.count()).select_from(Avaliacao))
    total_ind = await session.scalar(select(func.count()).select_from(Indicador))
    publicados = await session.scalar(select(func.count()).select_from(Avaliacao).where(Avaliacao.status == "publicado"))
    total_user = await session.scalar(select(func.count()).select_from(Usuario))

    avaliacoes = (await session.scalars(
        select(Avaliacao).order_by(Avaliacao.atualizado_em.desc()).limit(20)
    )).all()

    return templates.TemplateResponse(request, "dashboard.html", {
        "request": request,
        "user": user,
        "app_name": "Avaliador Farol Público",
        "stats": {
            "avaliacoes": total_aval or 0,
            "indicadores": total_ind or 0,
            "publicados": publicados or 0,
            "usuarios": total_user or 0,
        },
        "avaliacoes": avaliacoes,
    })


@router.get("/nova", response_class=HTMLResponse)
async def nova_get(request: Request, user=Depends(exige_login)):
    return templates.TemplateResponse(request, "avaliacao_nova.html", {
        "request": request,
        "user": user,
        "csrf": csrf_token(request),
    })


@router.post("/nova")
async def nova_post(
    request: Request,
    cidade: str = Form(...),
    uf: str = Form(...),
    ciclo: int = Form(2026),
    csrf: str = Form(..., alias='csrf_token'),
    user=Depends(exige_login),
    session: AsyncSession = Depends(get_session),
):
    if not csrf_verifica(request, csrf):
        flash(request, "erro", "Token CSRF inválido.")
        return RedirectResponse("/nova", status_code=303)

    cidade = cidade.strip()
    uf = uf.strip().upper()
    slug = slug_cidade(cidade)

    # Verifica duplicação
    existente = await session.scalar(select(Avaliacao).where(Avaliacao.slug == slug, Avaliacao.ciclo == ciclo))
    if existente:
        flash(request, "info", f"Já existe avaliação de {cidade} no ciclo {ciclo}. Abrindo.")
        return RedirectResponse(f"/avaliacoes/{existente.id}", status_code=303)

    # Cria avaliação
    av = Avaliacao(
        slug=slug, cidade=cidade, uf=uf, ciclo=ciclo,
        status="rascunho", avaliador_id=user.id,
    )
    session.add(av)
    await session.flush()  # pra ter av.id

    # Cria itens vazios pra cada indicador (122)
    indicadores = (await session.scalars(select(Indicador))).all()
    for ind in indicadores:
        session.add(AvaliacaoItem(avaliacao_id=av.id, codigo=ind.codigo))
    await session.commit()

    flash(request, "sucesso", f"Avaliação de <strong>{cidade}/{uf}</strong> criada com {len(indicadores)} indicadores prontos.")
    return RedirectResponse(f"/avaliacoes/{av.id}", status_code=303)


@router.get("/avaliacoes/{aid}", response_class=HTMLResponse)
async def detalhar(aid: int, request: Request, user=Depends(exige_login), session: AsyncSession = Depends(get_session)):
    av = await session.get(Avaliacao, aid)
    if not av:
        raise HTTPException(404, "Avaliação não encontrada")

    # Conta itens
    total = await session.scalar(
        select(func.count()).select_from(AvaliacaoItem).where(AvaliacaoItem.avaliacao_id == aid)
    )
    pontuados = await session.scalar(
        select(func.count()).select_from(AvaliacaoItem)
        .where(AvaliacaoItem.avaliacao_id == aid, AvaliacaoItem.nota.is_not(None))
    )
    return templates.TemplateResponse(request, "avaliacao_detalhe.html", {
        "request": request,
        "user": user,
        "avaliacao": av,
        "total": total or 0,
        "pontuados": pontuados or 0,
        "csrf": csrf_token(request),
    })
