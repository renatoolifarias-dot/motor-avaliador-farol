"""Descobridor de portais oficiais municipais.

Dado cidade+UF, gera URLs candidatas baseadas em padrões reais
(prefeitura.X.uf.gov.br, transparencia.X.uf.gov.br, X.uf.gov.br, etc.),
valida via HTTP, e retorna apenas as que respondem com 2xx/3xx
e que aparentam ser portais municipais (não 404 + sem CMS instalado).

Não usa browser real — só HTTP HEAD/GET — pra ser rápido. O Crawler
profundo (Playwright) vem depois.
"""
import re
import asyncio
from dataclasses import dataclass
from typing import Optional
import httpx


def _slug(s: str) -> str:
    """Remove acentos e normaliza pra subdomínio."""
    de = "áàãâäåéèêëíìîïóòõôöúùûüçñÁÀÃÂÄÅÉÈÊËÍÌÎÏÓÒÕÔÖÚÙÛÜÇÑ"
    para = "aaaaaaeeeeiiiiooooouuuucnAAAAAAEEEEIIIIOOOOOUUUUCN"
    s = s.translate(str.maketrans(de, para)).lower()
    return re.sub(r"[^a-z0-9]+", "", s)


# Padrões reais observados em municípios brasileiros (ordem = prioridade)
PADROES = [
    # gov.br (mais comum em BA, SE, RN, PE, etc.)
    "https://{slug}.{uf}.gov.br",
    "https://www.{slug}.{uf}.gov.br",
    "https://prefeitura.{slug}.{uf}.gov.br",
    "https://transparencia.{slug}.{uf}.gov.br",
    "https://portal.{slug}.{uf}.gov.br",
    "https://www.prefeituradel{slug}.{uf}.gov.br",   # "del" prefix raro
    # variações pelas vezes em .com.br
    "https://www.{slug}.{uf}.gov.br/transparencia",
    "https://www.{slug}.{uf}.gov.br/portal-da-transparencia",
    # PMs com CMS WP/comercial
    "https://www.prefeituradel{slug}.com.br",
    "https://www.pm{slug}.{uf}.gov.br",
]

# Sub-páginas que costumam ter dados de transparência
SUBPAGINAS_TRANSP = [
    "/transparencia",
    "/portal-da-transparencia",
    "/portal-transparencia",
    "/transparencia-municipal",
    "/lai",
    "/e-sic",
    "/ouvidoria",
    "/licitacoes",
    "/contratos",
    "/concursos",
    "/diario-oficial",
]


@dataclass
class Portal:
    url: str
    url_final: str
    status: int
    titulo: Optional[str]
    eh_oficial: bool          # heurística: gov.br/com.br municipal
    tem_transparencia: bool
    protegido_cloudflare: bool  # 403/429/503 → DNS resolve mas precisa Playwright


# Heurísticas para detectar prefeitura
PADROES_TITULO_OK = re.compile(
    r"(prefeitura|portal\s+(da\s+)?transpar[êe]ncia|munic[ií]pio|c[âa]mara\s+municipal)",
    re.IGNORECASE,
)


async def _check(client: httpx.AsyncClient, url: str) -> Optional[Portal]:
    """Verifica uma URL: faz GET (com follow_redirects=True) e retorna
    Portal se for um portal municipal plausível, None se 4xx/5xx/timeout."""
    try:
        r = await client.get(url, timeout=10.0, follow_redirects=True)
    except (httpx.RequestError, httpx.TimeoutException):
        return None

    # Cloudflare/WAF: DNS resolve, servidor responde, mas bloqueia bot.
    # Esses portais EXISTEM — só precisam de Playwright pra crawlear.
    protegido = r.status_code in (403, 429, 503)
    if r.status_code >= 400 and not protegido:
        return None

    # Detecta redirect pra página de "erro 404" (CMS comum no BA)
    url_final = str(r.url).lower()
    if "erro-404" in url_final or "/404" in url_final or "/pagenotfound" in url_final:
        return None

    titulo = None
    html = r.text[:50000] if r.text else ""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if m:
        titulo = m.group(1).strip()[:200]

    eh_oficial = bool(titulo and PADROES_TITULO_OK.search(titulo))
    # gov.br = municipal por definição (mesmo que WAF bloqueie e título seja "403")
    if ".gov.br" in str(r.url):
        eh_oficial = True

    tem_transparencia = (
        "transparencia" in html.lower() or "transparência" in html.lower()
    )

    return Portal(
        url=url,
        url_final=str(r.url),
        status=r.status_code,
        titulo=titulo,
        eh_oficial=eh_oficial,
        tem_transparencia=tem_transparencia,
        protegido_cloudflare=protegido,
    )


async def descobrir(cidade: str, uf: str) -> list[Portal]:
    """Descobre portais oficiais. Retorna lista deduplicada por url_final,
    ordenada por relevância (gov.br > .com.br, com transparência > sem)."""
    slug = _slug(cidade)
    uf = uf.strip().lower()
    urls = []
    for p in PADROES:
        try:
            urls.append(p.format(slug=slug, uf=uf))
        except KeyError:
            continue

    async with httpx.AsyncClient(
        headers={"User-Agent": "FarolPublico-Descobridor/1.0 (+https://farolpublico.com.br)"},
        verify=False,  # alguns portais municipais têm SSL ruim
        limits=httpx.Limits(max_connections=10),
    ) as client:
        resultados = await asyncio.gather(*[_check(client, u) for u in urls])

    # dedup por url_final
    visto = {}
    for p in resultados:
        if p is None:
            continue
        chave = p.url_final.rstrip("/").lower()
        if chave in visto:
            # mantém o de maior eh_oficial
            if p.eh_oficial and not visto[chave].eh_oficial:
                visto[chave] = p
            continue
        visto[chave] = p

    # ordena: gov.br primeiro, depois oficial, depois com transparência
    def score(p: Portal) -> tuple:
        return (
            ".gov.br" in p.url_final,
            p.eh_oficial,
            p.tem_transparencia,
            not p.protegido_cloudflare,  # não-bloqueado vem antes
        )

    return sorted(visto.values(), key=score, reverse=True)


# CLI simples pra testar
if __name__ == "__main__":
    import sys, json
    cidade, uf = sys.argv[1], sys.argv[2]
    portais = asyncio.run(descobrir(cidade, uf))
    print(json.dumps([p.__dict__ for p in portais], indent=2, ensure_ascii=False))
