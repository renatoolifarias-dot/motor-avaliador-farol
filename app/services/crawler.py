"""Crawler de portais municipais com Playwright (Chromium real).

Por que Chromium em vez de httpx:
- Cloudflare/Sucuri bloqueia bots (403 / "Just a moment...")
- Portais BR modernos são SPAs (Vue/React) que precisam JS executado
- Cookies + redirects de proteção exigem browser stateful

Estratégia:
- BFS controlado: começa de uma URL semente, navega até `profundidade` níveis
- Coleta texto extraído + links pra outras páginas do mesmo domínio
- PDFs: baixa e extrai texto via pypdf (sem renderizar)
- Salva tudo em AvaliacaoPagina (banco)
- Idempotente: se URL já está no banco, reusa (a menos que force=True)
"""
from __future__ import annotations
import asyncio
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin, urlparse
import structlog

logger = structlog.get_logger()


@dataclass
class PaginaCapturada:
    url: str
    url_final: str
    status: int
    tipo: str          # "html" | "pdf"
    titulo: Optional[str]
    texto: str
    links_internos: list[str]   # URLs do mesmo domínio descobertas
    profundidade: int


def _mesmo_dominio(a: str, b: str) -> bool:
    da = urlparse(a).netloc.lower().lstrip("www.")
    db = urlparse(b).netloc.lower().lstrip("www.")
    return da == db


def _eh_html(url: str) -> bool:
    u = url.lower().split("?")[0].split("#")[0]
    if u.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar")):
        return False
    return True


def _eh_pdf(url: str) -> bool:
    return url.lower().split("?")[0].endswith(".pdf")


async def _capturar_html(page, url: str, profundidade: int) -> Optional[PaginaCapturada]:
    """Navega até a URL e extrai texto + links."""
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        logger.warning("playwright_goto_error", url=url, err=str(e)[:120])
        return None
    if resp is None:
        return None

    # Aguarda um pouco pro Cloudflare passar (cookies de challenge)
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass

    titulo = await page.title()
    # Texto: pega o innerText do body (limpa, sem HTML)
    try:
        texto = await page.evaluate("() => document.body.innerText")
    except Exception:
        texto = ""
    texto = (texto or "").strip()[:200_000]   # cap 200KB por página

    # Coleta links absolutos do mesmo domínio
    try:
        hrefs = await page.evaluate(
            "() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href)"
        )
    except Exception:
        hrefs = []
    links_internos = []
    for h in hrefs or []:
        try:
            absu = urljoin(url, h.split("#")[0]).strip()
            if absu and _mesmo_dominio(url, absu) and absu not in links_internos:
                links_internos.append(absu)
        except Exception:
            continue

    return PaginaCapturada(
        url=url,
        url_final=page.url,
        status=resp.status,
        tipo="html",
        titulo=(titulo or "").strip()[:500] or None,
        texto=texto,
        links_internos=links_internos[:200],
        profundidade=profundidade,
    )


async def _capturar_pdf(context, url: str, profundidade: int) -> Optional[PaginaCapturada]:
    """Baixa PDF e extrai texto via pypdf."""
    try:
        # browser context tem cookies do Cloudflare (vc preencheu navegando antes)
        resp = await context.request.get(url, timeout=30000)
    except Exception as e:
        logger.warning("pdf_fetch_error", url=url, err=str(e)[:120])
        return None
    if resp.status >= 400:
        return None

    data = await resp.body()
    if not data:
        return None

    # Extrai texto do PDF
    try:
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        textos = []
        for pg in reader.pages[:50]:  # cap 50 páginas
            try:
                t = pg.extract_text() or ""
                if t.strip():
                    textos.append(t)
            except Exception:
                continue
        texto = "\n\n".join(textos)[:200_000]
    except Exception as e:
        logger.warning("pdf_parse_error", url=url, err=str(e)[:120])
        texto = ""

    return PaginaCapturada(
        url=url,
        url_final=str(resp.url),
        status=resp.status,
        tipo="pdf",
        titulo=url.split("/")[-1][:200],
        texto=texto,
        links_internos=[],
        profundidade=profundidade,
    )


# Filtros pra não cair em armadilhas (calendários infinitos, etc.)
LINKS_BLOQUEADOS_RE = re.compile(
    r"/(login|sair|logout|ajax|api/|wp-admin|/calendar|/cal/|/feed|/rss|"
    r"compartilhar=|share=|print=|imprimir)",
    re.IGNORECASE,
)


async def crawl(
    urls_seed: list[str],
    max_paginas: int = 50,
    profundidade_max: int = 2,
) -> list[PaginaCapturada]:
    """Crawler BFS. Recebe URLs sementes (do descobridor), navega
    até profundidade_max níveis, captura até max_paginas no total."""
    from playwright.async_api import async_playwright

    capturadas: list[PaginaCapturada] = []
    visitados: set[str] = set()
    fila: list[tuple[str, int]] = [(u, 0) for u in urls_seed]

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 900},
            locale="pt-BR",
        )
        page = await context.new_page()

        while fila and len(capturadas) < max_paginas:
            url, prof = fila.pop(0)
            url_norm = url.rstrip("/").lower()
            if url_norm in visitados:
                continue
            visitados.add(url_norm)

            if LINKS_BLOQUEADOS_RE.search(url):
                continue

            if _eh_pdf(url):
                p = await _capturar_pdf(context, url, prof)
            elif _eh_html(url):
                p = await _capturar_html(page, url, prof)
            else:
                continue

            if p is None:
                continue
            capturadas.append(p)
            logger.info("pagina_capturada", url=p.url, status=p.status, tipo=p.tipo, prof=prof)

            # Expande fila com links internos
            if prof < profundidade_max and p.tipo == "html":
                for link in p.links_internos:
                    if link.rstrip("/").lower() not in visitados:
                        fila.append((link, prof + 1))

        await browser.close()

    return capturadas


# CLI pra testar
if __name__ == "__main__":
    import sys, json
    seeds = sys.argv[1:]
    if not seeds:
        print("uso: python crawler.py <url1> [url2 ...]")
        sys.exit(1)
    res = asyncio.run(crawl(seeds, max_paginas=10, profundidade_max=1))
    for p in res:
        print(f"\n--- [{p.tipo}] {p.url_final}  (status={p.status}, depth={p.profundidade})")
        print(f"Título: {p.titulo}")
        print(f"Texto ({len(p.texto)} chars): {p.texto[:300]!r}")
        print(f"Links internos: {len(p.links_internos)}")
