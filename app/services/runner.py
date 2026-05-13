"""Orquestrador: descobre portais → crawleia → grava no banco.

Roda como Background Task do FastAPI (suficiente pra cidades pequenas).
Depois pode virar Celery task se quiser paralelismo de várias cidades.
"""
from __future__ import annotations
from datetime import datetime
from app.services.tz import now_bahia
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import AsyncSessionFactory
from app.models import Avaliacao, AvaliacaoPagina, AvaliacaoLog
from app.services.descobridor import descobrir
from app.services.crawler import crawl


async def _log(session: AsyncSession, aid: int, nivel: str, msg: str) -> None:
    session.add(AvaliacaoLog(avaliacao_id=aid, nivel=nivel, mensagem=msg))
    await session.commit()


async def _set_status(session: AsyncSession, aid: int, status: str) -> None:
    av = await session.get(Avaliacao, aid)
    if av:
        av.status = status
        av.atualizado_em = now_bahia()
        await session.commit()


async def descobrir_portais(avaliacao_id: int) -> dict:
    """Etapa 1: descobre portais oficiais de uma avaliação.
    Retorna stats. Os portais ficam guardados em AvaliacaoPagina
    com profundidade=-1 (marcador de 'seed')."""
    async with AsyncSessionFactory() as session:
        av = await session.get(Avaliacao, avaliacao_id)
        if not av:
            return {"erro": "avaliação não existe"}

        await _set_status(session, avaliacao_id, "descobrindo_portais")
        await _log(session, avaliacao_id, "info", f"Descobrindo portais de {av.cidade}/{av.uf}")

        portais = await descobrir(av.cidade, av.uf)

        # apaga seeds antigas (re-descoberta)
        await session.execute(
            AvaliacaoPagina.__table__.delete().where(
                AvaliacaoPagina.avaliacao_id == avaliacao_id,
                AvaliacaoPagina.profundidade == -1,
            )
        )
        await session.commit()

        for p in portais:
            session.add(AvaliacaoPagina(
                avaliacao_id=avaliacao_id,
                url=p.url,
                url_final=p.url_final,
                status_code=p.status,
                tipo="seed",
                titulo=p.titulo or ("[CF protegido]" if p.protegido_cloudflare else None),
                texto=None,
                profundidade=-1,
            ))
        await session.commit()

        await _log(
            session, avaliacao_id, "info",
            f"{len(portais)} portais descobertos "
            f"({sum(1 for p in portais if p.protegido_cloudflare)} protegidos por Cloudflare)"
        )
        return {
            "portais_encontrados": len(portais),
            "protegidos_cloudflare": sum(1 for p in portais if p.protegido_cloudflare),
            "lista": [
                {
                    "url": p.url_final,
                    "status": p.status,
                    "titulo": p.titulo,
                    "protegido": p.protegido_cloudflare,
                }
                for p in portais
            ],
        }


async def crawlear_avaliacao(
    avaliacao_id: int,
    max_paginas: int = 50,
    profundidade_max: int = 2,
) -> dict:
    """Etapa 2: usa as seeds (portais descobertos) e crawleia
    com Playwright. Salva tudo em avaliacao_paginas (profundidade >= 0)."""
    async with AsyncSessionFactory() as session:
        av = await session.get(Avaliacao, avaliacao_id)
        if not av:
            return {"erro": "avaliação não existe"}

        seeds = (await session.scalars(
            select(AvaliacaoPagina).where(
                AvaliacaoPagina.avaliacao_id == avaliacao_id,
                AvaliacaoPagina.profundidade == -1,
            )
        )).all()
        if not seeds:
            await _log(session, avaliacao_id, "warn", "Nenhum portal descoberto — rode 'Descobrir portais' antes")
            return {"erro": "sem seeds"}

        await _set_status(session, avaliacao_id, "crawleando")
        urls_seed = [s.url_final for s in seeds]
        await _log(session, avaliacao_id, "info", f"Iniciando crawl de {len(urls_seed)} portais ({max_paginas} max, profundidade {profundidade_max})")

    # crawl em si (fora da session async pra liberar conn)
    paginas = await crawl(urls_seed, max_paginas=max_paginas, profundidade_max=profundidade_max)

    # grava
    async with AsyncSessionFactory() as session:
        # limpa páginas antigas (não-seeds) dessa avaliação
        await session.execute(
            AvaliacaoPagina.__table__.delete().where(
                AvaliacaoPagina.avaliacao_id == avaliacao_id,
                AvaliacaoPagina.profundidade >= 0,
            )
        )
        for p in paginas:
            session.add(AvaliacaoPagina(
                avaliacao_id=avaliacao_id,
                url=p.url,
                url_final=p.url_final,
                status_code=p.status,
                tipo=p.tipo,
                titulo=p.titulo,
                texto=p.texto,
                profundidade=p.profundidade,
            ))
        await session.commit()

        await _log(
            session, avaliacao_id, "info",
            f"Crawl concluído: {len(paginas)} páginas capturadas "
            f"({sum(1 for p in paginas if p.tipo=='pdf')} PDFs, "
            f"~{sum(len(p.texto) for p in paginas)/1024:.1f} KB de texto)"
        )
        await _set_status(session, avaliacao_id, "crawleado")

    return {
        "paginas_capturadas": len(paginas),
        "pdfs": sum(1 for p in paginas if p.tipo == "pdf"),
        "kb_texto": round(sum(len(p.texto) for p in paginas) / 1024, 1),
    }
