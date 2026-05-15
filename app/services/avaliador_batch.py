"""Avaliador via Anthropic Message Batches API.

Vantagens vs avaliador.py (sequencial):
- 50% mais barato (50% off no input + 50% off no output)
- Sem rate limit (Anthropic processa quando há capacidade)
- Pode submeter os 122 indicadores como UM batch de 122 requests
- Processa em background, retornamos quando estiver pronto (até 24h)

Limitações:
- Cada request do batch é INDEPENDENTE (sem multi-turn Tool Use)
- Solução: passar o dossiê inteiro no prompt + pedir resposta JSON estruturada
- Sem buscar_no_dossie/ler_pagina — IA decide tudo com o contexto que tem
"""
from __future__ import annotations
import asyncio
import json
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionFactory
from app.services.tz import now_bahia
from app.models import Avaliacao, AvaliacaoLog, AvaliacaoItem, Indicador, AvaliacaoPagina
from app.services.ia_client import cliente_da_sessao
from app.services.prompts import gerar_system, carregar_indicadores, agrupar_por_dimensao


SYSTEM_BATCH = """Você é avaliador ITGP (Transparência Internacional Brasil, 3ª ed 2025).
Avalia 1 indicador municipal por vez com base no dossiê fornecido.

REGRAS (não-negociáveis):
1. INDÍCIO PARCIAL = 0,5 (não zero). Link/menu/rubrica explícita da info → 0,5.
2. Lei/decreto criando órgão = 0,5 a 0,75.
3. Portal SAI/IBDM/IMAP com filtros funcionais = 0,75.
4. Página VERIFICADAMENTE vazia = 0,25 (só com evidência ativa, não suspeita).
5. Defasagem >12 meses (rel. 2026-01) = nota / 2. >24m = 0.
6. URL_EVIDENCIA específica obrigatória para nota ≥ 0,5.
7. Granularidade: 0, 0,25, 0,5, 0,75, 1,0.

RETORNE SÓ JSON, sem prefixo nem sufixo. Schema:
{
  "nota": 0.5,
  "justificativa": "2-4 frases explicando",
  "url_evidencia": "https://...",
  "o_que_falta": "recomendação acionável",
  "desconto_motivos": ["motivo1"],
  "confianca": 0.85
}
"""


def montar_dossie_texto(paginas: list, max_chars: int = 40000) -> str:
    """Concatena texto das páginas do dossiê. Cap em 40k chars (~10k tokens)."""
    partes = []
    total = 0
    for p in paginas:
        titulo = (p.get("titulo") or "").strip()
        texto = (p.get("texto") or "").strip().replace("\n", " ")[:1500]
        bloco = f"## {titulo} ({p['url']})\n{texto}\n"
        if total + len(bloco) > max_chars:
            break
        partes.append(bloco)
        total += len(bloco)
    return "\n".join(partes)


def gerar_request_indicador(
    indicador: dict, cidade: str, uf: str, ciclo: int, dossie_texto: str
) -> dict:
    """Cria 1 request pra um indicador no formato Batch da Anthropic."""
    opcs = "; ".join(
        f"{o['nota']}={o['descricao']}" for o in indicador.get("opcoes_resposta", [])
    )
    user_msg = f"""CIDADE: {cidade}/{uf} · CICLO: {ciclo}
DIMENSÃO: {indicador.get('dim_nome')}

INDICADOR **{indicador['codigo']}** (peso {indicador['peso']}, max {indicador['nota_max']}):
{indicador.get('pergunta', '').strip()}

Opções: {opcs}

DOSSIÊ DA CIDADE:
{dossie_texto}

Responda APENAS com JSON (schema no system prompt)."""

    return {
        "custom_id": indicador["codigo"],  # nosso ID — voltará na response
        "params": {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 1024,
            "system": SYSTEM_BATCH,
            "messages": [{"role": "user", "content": user_msg}],
        },
    }


async def submeter_batch(avaliacao_id: int) -> dict:
    """Cria batch de 122 requests, submete, retorna batch_id pra polling."""
    async with AsyncSessionFactory() as session:
        av = await session.get(Avaliacao, avaliacao_id)
        if not av:
            return {"erro": "avaliação não existe"}

        cliente = await cliente_da_sessao(session)
        paginas = (await session.scalars(
            select(AvaliacaoPagina).where(
                AvaliacaoPagina.avaliacao_id == avaliacao_id,
                AvaliacaoPagina.profundidade >= 0,
            )
        )).all()
        paginas_dict = [
            {"url": p.url_final, "titulo": p.titulo, "texto": p.texto or "", "tipo": p.tipo}
            for p in paginas
        ]

    # Monta dossiê textual UM VEZ (mesmo pra todos os 122 indicadores)
    dossie_texto = montar_dossie_texto(paginas_dict, max_chars=40000)

    indicadores = carregar_indicadores()
    requests = [
        gerar_request_indicador(ind, av.cidade, av.uf, av.ciclo, dossie_texto)
        for ind in indicadores
    ]

    # Submete via SDK Anthropic (message_batches.create)
    batch = await cliente.client.messages.batches.create(requests=requests)
    batch_id = batch.id

    async with AsyncSessionFactory() as session:
        await _log(
            session, avaliacao_id, "info",
            f"Batch submetido: {batch_id} ({len(requests)} requests, modelo {cliente.modelo})"
        )
        av = await session.get(Avaliacao, avaliacao_id)
        av.status = "avaliando_ia"
        await session.commit()

    return {"batch_id": batch_id, "requests": len(requests)}


async def coletar_resultado_batch(avaliacao_id: int, batch_id: str) -> dict:
    """Polling: aguarda batch terminar e grava itens no banco."""
    async with AsyncSessionFactory() as session:
        cliente = await cliente_da_sessao(session)

    # Poll status
    while True:
        b = await cliente.client.messages.batches.retrieve(batch_id)
        status = b.processing_status
        if status == "ended":
            break
        await asyncio.sleep(30)

    # Lê resultados (streaming JSONL)
    resultados = []
    async for entry in await cliente.client.messages.batches.results(batch_id):
        if entry.result.type == "succeeded":
            try:
                content = entry.result.message.content[0].text
                # parse JSON da IA
                data = json.loads(content.strip())
                data["codigo"] = entry.custom_id
                resultados.append(data)
            except Exception as e:
                pass

    # Grava no banco
    now = now_bahia()
    async with AsyncSessionFactory() as session:
        for r in resultados:
            it = await session.scalar(
                select(AvaliacaoItem).where(
                    AvaliacaoItem.avaliacao_id == avaliacao_id,
                    AvaliacaoItem.codigo == r["codigo"],
                )
            )
            if not it:
                continue
            it.nota = float(r.get("nota", 0))
            it.justificativa = (r.get("justificativa") or "")[:5000]
            it.url_evidencia = (r.get("url_evidencia") or "")[:1000]
            it.o_que_falta = (r.get("o_que_falta") or "")[:3000]
            it.desconto_motivos = r.get("desconto_motivos") or []
            it.confianca = float(r.get("confianca", 0.7))
            it.ia_modelo = "haiku-batch-api"
            it.ia_gerado_em = now
        await session.commit()
        # Recalcula nota final
        from sqlalchemy import func
        r = await session.execute(
            select(func.sum(AvaliacaoItem.nota * Indicador.peso), func.sum(Indicador.peso))
            .select_from(Indicador).join(
                AvaliacaoItem,
                (AvaliacaoItem.codigo == Indicador.codigo)
                & (AvaliacaoItem.avaliacao_id == avaliacao_id),
            )
        )
        soma, peso = r.first()
        nota = round(float(soma or 0) * 100 / float(peso or 1), 2)
        classif = "Alta" if nota >= 75 else "Media" if nota >= 50 else "Baixa" if nota >= 25 else "Minima"
        av = await session.get(Avaliacao, avaliacao_id)
        av.nota_geral = nota
        av.classificacao = classif
        av.status = "aguardando_revisao"
        await session.commit()
        await _log(session, avaliacao_id, "info",
                   f"Batch concluído: {len(resultados)}/122 · nota={nota} · {classif}")

    return {"gravados": len(resultados), "nota": nota, "classificacao": classif}


async def _log(session, aid, nivel, msg):
    session.add(AvaliacaoLog(avaliacao_id=aid, nivel=nivel, mensagem=msg))
    await session.commit()


async def avaliar_via_batch(avaliacao_id: int) -> dict:
    """Pipeline completo: submete batch + aguarda + grava."""
    res = await submeter_batch(avaliacao_id)
    if "erro" in res:
        return res
    return await coletar_resultado_batch(avaliacao_id, res["batch_id"])
