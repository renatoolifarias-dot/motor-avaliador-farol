"""Tools que o Claude usa via Tool Use para avaliar.

Cada tool recebe um `tool_use_id` (gerado pela Anthropic SDK) e retorna
o conteúdo a ser enviado no próximo turn como tool_result.

As 3 tools são:
- buscar_no_dossie(query) → 10 URLs com snippets
- ler_pagina(url) → texto completo (truncado)
- gravar_avaliacao(...) → "OK" + gravação no DB

Idempotência: gravar_avaliacao com o mesmo codigo sobrescreve (não duplica).
"""
from __future__ import annotations
from datetime import datetime
from app.services.tz import now_bahia
from typing import Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import AvaliacaoPagina, AvaliacaoItem


async def resumir_dossie(session: AsyncSession, avaliacao_id: int) -> str:
    """Gera um sumário inicial do dossiê pra incluir no prompt:
    lista das URLs com título e primeiro parágrafo (~200 chars)."""
    paginas = (await session.scalars(
        select(AvaliacaoPagina)
        .where(AvaliacaoPagina.avaliacao_id == avaliacao_id, AvaliacaoPagina.profundidade >= 0)
        .order_by(AvaliacaoPagina.profundidade, AvaliacaoPagina.id)
    )).all()

    linhas = []
    for p in paginas:
        texto = (p.texto or "").strip().replace("\n", " ")[:180]
        linhas.append(
            f"- [{p.tipo}] {p.url_final}\n"
            f"  título: {(p.titulo or '—')[:120]}\n"
            f"  início: {texto}…"
        )
    return "\n".join(linhas) if linhas else "(dossiê vazio — execute o crawler antes)"


# -----------------------------------------------------------------------
# tool: buscar_no_dossie
# -----------------------------------------------------------------------
async def buscar_no_dossie(
    session: AsyncSession, avaliacao_id: int, query: str
) -> dict:
    """Procura substring em texto/título. Retorna até 10 URLs com snippets."""
    q = (query or "").strip().lower()
    if not q:
        return {"erro": "query vazia"}

    # Usa ILIKE pro Postgres aproveitar índice GIN (se houver) ou trgm
    pat = f"%{q}%"
    paginas = (await session.scalars(
        select(AvaliacaoPagina)
        .where(
            AvaliacaoPagina.avaliacao_id == avaliacao_id,
            AvaliacaoPagina.profundidade >= 0,
            (AvaliacaoPagina.texto.ilike(pat)) | (AvaliacaoPagina.titulo.ilike(pat)),
        )
        .limit(10)
    )).all()

    resultados = []
    for p in paginas:
        texto = (p.texto or "")
        idx = texto.lower().find(q)
        if idx == -1:
            snippet = (p.titulo or "")[:200]
        else:
            ini = max(0, idx - 80)
            fim = min(len(texto), idx + len(q) + 200)
            snippet = "…" + texto[ini:fim].replace("\n", " ") + "…"
        resultados.append({
            "url": p.url_final,
            "tipo": p.tipo,
            "titulo": p.titulo,
            "snippet": snippet,
        })

    return {
        "query": query,
        "total_encontrado": len(resultados),
        "resultados": resultados,
    }


# -----------------------------------------------------------------------
# tool: ler_pagina
# -----------------------------------------------------------------------
async def ler_pagina(
    session: AsyncSession, avaliacao_id: int, url: str
) -> dict:
    """Retorna o texto completo de uma página (truncado em 30k chars)."""
    pagina = await session.scalar(
        select(AvaliacaoPagina).where(
            AvaliacaoPagina.avaliacao_id == avaliacao_id,
            AvaliacaoPagina.url_final == url,
        )
    )
    if pagina is None:
        # tenta por url original também
        pagina = await session.scalar(
            select(AvaliacaoPagina).where(
                AvaliacaoPagina.avaliacao_id == avaliacao_id,
                AvaliacaoPagina.url == url,
            )
        )
    if pagina is None:
        return {"erro": f"página '{url}' não está no dossiê. Use buscar_no_dossie primeiro."}

    texto = (pagina.texto or "")[:30_000]
    return {
        "url": pagina.url_final,
        "tipo": pagina.tipo,
        "titulo": pagina.titulo,
        "tamanho_total": len(pagina.texto or ""),
        "texto": texto + ("\n\n[…truncado…]" if len(pagina.texto or "") > 30_000 else ""),
    }


# -----------------------------------------------------------------------
# tool: gravar_avaliacao
# -----------------------------------------------------------------------
async def gravar_avaliacao(
    session: AsyncSession,
    avaliacao_id: int,
    codigo: str,
    nota: float,
    justificativa: str,
    url_evidencia: str,
    o_que_falta: str,
    desconto_motivos: list[str] | None = None,
    confianca: float = 1.0,
    ia_modelo: str = "",
) -> dict:
    """Grava (upsert) o resultado da avaliação de um indicador."""
    item = await session.scalar(
        select(AvaliacaoItem).where(
            AvaliacaoItem.avaliacao_id == avaliacao_id,
            AvaliacaoItem.codigo == codigo,
        )
    )
    if item is None:
        return {"erro": f"indicador '{codigo}' não existe nesta avaliação"}

    item.nota = float(nota)
    item.justificativa = justificativa[:5000] if justificativa else None
    item.url_evidencia = (url_evidencia or "")[:1000]
    item.o_que_falta = (o_que_falta or "")[:3000]
    item.desconto_motivos = desconto_motivos or []
    item.confianca = float(confianca)
    item.ia_modelo = ia_modelo or None
    item.ia_gerado_em = now_bahia()
    await session.commit()

    return {
        "ok": True,
        "codigo": codigo,
        "nota_salva": float(nota),
        "confianca": float(confianca),
    }


# -----------------------------------------------------------------------
# despachante: recebe o que a IA pediu e roteia
# -----------------------------------------------------------------------
async def executar_tool(
    session: AsyncSession,
    avaliacao_id: int,
    nome: str,
    args: dict,
    ia_modelo: str = "",
) -> Any:
    if nome == "buscar_no_dossie":
        return await buscar_no_dossie(session, avaliacao_id, args.get("query", ""))
    if nome == "ler_pagina":
        return await ler_pagina(session, avaliacao_id, args.get("url", ""))
    if nome == "gravar_avaliacao":
        return await gravar_avaliacao(
            session, avaliacao_id,
            codigo=args.get("codigo", ""),
            nota=args.get("nota", 0),
            justificativa=args.get("justificativa", ""),
            url_evidencia=args.get("url_evidencia", ""),
            o_que_falta=args.get("o_que_falta", ""),
            desconto_motivos=args.get("desconto_motivos") or [],
            confianca=args.get("confianca", 1.0),
            ia_modelo=ia_modelo,
        )
    return {"erro": f"tool desconhecida: {nome}"}


async def resumir_dossie_magro(session: AsyncSession, avaliacao_id: int) -> str:
    """Versão enxuta: só URLs e títulos, sem texto.
    Reduz baseline de ~6k pra ~1k tokens. A IA usa as tools pra olhar o conteúdo."""
    paginas = (await session.scalars(
        select(AvaliacaoPagina)
        .where(AvaliacaoPagina.avaliacao_id == avaliacao_id, AvaliacaoPagina.profundidade >= 0)
        .order_by(AvaliacaoPagina.profundidade, AvaliacaoPagina.id)
    )).all()
    linhas = []
    for p in paginas:
        titulo = (p.titulo or "").strip()[:80]
        linhas.append(f"- [{p.tipo}] {p.url_final}  ({titulo})")
    return "\n".join(linhas) if linhas else "(dossiê vazio)"
