"""Tela de revisão: avaliador confirma/ajusta cada um dos 122 itens."""
import json
from pathlib import Path
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.services.auth import exige_login, csrf_token, csrf_verifica, flash
from app.services.tz import now_bahia
from app.models import Avaliacao, AvaliacaoItem, Indicador

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _carregar_indicadores_dict() -> dict:
    p = Path(__file__).parent.parent / "data" / "indicadores.json"
    return {i["codigo"]: i for i in json.load(p.open())["indicadores"]}


@router.get("/avaliacoes/{aid}/revisar", response_class=HTMLResponse)
async def revisar(
    aid: int, request: Request,
    secao: str = "Geral",
    user=Depends(exige_login),
    session: AsyncSession = Depends(get_session),
):
    av = await session.get(Avaliacao, aid)
    if not av:
        raise HTTPException(404, "Avaliação não encontrada")

    # Carrega indicadores do JSON (com perguntas íntegras)
    ind_full = _carregar_indicadores_dict()

    # Carrega itens da avaliação
    itens = (await session.scalars(
        select(AvaliacaoItem)
        .where(AvaliacaoItem.avaliacao_id == aid)
    )).all()
    itens_by_cod = {i.codigo: i for i in itens}

    # Monta linha por código (mantendo ordem do JSON)
    linhas = []
    for cod, info in ind_full.items():
        if info.get("secao") != secao:
            continue
        item = itens_by_cod.get(cod)
        linhas.append({
            "codigo": cod,
            "secao": info["secao"],
            "dim_nome": info["dim_nome"],
            "pergunta": info["pergunta"],
            "opcoes": info["opcoes_resposta"],
            "peso": info["peso"],
            "nota_max": info["nota_max"],
            "item": item,
        })

    # Stats globais
    total = await session.scalar(select(func.count()).select_from(AvaliacaoItem).where(AvaliacaoItem.avaliacao_id == aid))
    revisados = await session.scalar(select(func.count()).select_from(AvaliacaoItem).where(AvaliacaoItem.avaliacao_id == aid, AvaliacaoItem.revisado_humano == True))
    pontuados = await session.scalar(select(func.count()).select_from(AvaliacaoItem).where(AvaliacaoItem.avaliacao_id == aid, AvaliacaoItem.nota.is_not(None)))

    # Nota geral
    nota_calc = await session.execute(
        select(
            func.sum(AvaliacaoItem.nota * Indicador.peso),
            func.sum(Indicador.peso),
        ).select_from(Indicador).join(
            AvaliacaoItem,
            (AvaliacaoItem.codigo == Indicador.codigo) & (AvaliacaoItem.avaliacao_id == aid),
        )
    )
    soma, peso_total = nota_calc.first()
    nota_geral = round(float(soma or 0) * 100 / float(peso_total or 1), 2) if peso_total else 0

    return templates.TemplateResponse(request, "revisao.html", {
        "request": request,
        "user": user,
        "avaliacao": av,
        "linhas": linhas,
        "secao_atual": secao,
        "secoes": ["Geral", "Saúde", "Clima"],
        "stats": {
            "total": total or 0,
            "pontuados": pontuados or 0,
            "revisados": revisados or 0,
            "nota_geral": nota_geral,
        },
        "csrf": csrf_token(request),
    })


@router.post("/avaliacoes/{aid}/revisar/{codigo}")
async def salvar_item(
    aid: int, codigo: str, request: Request,
    nota: float = Form(...),
    justificativa: str = Form(""),
    url_evidencia: str = Form(""),
    o_que_falta: str = Form(""),
    revisado: int = Form(1),
    csrf: str = Form(..., alias="csrf_token"),
    user=Depends(exige_login),
    session: AsyncSession = Depends(get_session),
):
    if not csrf_verifica(request, csrf):
        flash(request, "erro", "CSRF inválido")
        return RedirectResponse(f"/avaliacoes/{aid}/revisar", status_code=303)

    item = await session.scalar(
        select(AvaliacaoItem).where(
            AvaliacaoItem.avaliacao_id == aid,
            AvaliacaoItem.codigo == codigo,
        )
    )
    if not item:
        raise HTTPException(404)

    item.nota = float(nota)
    item.justificativa = justificativa or item.justificativa
    item.url_evidencia = url_evidencia or item.url_evidencia
    item.o_que_falta = o_que_falta or item.o_que_falta
    item.revisado_humano = bool(revisado)
    if revisado:
        item.revisor_id = user.id
        item.revisado_em = now_bahia()
    await session.commit()

    return {"ok": True, "codigo": codigo, "nota": float(nota)}


@router.post("/avaliacoes/{aid}/confirmar")
async def confirmar(
    aid: int, request: Request,
    csrf: str = Form(..., alias="csrf_token"),
    user=Depends(exige_login),
    session: AsyncSession = Depends(get_session),
):
    if not csrf_verifica(request, csrf):
        flash(request, "erro", "CSRF inválido")
        return RedirectResponse(f"/avaliacoes/{aid}/revisar", status_code=303)

    av = await session.get(Avaliacao, aid)
    if not av:
        raise HTTPException(404)

    # Calcula nota final e classificação
    nota_calc = await session.execute(
        select(
            func.sum(AvaliacaoItem.nota * Indicador.peso),
            func.sum(Indicador.peso),
        ).select_from(Indicador).join(
            AvaliacaoItem,
            (AvaliacaoItem.codigo == Indicador.codigo) & (AvaliacaoItem.avaliacao_id == aid),
        )
    )
    soma, peso_total = nota_calc.first()
    nota_geral = round(float(soma or 0) * 100 / float(peso_total or 1), 2)

    # Classificação ITGP (3ª edição)
    if nota_geral >= 75:
        classif = "Alta"
    elif nota_geral >= 50:
        classif = "Média"
    elif nota_geral >= 25:
        classif = "Baixa"
    else:
        classif = "Mínima"

    av.nota_geral = nota_geral
    av.classificacao = classif
    av.status = "confirmado"
    av.atualizado_em = now_bahia()
    await session.commit()

    flash(request, "sucesso", f"✓ Avaliação confirmada · Nota {nota_geral:.2f}/100 · Classificação {classif}")
    return RedirectResponse(f"/avaliacoes/{aid}", status_code=303)
