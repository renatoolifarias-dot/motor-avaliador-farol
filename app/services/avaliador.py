"""Orquestrador de avaliação por IA.

Para cada dimensão (12 grupos = 6 Geral + 4 Saúde + 2 Clima),
roda um loop de Tool Use com Claude:

  enquanto não terminou (stop_reason != "end_turn"):
    response = claude.chamar(messages, tools=TOOLS)
    se vier tool_use:
        executa a tool no DB
        appenda tool_result na conversa
        continua
    senão break

Limites de segurança:
- max_iteracoes por dimensão: 60 (média ~3 tool_calls por indicador × 11 ind)
- max_tokens por chamada: 4096
- timeout total por avaliação: deve ser configurado pelo caller (BackgroundTask sem timeout)
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionFactory
from app.models import Avaliacao, AvaliacaoLog
from app.services.ia_client import cliente_da_sessao, ClienteIA
from app.services.prompts import (
    carregar_indicadores, agrupar_por_dimensao,
    gerar_system, gerar_user_message, TOOLS_SCHEMA,
)
from app.services.tools import resumir_dossie, executar_tool


MAX_ITER_POR_DIMENSAO = 60


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
    """Converte block do SDK Anthropic em dict serializável (pra messages)."""
    if hasattr(block, "model_dump"):
        return block.model_dump()
    return dict(block)


async def avaliar_dimensao(
    cliente: ClienteIA,
    avaliacao_id: int,
    cidade: str,
    uf: str,
    ciclo: int,
    grupo: dict,
    resumo_dossie: str,
) -> tuple[int, int]:
    """Roda Tool Use loop para 1 dimensão. Retorna (gravados, falhas)."""
    system = gerar_system(cidade, uf)
    user_msg = gerar_user_message(cidade, uf, ciclo, grupo, resumo_dossie)
    messages: list[dict] = [{"role": "user", "content": user_msg}]

    gravados, falhas = 0, 0

    for it in range(MAX_ITER_POR_DIMENSAO):
        resp = await cliente.chamar(
            system=system, messages=messages, tools=TOOLS_SCHEMA, max_tokens=4096
        )

        # Se ele só respondeu texto sem tool_use → fim do trabalho
        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if not tool_uses:
            break

        # Adiciona assistant message (com tool_use blocks) à conversa
        messages.append({"role": "assistant", "content": [_to_dict(b) for b in resp.content]})

        # Executa todos os tool_uses (paralelo seria possível mas sequencial é mais simples)
        results = []
        async with AsyncSessionFactory() as ses:
            for tu in tool_uses:
                try:
                    out = await executar_tool(
                        ses, avaliacao_id, tu.name, tu.input, ia_modelo=cliente.modelo
                    )
                    if tu.name == "gravar_avaliacao":
                        if out.get("ok"):
                            gravados += 1
                        else:
                            falhas += 1
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": str(out)[:4000],
                    })
                except Exception as e:
                    falhas += 1
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": f"ERRO: {type(e).__name__}: {str(e)[:300]}",
                        "is_error": True,
                    })

        messages.append({"role": "user", "content": results})

        if resp.stop_reason == "end_turn":
            break

    return gravados, falhas


async def avaliar_avaliacao(avaliacao_id: int) -> dict:
    """Avaliação completa: percorre as 12 dimensões."""
    async with AsyncSessionFactory() as session:
        av = await session.get(Avaliacao, avaliacao_id)
        if not av:
            return {"erro": "avaliação não existe"}

        cliente = await cliente_da_sessao(session)
        resumo_dossie = await resumir_dossie(session, avaliacao_id)

        await _set_status(session, avaliacao_id, "avaliando_ia")
        await _log(session, avaliacao_id, "info",
                   f"Início avaliação IA · modelo {cliente.modelo}")

    indicadores = carregar_indicadores()
    grupos = agrupar_por_dimensao(indicadores)

    total_gravados = 0
    total_falhas = 0

    for grupo in grupos:
        async with AsyncSessionFactory() as session:
            await _log(
                session, avaliacao_id, "info",
                f"→ Dimensão **{grupo['secao']}/{grupo['dim_nome']}** ({len(grupo['indicadores'])} ind)"
            )

        try:
            g, f = await avaliar_dimensao(
                cliente, avaliacao_id, av.cidade, av.uf, av.ciclo,
                grupo, resumo_dossie,
            )
            total_gravados += g
            total_falhas += f
            async with AsyncSessionFactory() as session:
                await _log(
                    session, avaliacao_id, "info",
                    f"  ✓ {grupo['dim_nome']}: {g} gravados / {f} falhas · "
                    f"acumulado uso: {cliente.resumo_uso()}"
                )
        except Exception as e:
            async with AsyncSessionFactory() as session:
                await _log(
                    session, avaliacao_id, "error",
                    f"  ✗ erro em {grupo['dim_nome']}: {type(e).__name__}: {str(e)[:300]}"
                )

    async with AsyncSessionFactory() as session:
        await _log(
            session, avaliacao_id, "info",
            f"Avaliação IA concluída: {total_gravados} indicadores pontuados · "
            f"custo total: {cliente.resumo_uso()}"
        )
        await _set_status(session, avaliacao_id, "aguardando_revisao")

    return {
        "gravados": total_gravados,
        "falhas": total_falhas,
        "chamadas": cliente.total_chamadas,
        "custo_usd": cliente.custo_acumulado_usd(),
    }
