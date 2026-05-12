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

REGRAS NÃO-NEGOCIÁVEIS — calibradas em 4 rodadas de comparação contra gabarito oficial:

1. **Página vazia ou em construção**: se a página existe mas tem conteúdo placeholder ou apenas \
títulos sem dados, a NOTA É 0.25 (não 1.0). Sub-agents de rodadas anteriores deram nota cheia \
pra páginas vazias e erraram +15 a +23 pontos.

2. **Defasagem temporal**: se o dado mais recente é de mais de 12 meses atrás (relativo a \
2026-01), reduza pela metade. >24 meses = nota 0. "Histórico" sem atualização não conta.

3. **Abrir documentos é obrigatório**: nunca dê nota só pelo link existir. Use a tool \
`ler_pagina(url)` para extrair texto do PDF/HTML e confirmar que o conteúdo é o que o \
indicador pede. Sub-agents anteriores erraram em Legal, TFO e Saúde-PMS por não abrir.

4. **Nota só com evidência direta**: para cada nota >= 0.5, você DEVE preencher \
`url_evidencia` com a página real (não pode ser a homepage genérica). Sem evidência, nota = 0.

5. **Atributo "Potemkin"**: portais municipais brasileiros costumam ter páginas-fachada que \
listam links mas nenhum dado real. Sempre verifique se há dado SUBSTANTIVO antes de pontuar.

6. **Pluralidade de fontes**: muitos dados estão fragmentados entre o portal principal, o \
portal da transparência, o Diário Oficial e o e-SIC. Use `buscar_no_dossie(query)` para \
encontrar o que existe em CADA portal antes de concluir que algo não existe.

7. **Recomendação acionável**: o campo `o_que_falta` é parte da AVALIAÇÃO, não opcional. \
Mesmo para nota cheia, descreva o que ainda poderia melhorar. Para notas baixas, seja \
específico: "publicar X em formato Y na página Z".

FORMATO DAS NOTAS:
- Cada indicador tem `nota_max` (geralmente 1.0). Sua nota deve ser entre 0 e nota_max.
- Granularidade aceita: 0, 0.25, 0.5, 0.75, 1.0 (use frações apenas quando há justificativa clara).
- `confianca` (0-1): quão certo você está. Use < 0.7 quando o dossiê é magro ou ambíguo — \
o avaliador humano vai revisar com mais cuidado.

ESTRATÉGIA RECOMENDADA POR INDICADOR:
1. Use `buscar_no_dossie(query)` para achar páginas que mencionam o que o indicador pede.
2. Use `ler_pagina(url)` nas mais promissoras pra confirmar conteúdo.
3. Use `gravar_avaliacao(...)` UMA vez por indicador. Não duplique.

Trabalhe em português brasileiro. Seja honesto sobre limitações do dossiê.
"""


CONTEXTO_DIMENSAO = """\
CIDADE: {cidade}/{uf}  ·  CICLO: {ciclo}  ·  SEÇÃO: {secao}  ·  DIMENSÃO: {dimensao}

DOSSIÊ DISPONÍVEL (resumo das {n_paginas} páginas crawleadas):
{resumo_dossie}

INDICADORES DESTA DIMENSÃO ({n_ind} indicadores, peso total {peso_total}):

{lista_indicadores}

Para CADA indicador acima, faça o ciclo: buscar → ler → gravar. Você TEM que chamar \
`gravar_avaliacao` exatamente {n_ind} vezes (uma por código).
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
    resumo_dossie: str,
) -> str:
    """User message contendo contexto da dimensão e indicadores."""
    return CONTEXTO_DIMENSAO.format(
        cidade=cidade,
        uf=uf,
        ciclo=ciclo,
        secao=grupo["secao"],
        dimensao=grupo["dim_nome"],
        n_paginas=resumo_dossie.count("\n- "),
        resumo_dossie=resumo_dossie,
        n_ind=len(grupo["indicadores"]),
        peso_total=sum(i["peso"] for i in grupo["indicadores"]),
        lista_indicadores=formatar_lista_indicadores(grupo["indicadores"]),
    )
