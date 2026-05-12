# Arquitetura — Motor Avaliador Farol Público

## Visão geral

```
┌──────────────────────────────────────────────────────────────────────┐
│ Locaweb (mantém — zero risco/custo adicional)                        │
│ ├─ farolpublico.com.br/  ........ Portal público (HTML estático)     │
│ └─ farolpublico.com.br/relatorios-2026/  .. Relatórios publicados   │
└──────────────────────────────────────────────────────────────────────┘
              ▲ (deploy via SFTP automático quando publica)
              │
┌──────────────────────────────────────────────────────────────────────┐
│ Servidor próprio Ubuntu 4CPU/8GB (avaliador.farolpublico.com.br)    │
│                                                                       │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────┐            │
│  │  FastAPI    │───▶│  Celery      │───▶│  Playwright  │            │
│  │  (web/API)  │    │  (workers)   │    │  (Chromium)  │            │
│  └─────┬───────┘    └──────┬───────┘    └──────────────┘            │
│        │                   │                                          │
│        ▼                   ▼                                          │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────┐            │
│  │ PostgreSQL  │    │  Redis       │    │  Claude API  │            │
│  │ (avaliações│    │ (queue/cache)│    │  (Anthropic) │            │
│  │  + evidênc) │    └──────────────┘    └──────────────┘            │
│  └─────────────┘                                                      │
│                                                                       │
│  ┌──────────── Tudo orquestrado por Coolify ────────────────────┐    │
│  │ deploy via git push + SSL automático Let's Encrypt + UI web   │    │
│  └────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

## Componentes

### Frontend (FastAPI + Jinja + HTMX + Tailwind)

- Auth com sessões (cookies HTTP-only, CSRF)
- Dashboard com lista de avaliações
- Tela de "Nova avaliação" (input cidade)
- Tela de progresso ao vivo (WebSocket ou polling)
- Tela de revisão (aprovar nota proposta pela IA)
- Tela de publicação
- Admin (usuários, configurações, API key)

### API (FastAPI)

Endpoints REST internos:
- `POST /api/avaliacoes` — criar
- `GET /api/avaliacoes/{slug}` — ler
- `POST /api/avaliacoes/{slug}/processar` — dispara worker
- `POST /api/avaliacoes/{slug}/publicar` — publica no portal
- `GET /api/avaliacoes/{slug}/progresso` — status (SSE/WebSocket)

### Workers (Celery)

Tarefas assíncronas em background:
1. `descobrir_portais(cidade, uf)` — WebSearch + verificação HEAD
2. `crawl_portal(url)` — Playwright navega, extrai texto, baixa PDFs
3. `extrair_pdf(url)` — baixa PDF e envia pra Claude API como anexo
4. `avaliar_dimensao(avaliacao_id, dim_key)` — Claude pontua uma dimensão
5. `gerar_relatorio(avaliacao_id)` — HTML/PDF
6. `publicar_portal(avaliacao_id)` — FTP upload pro Locaweb

### Crawler (Playwright + Python)

- Chromium headless oficial Microsoft
- Stealth mode (passa Cloudflare melhor que Selenium)
- Suporta interação com formulários SPA
- Captura HTML renderizado, links internos relevantes
- Detecta PDFs/DOCs e baixa pra disco temporário
- Detecta "padrão Potemkin" (página existe + conteúdo vazio)
- Detecta desatualização (timestamps antigos no conteúdo)

### IA (Claude API)

- Modelos: Haiku 4.5 (padrão), Sonnet 4.6, Opus 4.6
- **Tool use**: a IA pode chamar `fetch_url(x)` recursivamente pra investigar
- **PDFs como anexo nativo**: Claude aceita PDF via base64
- Prompt por dimensão (12 chamadas no total)
- Saída JSON estruturada: nota + justificativa + url_evidencia

### Banco (PostgreSQL)

Schema simplificado:

```
usuarios (id, username, email, perfil, senha_hash, ativo, criado_em)
configs (chave, valor, atualizado_em)
indicadores (codigo, secao, dim_key, dim_nome, pergunta, peso, nota_max, opcoes_jsonb)
padroes_url (id, label, template, dim_keys, indicadores_alvo, observacao)
avaliacoes (id, slug, cidade, uf, ciclo, status, avaliador_id, criado_em, atualizado_em)
avaliacao_itens (id, avaliacao_id, codigo, nota, justificativa, url_evidencia, ia_proposta_jsonb, confirmado, confirmado_por_id, confirmado_em)
avaliacao_paginas (id, avaliacao_id, url, status_code, texto, capturado_em, tipo)  -- dossiê do crawler
avaliacao_logs (id, avaliacao_id, nivel, mensagem, criado_em)
relatorios_publicados (id, avaliacao_id, url_publica, publicado_em, publicado_por_id)
```

### Cache/Queue (Redis)

- Queue do Celery
- Cache de páginas crawleadas (TTL 7 dias)
- Sessões web (se usar Redis-backed)

### Reverse proxy + SSL (Caddy via Coolify)

- SSL automático Let's Encrypt
- HTTP/2
- Compressão gzip/brotli
- Limites de rate

## Fluxo completo de uma avaliação

```
1. Avaliador acessa avaliador.farolpublico.com.br
2. Loga (usuário + senha)
3. Clica "+ Nova avaliação"
4. Digita "Ubaitaba", UF "BA", clica "Iniciar"
5. ── Sistema dispara worker.processar(slug=ubaitaba) ──
6.   Worker:
     6.1. Cria registro em `avaliacoes` com status='descobrindo_portais'
     6.2. Roda `descobrir_portais("Ubaitaba", "BA")`:
          - WebSearch "prefeitura Ubaitaba BA portal"
          - WebSearch "Ubaitaba transparência"
          - WebSearch "Ubaitaba câmara"
          - Para cada URL candidata: HEAD + verificar resposta
          - Salva URLs validadas em `padroes_url` (cache)
     6.3. Status='crawleando'
     6.4. Roda `crawl_portal(url)` pra cada URL principal:
          - Playwright abre, espera renderizar
          - Captura texto + links internos relevantes
          - Detecta PDFs, baixa pra disco temporário
          - Salva tudo em `avaliacao_paginas`
     6.5. Status='avaliando'
     6.6. Pra cada dimensão (12):
          - Monta dossiê (textos das páginas relevantes)
          - Anexa PDFs relevantes
          - Chama Claude com indicadores + dossiê + PDFs
          - Recebe JSON com nota + justificativa
          - Salva em `avaliacao_itens`
     6.7. Status='aguardando_revisao'
7. UI mostra "Pronto pra revisão" (via WebSocket)
8. Avaliador entra na tela de revisão
9. Lê cada indicador (nota, justificativa, link da evidência)
10. Ajusta os que discordar (override)
11. Clica "Confirmar tudo"
12. Status='confirmado'
13. Sistema gera relatório HTML/PDF
14. Avaliador clica "Publicar"
15. Worker `publicar_portal()` envia HTML por FTP pro Locaweb
16. Status='publicado'
17. Avaliador opcionalmente envia ofício à prefeitura
```

## Segurança

- Senhas: bcrypt (passlib)
- Sessões: cookies HTTP-only + Secure + SameSite=Lax
- CSRF: token por sessão em formulários POST
- API key Anthropic: variável de ambiente, nunca em código
- Acesso por IP/SSH: somente chave (sem senha)
- Banco: usuário Postgres dedicado por app
- HTTPS obrigatório (HSTS)
- Logs: sem dados pessoais; LGPD-aware

## Decisões e por quês

| Decisão | Por quê |
|---|---|
| Python (FastAPI) em vez de PHP | Ecossistema muito mais rico pra IA, Playwright, async, ML futuro |
| Playwright em vez de Selenium | Oficial Microsoft, mais rápido, melhor anti-bot |
| Coolify em vez de Kubernetes | Bem mais simples pro perfil. Uma máquina, deploy fácil |
| PostgreSQL em vez de MongoDB | Schema relacional faz sentido (auditável) + JSON nativo quando precisa |
| HTMX em vez de SPA React | UI dinâmica sem complexidade de SPA. Manutenção fácil. |
| Celery em vez de cron | Avaliações duram 15-30 min, precisam status visível + retry |
| Claude (Anthropic) | Já configurado, vision/PDF nativo, qualidade comprovada |

## Os 8 requisitos de transparência (não-negociáveis)

Veja `REQUISITOS-TRANSPARENCIA.md`. Em resumo:

1. Indicar que avaliação é por IA
2. Disclaimer "não é oficial TIB"
3. Aplicar metodologia ITGP sem alterações
4. Edital com prazos e periodicidade
5. Canal para prefeitura informar alterações
6. Canal para prefeitura corrigir URLs
7. ⭐ Relatório acessível por cidade com nota + justificativa + "o que falta" pra cada indicador
8. Atribuição: INI realiza, NIBS produz

Esses requisitos moldam:
- **Modelo de dados**: precisa campos `o_que_falta`, `desconto_motivos`, `fontes_consultadas`, `confianca`
- **Prompt da IA**: deve gerar recomendação acionável ("o que falta pra subir nota")
- **Portal público**: páginas novas (`/sobre`, `/metodologia`, `/edital-{ano}`, `/canal/*`, `/relatorios-{ano}/{cidade}`)
- **Workflow**: recursos viram tarefas de revisão; relatórios são regeráveis a cada nova avaliação

## Trade-offs assumidos

- Não vai escalar pra 10.000 cidades em paralelo (precisaria K8s/cluster). Mas dá pra ~10 simultâneas no VPS atual.
- Não tem analytics avançado / business intelligence — só portal + relatório.
- Não tem app mobile (web responsivo basta).
- Não integra com Fala.BR/CGU programaticamente (somente referencia URL).
