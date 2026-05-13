"""Triagem prévia: para cada indicador, identifica páginas relevantes do dossiê
ANTES de chamar a IA. Se nenhuma página tem keywords do indicador, gravamos
nota 0 sem gastar API.

Estratégia:
1. Extrai keywords da `pergunta` do indicador (substantivos, termos técnicos).
2. Para cada página do dossiê (título+texto), conta matches dessas keywords.
3. Retorna lista ordenada por score; vazia = "nada relevante".
"""
from __future__ import annotations
import re
import unicodedata
from collections import Counter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import AvaliacaoPagina


# Stopwords ptBR mínimo + termos genéricos que poluem
STOPWORDS = {
    "a","o","as","os","de","do","da","dos","das","e","em","no","na","nos","nas",
    "para","com","por","pelo","pela","um","uma","uns","umas","que","ou","se",
    "ao","aos","à","às","mais","menos","entre","sobre","sob","ser","estar",
    "ter","há","foi","é","são","seja","sejam","como","quando","onde","qual",
    "quais","seu","sua","seus","suas","esse","essa","esses","essas","este",
    "esta","estes","estas","isso","isto","aquele","aquela","aquilo","seu",
    "sua","já","ainda","apenas","também","muito","pouco","todo","toda",
    "todos","todas","cada","podem","pode","deve","devem","feito","feita",
    "sido","tem","têm","após","durante","exemplo","forma","etc","ex",
    "url","site","portal","página","paginas","link","outro","outros","outra",
    "outras","entre","mesmo","mesma","tais","tal","aquela","aqueles","aquelas",
    "informações","dados","disponibiliza","disponibilizar","publica","publicar",
}


def _normalizar(s: str) -> str:
    """Remove acentos, baixa caixa, retorna só letras/dígitos/espaços."""
    if not s: return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s)


def extrair_keywords(pergunta: str, min_len: int = 4, max_kw: int = 12) -> list[str]:
    """Extrai termos-chave da pergunta do indicador.
    Pega palavras com 4+ chars que não estão em stopwords. Dedup, limita."""
    txt = _normalizar(pergunta)
    if not txt:
        return []
    # bigrams (termos compostos) e unigrams
    palavras = [p for p in txt.split() if len(p) >= min_len and p not in STOPWORDS]
    bigrams = []
    for i in range(len(palavras)-1):
        bigrams.append(palavras[i] + " " + palavras[i+1])
    # priorizar bigrams (mais discriminativos), depois unigrams únicos
    vistos = set()
    out = []
    for kw in bigrams + palavras:
        if kw in vistos:
            continue
        vistos.add(kw)
        out.append(kw)
        if len(out) >= max_kw:
            break
    return out


async def carregar_paginas_normalizadas(
    session: AsyncSession, avaliacao_id: int
) -> list[dict]:
    """Retorna lista [{url, titulo, texto_norm}] das páginas crawleadas."""
    paginas = (await session.scalars(
        select(AvaliacaoPagina)
        .where(AvaliacaoPagina.avaliacao_id == avaliacao_id, AvaliacaoPagina.profundidade >= 0)
    )).all()
    out = []
    for p in paginas:
        # cache do normalizado pra não refazer 122 vezes
        out.append({
            "url": p.url_final,
            "tipo": p.tipo,
            "titulo": p.titulo or "",
            "texto": p.texto or "",
            "texto_norm": _normalizar((p.titulo or "") + " " + (p.texto or "")),
        })
    return out


def paginas_relevantes(
    paginas: list[dict], keywords: list[str], top_n: int = 6, min_score: int = 2
) -> tuple[list[dict], int]:
    """Retorna até top_n páginas com maior score (count de keywords matched).
    Score mínimo configurável. Retorna (lista_relevantes, score_total)."""
    if not keywords:
        return [], 0

    scored = []
    score_total = 0
    for p in paginas:
        cnt = 0
        for kw in keywords:
            if kw in p["texto_norm"]:
                cnt += 1
        if cnt >= min_score:
            scored.append((cnt, p))
            score_total += cnt

    scored.sort(key=lambda t: t[0], reverse=True)
    relevantes = [p for _, p in scored[:top_n]]
    return relevantes, score_total
