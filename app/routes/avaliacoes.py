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

    # Sprint 2: portais semente + páginas crawleadas
    seeds = (await session.scalars(
        select(AvaliacaoPagina)
        .where(AvaliacaoPagina.avaliacao_id == aid, AvaliacaoPagina.profundidade == -1)
        .order_by(AvaliacaoPagina.id)
    )).all()
    paginas = (await session.scalars(
        select(AvaliacaoPagina)
        .where(AvaliacaoPagina.avaliacao_id == aid, AvaliacaoPagina.profundidade >= 0)
        .order_by(AvaliacaoPagina.profundidade, AvaliacaoPagina.id)
    )).all()
    logs = (await session.scalars(
        select(AvaliacaoLog)
        .where(AvaliacaoLog.avaliacao_id == aid)
        .order_by(AvaliacaoLog.criado_em.desc())
        .limit(15)
    )).all()

    return templates.TemplateResponse(request, "avaliacao_detalhe.html", {
        "request": request,
        "user": user,
        "avaliacao": av,
        "total": total or 0,
        "pontuados": pontuados or 0,
        "seeds": seeds,
        "paginas": paginas,
        "logs": logs,
        "csrf": csrf_token(request),
    })


# =========================================================
# Sprint 2 — descobrir portais + crawler
# =========================================================
from fastapi import BackgroundTasks
from app.services.runner import descobrir_portais, crawlear_avaliacao
from app.models import AvaliacaoPagina, AvaliacaoLog


@router.post("/avaliacoes/{aid}/descobrir")
async def descobrir_post(
    aid: int, request: Request,
    csrf: str = Form(..., alias="csrf_token"),
    user=Depends(exige_login),
):
    if not csrf_verifica(request, csrf):
        flash(request, "erro", "CSRF inválido")
        return RedirectResponse(f"/avaliacoes/{aid}", status_code=303)
    try:
        res = await descobrir_portais(aid)
        if "erro" in res:
            flash(request, "erro", f"Falha: {res['erro']}")
        else:
            flash(request, "sucesso",
                  f"🔍 {res['portais_encontrados']} portais descobertos "
                  f"({res['protegidos_cloudflare']} protegidos por Cloudflare — Playwright vai cuidar).")
    except Exception as e:
        flash(request, "erro", f"Erro no descobridor: {str(e)[:200]}")
    return RedirectResponse(f"/avaliacoes/{aid}", status_code=303)


@router.post("/avaliacoes/{aid}/crawl")
async def crawl_post(
    aid: int, request: Request, background: BackgroundTasks,
    csrf: str = Form(..., alias="csrf_token"),
    user=Depends(exige_login),
):
    if not csrf_verifica(request, csrf):
        flash(request, "erro", "CSRF inválido")
        return RedirectResponse(f"/avaliacoes/{aid}", status_code=303)

    # Dispara em background — pode levar minutos
    background.add_task(crawlear_avaliacao, aid, 60, 2)
    flash(request, "info",
          "🕷️ Crawler iniciado em segundo plano. "
          "Atualize a página em ~2 minutos pra ver as páginas capturadas.")
    return RedirectResponse(f"/avaliacoes/{aid}", status_code=303)


@router.post("/avaliacoes/{aid}/avaliar")
async def avaliar_post(
    aid: int, request: Request, background: BackgroundTasks,
    csrf: str = Form(..., alias="csrf_token"),
    user=Depends(exige_login),
    session: AsyncSession = Depends(get_session),
):
    if not csrf_verifica(request, csrf):
        flash(request, "erro", "CSRF inválido")
        return RedirectResponse(f"/avaliacoes/{aid}", status_code=303)

    # Pré-checagens
    av = await session.get(Avaliacao, aid)
    if not av:
        raise HTTPException(404)

    paginas = await session.scalar(
        select(func.count()).select_from(AvaliacaoPagina)
        .where(AvaliacaoPagina.avaliacao_id == aid, AvaliacaoPagina.profundidade >= 0)
    )
    if not paginas:
        flash(request, "erro", "Rode o crawler antes — sem dossiê não há o que a IA avaliar.")
        return RedirectResponse(f"/avaliacoes/{aid}", status_code=303)

    # Checagem da API key
    from sqlalchemy import text as _text
    r = await session.execute(_text("SELECT valor FROM configs WHERE chave='anthropic_api_key'"))
    row = r.first()
    if not (row and row[0]):
        flash(request, "erro", "Configure a chave da API Anthropic em /configuracoes/")
        return RedirectResponse(f"/avaliacoes/{aid}", status_code=303)

    from app.services.avaliador import avaliar_avaliacao
    background.add_task(avaliar_avaliacao, aid)
    flash(request, "info",
          "🤖 Avaliação por IA iniciada (~5 a 15 min). "
          "Atualize a página pra acompanhar; cada dimensão pontua ~10 indicadores por vez.")
    return RedirectResponse(f"/avaliacoes/{aid}", status_code=303)
