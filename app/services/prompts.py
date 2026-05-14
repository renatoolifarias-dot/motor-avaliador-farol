"""Prompts calibrados para avaliação ITGP por dimensão.

Cada dimensão recebe:
- Rubrica oficial da TI Brasil (3ª edição 2025)
- As 7 regras de calibração derivadas das rodadas anteriores
  (Ilhéus, Ubaitaba, Ipiaú, Pau Brasil — comparadas com gabarito oficial)
- Lista dos indicadores daquela dimensão (com pergunta, peso e opções)
- Schema das 3 tools que ela usa para acessar o dossiê e gravar
"""
from __future__ import annotations
import json
from pathlib import Path


SYSTEM_BASE = """Você é avaliador oficial do **Índice de Transparência e Governança Pública (ITGP)** \
do Instituto Nossa Ilhéus / Farol Público, baseado na metodologia da Transparência Internacional \
Brasil (3ª edição, 2025).

REGRAS NÃO-NEGOCIÁVEIS — calibradas em comparação contra Cowork multi-agente em 3 cidades:

**REGRA 1 — INDÍCIO PARCIAL VALE 0,5 (NÃO ZERO).** ⚠️ ERRO MAIS COMUM ⚠️
Se há LINK, MENU, RUBRICA EXPLÍCITA ou MENÇÃO da informação pedida mas você não pode \
verificar o conteúdo completo no dossiê crawleado, **dê 0,5** (não 0). \
Exemplos: "Plano Municipal de Saúde" listado no menu → 0,5 (não 0); \
"Relatório de Gestão Fiscal - RGF" em /transparencia/lrf → 0,5; \
Lista de licitações com filtros funcionais → 0,75. \
Cowork descobriu que Haiku zerava esses casos e ficava 7-22 pts abaixo do gabarito oficial.

**REGRA 2 — ESTRUTURA NORMATIVA VALE 0,5 ATÉ 0,75.**
Quando há LEI ou DECRETO criando o órgão/política (ex: "Lei 1271/2020 — Secretaria de Saúde") \
mas a página pública não mostra os campos exatos pedidos (ex: organograma, contatos), \
**dê 0,5**. Se a lei é citada E há alguma evidência adicional (página institucional, link), \
**dê 0,75**. Nota 0 só se NÃO há sequer a norma de criação.

**REGRA 3 — PORTAIS SAI/IBDM PADRÃO TÊM INFRAESTRUTURA TÍPICA.**
Cidades baianas usam portais SAI-Prefeitura/IBDM/GEDDOEM/kbfsistemas. \
Quando o dossiê mostra essas marcas:
- Página com FILTROS funcionais (ano, modalidade, fase) → infraestrutura existe → 0,75
- Atualizado nos últimos 12 meses → mais 0,25 (vira 1,0)
- Múltiplos campos cumpridos (i, ii, iii) → cobre o que o indicador pede

**REGRA 4 — PÁGINA EFETIVAMENTE VAZIA = 0,25 (NÃO 1,0).**
Aplicada SÓ quando você ABRIU a página e ela tem apenas placeholder \
("0 resultados encontrados", "Não realizou nos últimos anos") sem dado real. \
NÃO use 0,25 só por suspeita — exige evidência ativa.

**REGRA 5 — DEFASAGEM TEMPORAL.**
Dado mais recente >12 meses (rel. 2026-01) → divide por 2. >24m = 0. \
Atualização contínua mensal/trimestral → não desconta nada.

**REGRA 6 — EVIDÊNCIA DIRETA OBRIGATÓRIA.**
Para nota ≥0,5, `url_evidencia` DEVE ser a página específica (não homepage). \
A URL pode ser a do menu/listagem se essa for a evidência do indício parcial.

**REGRA 7 — PLURALIDADE DE FONTES.**
Dados costumam estar entre portal principal + transparencia.* + DOM. \
Use `buscar_no_dossie` com múltiplas queries antes de concluir que algo não existe.

**REGRA 8 — ANTI-FALSO-ZERO.**
Cidades baianas com nota oficial 25-50/100 NÃO têm 80%+ de itens em zero. \
Se você está zerando massivamente uma dimensão (>70% em 0), **pare e reconsidere** \
— provavelmente está sendo restritivo demais (Regras 1, 2 ou 3).

**REGRA 9 — RECOMENDAÇÃO ACIONÁVEL OBRIGATÓRIA.**
`o_que_falta` SEMPRE preenchido. Mesmo nota 1,0 tem o que melhorar. \
Nota baixa: "publicar X em formato Y na página Z".

GRANULARIDADE: 0, 0,25, 0,5, 0,75, 1,0.
- **0** = sem qualquer indício ou evidência direta de página vazia
- **0,25** = página existe mas vazia (verificado), OU norma mas sem qualquer implementação
- **0,5** = indício parcial (menu/link/lei) ou cumpre 50% dos sub-requisitos
- **0,75** = infraestrutura clara funcionando, atualizada, falta detalhe
- **1,0** = cumpre TODOS os sub-requisitos, atualizado, com evidência direta

CONFIANÇA (0-1): use <0,7 quando dossiê magro/ambíguo — sinaliza revisão humana.

ESTRATÉGIA POR INDICADOR:
1. `buscar_no_dossie(query)` com termos da pergunta
2. `ler_pagina(url)` em 1-2 mais promissoras
3. `gravar_avaliacao(...)` UMA vez

Trabalhe em ptBR. Seja honesto sobre o que descobriu.
"""


CONTEXTO_INDICADOR = """\
CIDADE: {cidade}/{uf} · CICLO: {ciclo} · SEÇÃO: {secao} · DIMENSÃO: {dimensao}

DOSSIÊ (use buscar_no_dossie/ler_pagina para acessar):
{lista_paginas}

AVALIE ESTE INDICADOR:

**{codigo}** (peso {peso}, max {nota_max}): {pergunta}

Opções: {opcoes}

Estratégia (~3-4 chamadas): buscar termos-chave → ler 1-2 páginas promissoras → gravar_avaliacao com nota, justificativa, url_evidencia específica e o_que_falta.
"""


def carregar_indicadores() -> list[dict]:
    """Carrega os 122 indicadores do JSON."""
    p = Path(__file__).parent.parent / "data" / "indicadores.json"
    return json.load(p.open())["indicadores"]


def agrupar_por_dimensao(indicadores: list[dict]) -> list[dict]:
    """Agrupa por (secao, dim_key). Retorna lista de dicts com chaves
    secao, dim_key, dim_nome, indicadores."""
    grupos = {}
    for ind in indicadores:
        chave = (ind["secao"], ind["dim_key"])
        if chave not in grupos:
            grupos[chave] = {
                "secao": ind["secao"],
                "dim_key": ind["dim_key"],
                "dim_nome": ind["dim_nome"],
                "indicadores": [],
            }
        grupos[chave]["indicadores"].append(ind)
    # ordem fixa: Geral > Saúde > Clima, mantém ordem dos códigos
    ordem_secao = {"Geral": 0, "Saúde": 1, "Clima": 2}
    return sorted(
        grupos.values(),
        key=lambda g: (ordem_secao.get(g["secao"], 99), g["dim_key"]),
    )


def formatar_lista_indicadores(indicadores: list[dict]) -> str:
    linhas = []
    for ind in indicadores:
        opcs = "; ".join(
            f"{o['nota']}={o['descricao']}" for o in ind.get("opcoes_resposta", [])
        )
        linhas.append(
            f"- **{ind['codigo']}** (peso {ind['peso']}, max {ind['nota_max']}): "
            f"{(ind.get('pergunta') or '').strip()[:300]}\n"
            f"  Opções: {opcs}"
        )
    return "\n".join(linhas)


# Schemas das tools (definidos uma vez aqui pra reutilizar)
TOOLS_SCHEMA = [
    {
        "name": "buscar_no_dossie",
        "description": (
            "Busca substring nas páginas crawleadas da cidade. Retorna até 10 URLs com snippets "
            "onde a query aparece. Use queries específicas em português (ex.: 'lei de acesso', "
            "'plano plurianual', 'diário oficial', 'ouvidoria', 'licitações'). Use múltiplas "
            "queries por indicador se preciso. Quanto mais específica, melhor."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Termo ou frase a buscar (case-insensitive).",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "ler_pagina",
        "description": (
            "Lê texto completo de uma página específica (HTML ou PDF) do dossiê. Use a URL "
            "exata retornada por buscar_no_dossie. Trunca em 30 mil caracteres."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL absoluta da página."},
            },
            "required": ["url"],
        },
    },
    {
        "name": "gravar_avaliacao",
        "description": (
            "Grava o resultado da avaliação de UM indicador. Chame uma vez por código. "
            "Não duplique — se errou, faça outra chamada sobrescrevendo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "codigo": {"type": "string", "description": "Código exato do indicador (ex.: 'L01', 'TFO20')."},
                "nota": {"type": "number", "description": "Entre 0 e nota_max. Granularidade 0.25."},
                "justificativa": {"type": "string", "description": "Por que essa nota. 2-5 frases."},
                "url_evidencia": {"type": "string", "description": "URL real da evidência (homepage genérica não vale)."},
                "o_que_falta": {"type": "string", "description": "Recomendação acionável para a prefeitura."},
                "desconto_motivos": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Motivos que reduziram a nota. Ex.: ['página vazia','defasagem >12 meses']",
                },
                "confianca": {"type": "number", "description": "0 a 1. <0.7 = pede revisão humana."},
            },
            "required": ["codigo", "nota", "justificativa", "url_evidencia", "o_que_falta", "confianca"],
        },
    },
]


def gerar_system(cidade: str, uf: str) -> str:
    """System prompt completo (regras + identidade)."""
    return SYSTEM_BASE


def gerar_user_message(
    cidade: str,
    uf: str,
    ciclo: int,
    grupo: dict,
    ind: dict,
    lista_paginas: str,
) -> str:
    """User message para UM indicador específico (não dimensão inteira).
    Reduz drasticamente o uso de tokens: cada indicador é uma conversa
    independente, sem acumular histórico de outros indicadores."""
    opcs = "; ".join(
        f"{o['nota']}={o['descricao']}" for o in ind.get("opcoes_resposta", [])
    )
    return CONTEXTO_INDICADOR.format(
        cidade=cidade, uf=uf, ciclo=ciclo,
        secao=grupo["secao"], dimensao=grupo["dim_nome"],
        lista_paginas=lista_paginas,
        codigo=ind["codigo"],
        peso=ind["peso"],
        nota_max=ind["nota_max"],
        pergunta=(ind.get("pergunta") or "").strip()[:400],
        opcoes=opcs,
    )
