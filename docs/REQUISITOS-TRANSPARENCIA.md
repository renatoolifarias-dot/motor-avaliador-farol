# Requisitos formais de transparência do Farol Público

> Definidos por Renato em 2026-05-12. **Não-negociáveis** — devem aparecer no sistema final.

## Os 8 itens

### 1. Análise por Inteligência Artificial
**O quê:** toda página pública deve sinalizar que a avaliação foi feita por IA.

**Onde aparecer:**
- Rodapé global do site público: `"Avaliação realizada por Inteligência Artificial (modelo Claude/Anthropic) com supervisão humana."`
- Cabeçalho do relatório por cidade: badge "🤖 Avaliação por IA"
- Página "Metodologia"
- Página "Sobre o Farol Público"

### 2. Não é oficial Transparência Internacional
**O quê:** disclaimer obrigatório de que isto **não é** o ranking oficial da TIB.

**Onde aparecer:**
- Rodapé: `"O Farol Público não é o ranking oficial da Transparência Internacional Brasil (TIB). É uma iniciativa do Instituto Nossa Ilhéus que aplica a metodologia ITGP da TIB."`
- Topo de cada relatório por cidade
- Página "Sobre"

### 3. Uso de metodologia da TI sem alterações
**O quê:** texto que confirma uso EXATO da metodologia ITGP 3ª ed. (2025).

**Onde aparecer:**
- Página "Metodologia": "Aplicamos integralmente os 122 indicadores e os pesos da Nota Metodológica do ITGP — Executivo Municipal, 3ª edição (2025), publicada pela Transparência Internacional Brasil. Não modificamos rubricas ou pesos."
- Link pro PDF da Nota Metodológica
- Licença CC BY-ND 4.0 referenciada

### 4. Edital de divulgação com prazos e periodicidade
**O quê:** documento formal publicado no site explicando o calendário do ciclo.

**Conteúdo do edital:**
- Período de coleta de evidências
- Data de envio do relatório preliminar à prefeitura
- Prazo de recurso (26 dias úteis ou corridos — confirmar metodologia TIB)
- Data de publicação final
- Periodicidade (anual)
- Contato pra dúvidas

**URL:** `farolpublico.com.br/edital-2026.html` (e `edital-2027.html` etc.)

### 5. Canal de comunicação para alterações (prefeitura informa mudanças)
**O quê:** formulário onde a prefeitura informa que algo mudou após a avaliação.

**Estrutura:**
- Cidade (select)
- Nome do informante + cargo
- Email institucional (validar domínio gov.br)
- Tipo de alteração: "Norma publicada", "Plataforma nova", "Atualização de página", "Outro"
- Descrição + URL da evidência nova
- Captcha

**Fluxo:** entra como "recurso pendente" na avaliação. Avaliador (Nossa Ilhéus) recebe email e decide se re-avalia.

**URL:** `farolpublico.com.br/canal/alteracao`

### 6. Canal de informação de site correto
**O quê:** formulário onde a prefeitura aponta URL correta quando o sistema usou a errada.

**Estrutura:**
- Cidade
- Indicador (qual nota/seção)
- URL incorreta usada pelo sistema
- URL correta a usar
- Justificativa (1 parágrafo)

**Fluxo:** atualiza o mapa de URLs canônicas + dispara re-avaliação do(s) indicador(es) afetado(s).

**URL:** `farolpublico.com.br/canal/site-correto`

### 7. ⭐ Relatório acessível por cidade (CRÍTICO)
**O quê:** página detalhada por cidade que QUALQUER visitante consegue acessar e ver:

- Nota geral, por seção, por dimensão
- Para cada um dos 122 indicadores:
  - Código + pergunta completa
  - Nota dada (ex: 0,5)
  - Nota máxima possível
  - **Justificativa em linguagem natural** (1-3 frases)
  - URL de evidência consultada (clicável)
  - **O que está faltando pra atingir nota cheia** (recomendação acionável)
- Filtros: por seção, por nota (ver só os zerados), por dimensão
- Botão "Solicitar recurso" → leva ao canal #5 ou #6 com indicador pré-selecionado

**URL:** `farolpublico.com.br/relatorios-2026/{cidade}.html` (ou rota dinâmica via API)

**Por que é crítico:** é o que dá poder à prefeitura pra entender exatamente onde foi penalizada e o que precisa fazer pra melhorar. Sem isso, vira caixa-preta — o oposto de transparência.

### 8. Atribuição: INI responsável + NIBS produção
**O quê:** rodapé/cabeçalho atribui claramente:
- **Realização**: Instituto Nossa Ilhéus (INI)
- **Produção**: NIBS

**Onde aparecer:**
- Rodapé global do site público
- Cabeçalho do relatório formal (PDF/HTML)
- Topo de cada página
- Email transacional (ofício à prefeitura)

## Implicações na arquitetura

### Camada de dados (motor novo)

Cada `AvaliacaoItem` precisa ter (campos novos em relação ao atual):

```python
class AvaliacaoItem:
    codigo: str
    nota: float
    justificativa: str           # já tem
    url_evidencia: str           # já tem
    o_que_falta: str             # NOVO — recomendação acionável
    desconto_motivos: list[str]  # NOVO — por que perdeu pontos
    fontes_consultadas: list[FonteConsulta]  # NOVO — todas as URLs visitadas
    confianca: float             # NOVO — 0-1, quão confiante a IA está
    revisado_humano: bool        # NOVO — se passou pela revisão
    revisor_id: int | None
```

### Camada de apresentação (portal público)

Páginas novas necessárias:
- `/sobre` — explica o Farol Público (itens 1, 2, 3, 8)
- `/metodologia` — detalha aplicação ITGP (item 3) + PDF da TIB
- `/edital-{ano}` — calendário do ciclo (item 4)
- `/canal/alteracao` — formulário (item 5)
- `/canal/site-correto` — formulário (item 6)
- `/relatorios-{ano}/{cidade}` — relatório navegável (item 7) ⭐

Componentes globais:
- Rodapé com disclaimer + atribuição (itens 1, 2, 8)
- Banner "🤖 Avaliação por IA" no topo de relatórios

### Camada de fluxo

- **Edital** vira ato formal: publicado no portal antes do ciclo começar
- **Recursos** (canais 5 e 6) viram tarefas na fila de revisão do avaliador
- **Relatórios por cidade** são geradas a partir do banco e atualizadas a cada re-avaliação

## Próximas tarefas (a fazer depois do motor base estar pronto)

- [ ] Implementar campos `o_que_falta`, `desconto_motivos`, `confianca` no modelo
- [ ] Prompt da IA deve gerar `o_que_falta` automaticamente (instrução: "explique o que a prefeitura precisaria fazer pra subir essa nota")
- [ ] Template `/relatorios-{ano}/{cidade}` com filtros e botão de recurso
- [ ] Formulários `/canal/*` com validação + queue de recursos
- [ ] Página `/edital-{ano}` editável pelo admin (markdown)
- [ ] Rodapé global com os 4 disclaimers
- [ ] Banner "IA" no topo dos relatórios
- [ ] Email transacional do recurso (avaliador recebe quando alguém submete)
