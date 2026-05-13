"""Gera o relatório HTML estático e (opcionalmente) envia via FTP.

O HTML é montado a partir de relatorio_publico.html. Salva localmente em
/tmp/relatorio_<slug>_<ciclo>.html e retorna o caminho. Upload via FTP é
configurável por env (FTP_HOST/USER/PASS/DIR).
"""
from __future__ import annotations
import os
import re
from io import BytesIO
from datetime import datetime
from pathlib import Path
from typing import Optional
import jinja2
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionFactory
from app.models import Avaliacao, AvaliacaoItem, AvaliacaoPagina
from app.services.tz import now_bahia
import json


def _carregar_indicadores() -> dict:
    p = Path(__file__).parent.parent / "data" / "indicadores.json"
    return {i["codigo"]: i for i in json.load(p.open())["indicadores"]}


async def montar_dados(avaliacao_id: int) -> dict:
    """Carrega tudo que o template precisa."""
    ind_full = _carregar_indicadores()
    async with AsyncSessionFactory() as session:
        av = await session.get(Avaliacao, avaliacao_id)
        if not av:
            raise ValueError("avaliação não existe")

        itens = (await session.scalars(
            select(AvaliacaoItem).where(AvaliacaoItem.avaliacao_id == avaliacao_id)
        )).all()
        itens_by_cod = {i.codigo: i for i in itens}

        total = len(itens)
        confirmados = sum(1 for i in itens if i.revisado_humano)
        paginas = await session.scalar(
            select(func.count()).select_from(AvaliacaoPagina)
            .where(AvaliacaoPagina.avaliacao_id == avaliacao_id, AvaliacaoPagina.profundidade >= 0)
        )
        pdfs = await session.scalar(
            select(func.count()).select_from(AvaliacaoPagina)
            .where(AvaliacaoPagina.avaliacao_id == avaliacao_id, AvaliacaoPagina.tipo == "pdf")
        )

    # Agrupa indicadores por dimensão (apenas os com nota)
    dim_map: dict[tuple, dict] = {}
    for cod, info in ind_full.items():
        item = itens_by_cod.get(cod)
        chave = (info["secao"], info["dim_key"])
        if chave not in dim_map:
            dim_map[chave] = {
                "secao": info["secao"],
                "dim_key": info["dim_key"],
                "dim_nome": info["dim_nome"],
                "itens": [],
                "soma": 0.0,
                "peso_total": 0,
                "pontuados": 0,
                "total": 0,
            }
        dim_map[chave]["total"] += 1
        dim_map[chave]["peso_total"] += info["peso"]
        dim_map[chave]["itens"].append({
            "codigo": cod,
            "pergunta": info["pergunta"],
            "peso": info["peso"],
            "nota_max": info["nota_max"],
            "nota": float(item.nota) if item and item.nota is not None else 0.0,
            "justificativa": item.justificativa if item else "",
            "url_evidencia": item.url_evidencia if item else "",
            "o_que_falta": item.o_que_falta if item else "",
        })
        if item and item.nota is not None:
            dim_map[chave]["pontuados"] += 1
            dim_map[chave]["soma"] += float(item.nota) * info["peso"]

    # Calcula percentual por dimensão e ordena
    ordem_secao = {"Geral": 0, "Saúde": 1, "Clima": 2}
    dimensoes = sorted(
        dim_map.values(),
        key=lambda g: (ordem_secao.get(g["secao"], 99), g["dim_key"]),
    )
    for d in dimensoes:
        d["pct"] = (d["soma"] * 100 / d["peso_total"]) if d["peso_total"] else 0

    return {
        "avaliacao": av,
        "total": total,
        "confirmados": confirmados,
        "paginas": paginas or 0,
        "pdfs": pdfs or 0,
        "dimensoes": dimensoes,
        "publicado_em": now_bahia().strftime("%d/%m/%Y às %H:%M"),
    }


async def gerar_html(avaliacao_id: int) -> tuple[str, str]:
    """Gera o HTML estático. Retorna (caminho_arquivo, slug_cidade)."""
    dados = await montar_dados(avaliacao_id)
    av = dados["avaliacao"]

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(Path(__file__).parent.parent / "templates")),
        autoescape=True,
    )
    tpl = env.get_template("relatorio_publico.html")
    html = tpl.render(**dados)

    out_path = Path("/tmp") / f"relatorio_{av.slug}_{av.ciclo}.html"
    out_path.write_text(html, encoding="utf-8")
    return str(out_path), av.slug


async def publicar_via_ftp(avaliacao_id: int) -> dict:
    """Gera + envia via FTP. Configurar FTP_HOST/USER/PASS/DIR em env."""
    caminho, slug = await gerar_html(avaliacao_id)
    ftp_host = os.environ.get("FTP_HOST", "")
    ftp_user = os.environ.get("FTP_USER", "")
    ftp_pass = os.environ.get("FTP_PASS", "")
    ftp_dir = os.environ.get("FTP_DIR", "/web/farolpublico")

    if not (ftp_host and ftp_user and ftp_pass):
        return {
            "html_local": caminho,
            "upload": "skipped",
            "motivo": "FTP_HOST/USER/PASS não configurados",
        }

    from ftplib import FTP
    # Caminho remoto: /web/farolpublico/relatorios-2026/{slug}.html
    pasta = f"relatorios-{datetime.now().year}"
    nome_arq = f"{slug}.html"
    with FTP(ftp_host, ftp_user, ftp_pass, timeout=30) as ftp:
        ftp.cwd(ftp_dir)
        try:
            ftp.mkd(pasta)
        except Exception:
            pass  # já existe
        ftp.cwd(pasta)
        with open(caminho, "rb") as f:
            ftp.storbinary(f"STOR {nome_arq}", f)
    return {
        "html_local": caminho,
        "upload": "ok",
        "url_publica": f"https://farolpublico.com.br/{pasta}/{nome_arq}",
    }



async def gerar_pdf(avaliacao_id: int) -> str:
    """Gera PDF do relatório usando Playwright (Chromium).
    Retorna caminho do arquivo PDF gerado."""
    caminho_html, slug = await gerar_html(avaliacao_id)
    pdf_path = caminho_html.replace(".html", ".pdf")

    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        # Carrega arquivo local
        await page.goto(f"file://{caminho_html}", wait_until="networkidle", timeout=20000)
        await page.pdf(
            path=pdf_path,
            format="A4",
            print_background=True,
            margin={"top": "12mm", "right": "12mm", "bottom": "12mm", "left": "12mm"},
        )
        await browser.close()
    return pdf_path
