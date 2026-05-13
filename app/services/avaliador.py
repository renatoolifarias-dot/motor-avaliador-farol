"""Orquestrador de avaliação por IA — versão otimizada.

Otimizações sobre a versão anterior:
- 1 conversa POR INDICADOR (não por dimensão) → histórico não acumula
- Prompt caching (system + dossiê magro) → 90% desconto nos turns subsequentes
- Dossiê magro: só URLs+títulos no prompt; IA usa tools pra ler conteúdo

Custo estimado por cidade: ~US$ 0.20-0.40 (vs US$ 6+ na versão antiga).
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionFactory
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


MAX_ITER_POR_INDICADOR = 8   # tipicamente 3-4 chamadas (search → read → grava)


async def _log(session: AsyncSession, aid: int, nivel: str, msg: str) -> None:
    session.add(AvaliacaoLog(avaliacao_id=aid, nivel=nivel, mensagem=msg))
    await session.commit()


async def _set_status(session: AsyncSession, aid: int, status: str) -> None:
    av = await session.get(Avaliacao, aid)
    if av:
        av.status = status
        av.atualizado_em = datetime.utcnow()
        await session.commit()


def _to_dict(block) -> dict:
    if hasattr(block, "model_dump"):
        return block.model_dump()
    return dict(block)


async def avaliar_indicador(
    cliente: ClienteIA,
    avaliacao_id: int,
    cidade: str, uf: str, ciclo: int,
    grupo: dict, ind: dict,
    lista_paginas_magra: str,
    system_blocks: list,
) -> tuple[bool, int]:
    """Loop Tool Use para 1 indicador. Retorna (gravou?, num_chamadas)."""
    user_msg = gerar_user_message(cidade, uf, ciclo, grupo, ind, lista_paginas_magra)
    messages: list[dict] = [{"role": "user", "content": user_msg}]

    gravou = False
    n_chamadas_inicio = cliente.total_chamadas

    for it in range(MAX_ITER_POR_INDICADOR):
        resp = await cliente.chamar(
            system=system_blocks,            # list com cache_control
            messages=messages,
            tools=TOOLS_SCHEMA,
            max_tokens=2048,
        )

        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if not tool_uses:
            break

        messages.append({"role": "assistant", "content": [_to_dict(b) for b in resp.content]})

        results = []
        async with AsyncSessionFactory() as ses:
            for tu in tool_uses:
                try:
                    out = await executar_tool(
                        ses, avaliacao_id, tu.name, tu.input, ia_modelo=cliente.modelo
                    )
                    if tu.name == "gravar_avaliacao" and out.get("ok"):
                        gravou = True
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": str(out)[:3000],
                    })
                except Exception as e:
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": f"ERRO: {type(e).__name__}: {str(e)[:300]}",
                        "is_error": True,
                    })

        messages.append({"role": "user", "content": results})

        # Se já gravou e a IA não está pedindo mais nada, sai
        if gravou and resp.stop_reason == "end_turn":
            break

    return gravou, cliente.total_chamadas - n_chamadas_inicio


async def avaliar_avaliacao(avaliacao_id: int) -> dict:
    """Avaliação completa com TRIAGEM PRÉVIA.
    Para cada indicador: se nenhuma página do dossiê tem keywords da pergunta,
    grava nota 0 SEM chamar IA. Caso contrário, manda só as páginas relevantes."""
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
            f"dossiê com {len(paginas_norm)} páginas (triagem prévia ativa)"
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
    total_zero_sem_ia = 0

    for grupo in grupos:
        async with AsyncSessionFactory() as session:
            await _log(
                session, avaliacao_id, "info",
                f"→ Dim **{grupo['secao']}/{grupo['dim_nome']}** ({len(grupo['indicadores'])} ind)"
            )
        g_grupo, f_grupo, z_grupo = 0, 0, 0

        for ind in grupo["indicadores"]:
            keywords = extrair_keywords(ind.get("pergunta", ""))
            relevantes, score = paginas_relevantes(paginas_norm, keywords, top_n=6, min_score=2)

            # Triagem: se nada do dossiê tem relação, grava 0 sem IA
            if not relevantes:
                async with AsyncSessionFactory() as ses:
                    await gravar_avaliacao(
                        ses, avaliacao_id,
                        codigo=ind["codigo"],
                        nota=0.0,
                        justificativa=(
                            f"Triagem automática: nenhuma página do dossiê tem keywords "
                            f"desse indicador ({', '.join(keywords[:5]) or 'sem keywords extraídas'}). "
                            f"Indica que a Prefeitura não publica esse tipo de informação."
                        ),
                        url_evidencia=av.cidade,  # placeholder; revisor humano pode ajustar
                        o_que_falta=f"Publicar conteúdo relacionado a: {(ind.get('pergunta') or '').strip()[:200]}",
                        desconto_motivos=["sem evidência no dossiê (triagem)"],
                        confianca=0.6,
                        ia_modelo=f"triagem_sem_ia",
                    )
                z_grupo += 1
                total_zero_sem_ia += 1
                total_gravados += 1
                continue

            # Tem páginas relevantes — chama IA com lista SÓ delas
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
                f"  ✓ {grupo['dim_nome']}: {g_grupo} via IA + {z_grupo} zeros triagem / "
                f"{f_grupo} ✗ · {cliente.resumo_uso()}"
            )

    async with AsyncSessionFactory() as session:
        await _log(
            session, avaliacao_id, "info",
            f"Avaliação concluída: {total_gravados}/{total_gravados+total_falhas} pontuados "
            f"({total_zero_sem_ia} zeros via triagem sem IA) · {cliente.resumo_uso()}"
        )
        await _set_status(session, avaliacao_id, "aguardando_revisao")

    return {
        "gravados": total_gravados,
        "falhas": total_falhas,
        "zeros_triagem": total_zero_sem_ia,
        "chamadas": cliente.total_chamadas,
        "custo_usd": cliente.custo_acumulado_usd(),
    }
