# Calibração da IA — Lições da comparação vs Ground Truth (ITGP 2026)

> Documento vivo. Atualizado conforme novas avaliações forem comparadas com relatórios oficiais.

## Status (12/05/2026)

Avaliações sub-agent comparadas com ground truth:

| Cidade | Sub-agent | Oficial 2026 | Erro | Acertou |
|---|---|---|---|---|
| Ilhéus | 47,0 | 24,06 | **+22,94** | 56% indicadores |
| Ubaitaba | 15,2 | 28,28 | **-13,08** | 67% indicadores |

## Vieses identificados

### Viés #1 — Superestima cidade GRANDE com conteúdo, subestima cidade PEQUENA "Potemkin"

A IA usa "página existe + tem conteúdo visível" como sinal forte. Mas:
- Em cidades grandes (Ilhéus), há MUITAS páginas com conteúdo de fachada que **não cumprem o indicador inteiro**. IA dá nota cheia, oficial dá 0.
- Em cidades pequenas com Potemkin (Ubaitaba), IA zera. Mas a norma pode estar publicada no Diário Oficial, fora dessas páginas. Oficial dá nota.

**Calibração:**
- Prompt deve forçar **verificação de TODOS os requisitos** do indicador (não só "existe a página")
- Quando indicador tem rubrica do tipo "cumpre (i), (ii) e (iii)" → contar cada requisito separadamente
- Pra cidades onde menus mostram "Não informado / sem dados", buscar no Diário Oficial antes de zerar

### Viés #2 — "Vê o link, infere o conteúdo"

A IA olha um link "Decreto 128/2017" e infere que regula a LAI. Mas o decreto pode ser sobre outra coisa.

**Calibração:**
- Obrigatório abrir e ler PDFs/documentos (já anotado em `feedback_avaliacao_abrir_pdfs.md`)
- Prompt: "se a evidência depende do CONTEÚDO de um documento, é OBRIGATÓRIO ter o texto. Sem ele: 0"

### Viés #3 — Defasagem temporal não penalizada

Páginas com timestamp "atualizado em 2024" recebem nota cheia da IA. A oficial reduz.

**Calibração:**
- Heurística: conteúdo > 12 meses → no máximo 0,5
- Heurística: conteúdo > 24 meses → 0 ou 0,25

### Viés #4 — Diário Oficial é "ponto cego"

Em Ubaitaba, várias normas estão no Diário Oficial (PDFs com decretos) mas NÃO no banco /leis. IA zera. Oficial encontra.

**Calibração:**
- Pipeline `Diário Oficial → OCR → indexação semântica → busca antes de zerar indicadores Legal/AG/CEP/Saúde/Clima`
- Quando indicador exige norma e banco /leis está vazio, **OBRIGATÓRIO buscar no Diário** antes de zerar

## Top indicadores onde a IA mais erra (consistente entre Ilhéus e Ubaitaba)

| Código | Dimensão | Erro padrão | Por quê |
|---|---|---|---|
| AG03 | Admin/Governança | sub-agent dá 1 vendo link CGM; oficial exige norma de criação publicada | Não lê o decreto de criação |
| AG04 | Admin/Governança | escalão do controle interno — IA infere; oficial confere organograma | Falta verificação posicional |
| AG08 | Admin/Governança | "publica pareceres" — IA vê seção, oficial vê se TEM pareceres recentes | Não verifica recência |
| CEP01 | Comunicação | "página de conselhos" — IA vê item de menu; oficial exige listagem completa + atas | Confunde menu com conteúdo |
| CEP09 | Comunicação | "Carta de Serviços atualizada a cada 6 meses" — IA vê carta; oficial confere data | Não lê data de atualização |
| P02 | Plataformas | Dados Abertos — IA vê página; oficial exige datasets reais | Conhecido (Potemkin) |
| P08 / P09 | Plataformas | Relatórios estatísticos SIC/Ouvidoria — exigem documento periódico | Não procura PDF de relatório |

## Regras pro prompt da IA (versão calibrada)

```
Avalie cada indicador ITGP aplicando estas regras COMO PRIORIDADE:

1. PARA TODA evidência baseada em DOCUMENTO (lei, decreto, plano, relatório):
   - É OBRIGATÓRIO ter o texto do documento. Sem o conteúdo: nota 0 com justificativa "documento não acessado".
   - O nome/título do link NÃO basta. "Decreto 128/2017" pode regular qualquer coisa.

2. PARA TODA evidência baseada em PÁGINA WEB:
   - Página existe e tem conteúdo atualizado (≤12 meses): considere a rubrica oficial.
   - Página existe mas conteúdo defasado (>12 meses): no máximo 0,5.
   - Página existe mas conteúdo vazio (zero registros, "Não informado", R$ 0,00): no máximo 0,25.
   - Página 404 ou inacessível: 0.

3. PARA INDICADORES COM REQUISITOS MÚLTIPLOS (rubrica "cumpre (i), (ii) e (iii)"):
   - Verifique CADA requisito separadamente.
   - Conte quantos foram cumpridos antes de atribuir a nota.

4. PARA INDICADORES LEGAIS (L01-L06, AG09-AG10):
   - SE o banco /leis não tem a norma, busque no DIÁRIO OFICIAL antes de zerar.
   - O sistema disponibiliza ferramenta `buscar_no_diario(termo)`.

5. PARA INDICADORES DE PUBLICAÇÃO PERIÓDICA (P08, P09, TFO25-27, S-AG07 etc.):
   - "Publica" = tem PDF/documento recente, não só seção genérica.
   - Confira a DATA da última publicação. Sem datas recentes: nota ≤ 0,5.

6. PARA INDICADORES DE PARTICIPAÇÃO (CEP01-10):
   - Página de conselho ≠ existência de conselho ativo. Procure atas, regimentos, composição.

7. SEJA EXPLICITO NA JUSTIFICATIVA:
   - "Encontrei [evidência X] em [URL Y]"  ←  nota cheia
   - "Encontrei seção mas sem [requisito Z]"  ←  nota parcial
   - "Não encontrei evidência"  ←  nota 0
```

## Próximos passos de calibração

1. Aplicar o prompt calibrado ao motor novo (FastAPI/Coolify)
2. Re-avaliar Ilhéus e Ubaitaba com prompt calibrado, comparar com oficial
3. Avaliar **no escuro** cidades ainda não vistas (Alcobaça, Barro Preto, Coaraci, Ipiaú, Medeiros Neto, Nova Viçosa, Pau Brasil — TODAS têm ground truth)
4. Verificar se o viés diminui
5. Iterar
