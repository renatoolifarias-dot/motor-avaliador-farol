"""Orquestrador de avaliação por IA — sequencial com triagem afrouxada.

Mudanças v4:
- Triagem afrouxada (Sprint 6a): min_score=0, sempre chama IA
- Sequential (revertido 6b): paralelo quebrava cache e disparava rate limit
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionFactory
from app.services.tz import now_bahia
from app.models import Avaliacao, AvaliacaoLog, AvaliacaoItem
from app.services.ia_client import cliente_da_sessao, ClienteIA
from app.services.prompts import (
    carregar_indicadores, agrupar_por_dimensao,
    gerar_system, gerar_user_message, TOOLS_SCHEMA,
)
from app.services.tools import resumir_dossie_magro, executar_tool, gravar_avaliacao
from app.services.triagem import (
    extrair_keywords, carregar_paginas_normalizadas, paginas_relevantes,
)

MAX_ITER_POR_INDICADOR = 4


async def _log(session: AsyncSession, aid: int, nivel: str, msg: str) -> None:
    session.add(AvaliacaoLog(avaliacao_id=aid, nivel=nivel, mensagem=msg))
    await session.commit()


async def _set_status(session: AsyncSession, aid: int, status: str) -> None:
    av = await session.get(Avaliacao, aid)
    if av:
        av.status = status
        av.atualizado_em = now_bahia()
        await session.commit()


def _to_dict(block) -> dict:
    if hasattr(block, "model_dump"):
        return block.model_dump()
    return dict(block)


async def avaliar_indicador(
    cliente: ClienteIA, avaliacao_id: int,
    cidade: str, uf: str, ciclo: int,
    grupo: dict, ind: dict,
    lista_paginas_magra: str, system_blocks: list,
) -> tuple[bool, int]:
    user_msg = gerar_user_message(cidade, uf, ciclo, grupo, ind, lista_paginas_magra)
    messages: list[dict] = [{"role": "user", "content": user_msg}]
    gravou = False
    n_inicio = cliente.total_chamadas

    for it in range(MAX_ITER_POR_INDICADOR):
        if it == MAX_ITER_POR_INDICADOR - 1 and not gravou:
            messages.append({
                "role": "user",
                "content": (
                    f"ESTA É SUA ÚLTIMA CHANCE. Chame gravar_avaliacao AGORA "
                    f"para o indicador {ind['codigo']} com base no que já viu. "
                    f"Se não há evidência, use nota=0 com justificativa explicando."
                ),
            })

        resp = await cliente.chamar(
            system=system_blocks, messages=messages,
            tools=TOOLS_SCHEMA, max_tokens=2048,
        )

        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if not tool_uses:
            break

        messages.append({"role": "assistant", "content": [_to_dict(b) for b in resp.content]})

        results = []
        async with AsyncSessionFactory() as ses:
            for tu in tool_uses:
                try:
                    out = await executar_tool(ses, avaliacao_id, tu.name, tu.input, ia_modelo=cliente.modelo)
                    if tu.name == "gravar_avaliacao" and out.get("ok"):
                        gravou = True
                    results.append({"type": "tool_result", "tool_use_id": tu.id, "content": str(out)[:3000]})
                except Exception as e:
                    results.append({
                        "type": "tool_result", "tool_use_id": tu.id,
                        "content": f"ERRO: {type(e).__name__}: {str(e)[:300]}",
                        "is_error": True,
                    })

        messages.append({"role": "user", "content": results})

        if gravou and resp.stop_reason == "end_turn":
            break

    # Fallback obrigatório
    if not gravou:
        async with AsyncSessionFactory() as ses:
            await gravar_avaliacao(
                ses, avaliacao_id,
                codigo=ind["codigo"], nota=0.0,
                justificativa=f"IA não convergiu após {MAX_ITER_POR_INDICADOR} chamadas — gravação automática como 0.",
                url_evidencia="(IA não retornou)",
                o_que_falta=f"Avaliar manualmente: {(ind.get('pergunta') or '').strip()[:200]}",
                desconto_motivos=["IA não convergiu (max_iter)"],
                confianca=0.2,
                ia_modelo=f"fallback_zero_{cliente.modelo}",
            )
        gravou = True

    return gravou, cliente.total_chamadas - n_inicio


async def avaliar_avaliacao(avaliacao_id: int) -> dict:
    """Avaliação sequencial dimensão por dimensão (sem multi-agent paralelo).
    Mantém triagem afrouxada (min_score=0) — sempre chama IA."""
    async with AsyncSessionFactory() as session:
        av = await session.get(Avaliacao, avaliacao_id)
        if not av:
            return {"erro": "avaliação não existe"}

        cliente = await cliente_da_sessao(session)
        paginas_norm = await carregar_paginas_normalizadas(session, avaliacao_id)

        await _set_status(session, avaliacao_id, "avaliando_ia")
        await _log(
            session, avaliacao_id, "info",
            f"Início avaliação · {cliente.modelo} · "
            f"{len(paginas_norm)} páginas no dossiê · triagem afrouxada"
        )

    system_blocks = [{
        "type": "text",
        "text": gerar_system(av.cidade, av.uf),
        "cache_control": {"type": "ephemeral"},
    }]

    indicadores = carregar_indicadores()
    grupos = agrupar_por_dimensao(indicadores)

    total_gravados = 0
    total_falhas = 0

    for grupo in grupos:
        async with AsyncSessionFactory() as session:
            await _log(
                session, avaliacao_id, "info",
                f"→ Dim **{grupo['secao']}/{grupo['dim_nome']}** ({len(grupo['indicadores'])} ind)"
            )
        g_grupo, f_grupo = 0, 0
        for ind in grupo["indicadores"]:
            keywords = extrair_keywords(ind.get("pergunta", ""))
            relevantes, _ = paginas_relevantes(paginas_norm, keywords, top_n=8, min_score=0)
            if not relevantes:
                relevantes = paginas_norm[:6]
            lista_relevante = "\n".join(
                f"- [{p['tipo']}] {p['url']}  ({(p['titulo'] or '')[:80]})"
                for p in relevantes
            )
            try:
                gravou, _ = await avaliar_indicador(
                    cliente, avaliacao_id, av.cidade, av.uf, av.ciclo,
                    grupo, ind, lista_relevante, system_blocks,
                )
                if gravou:
                    g_grupo += 1
                    total_gravados += 1
                else:
                    f_grupo += 1
                    total_falhas += 1
            except Exception as e:
                f_grupo += 1
                total_falhas += 1
                async with AsyncSessionFactory() as session:
                    await _log(
                        session, avaliacao_id, "warn",
                        f"falha em {ind['codigo']}: {type(e).__name__}: {str(e)[:200]}"
                    )
        async with AsyncSessionFactory() as session:
            await _log(
                session, avaliacao_id, "info",
                f"  ✓ {grupo['dim_nome']}: {g_grupo} ✓ / {f_grupo} ✗ · {cliente.resumo_uso()}"
            )

    async with AsyncSessionFactory() as session:
        await _log(
            session, avaliacao_id, "info",
            f"Avaliação concluída: {total_gravados}/{total_gravados+total_falhas} pontuados · "
            f"{cliente.resumo_uso()}"
        )
        await _set_status(session, avaliacao_id, "aguardando_revisao")

    return {
        "gravados": total_gravados,
        "falhas": total_falhas,
        "chamadas": cliente.total_chamadas,
        "custo_usd": cliente.custo_acumulado_usd(),
    }
