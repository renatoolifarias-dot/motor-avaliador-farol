# Motor Avaliador — Farol Público

Sistema automatizado de avaliação ITGP (Índice de Transparência e Governança Pública)
para municípios brasileiros. Aplica os 122 indicadores da metodologia ITGP 3ª edição (2025)
da Transparência Internacional Brasil.

> **Diferente do portal público** (`04-codigo/portal/`, hospedado no Locaweb).
> O motor é o **sistema do avaliador** que produz os relatórios que depois são publicados no portal.

## O que faz

1. Avaliador digita o nome da cidade + UF
2. Sistema descobre os portais da prefeitura (via WebSearch + heurísticas)
3. Crawler **com browser real (Playwright)** acessa portais SPA/Cloudflare
4. Baixa PDFs e documentos relevantes
5. **Claude API** avalia cada indicador com base nas evidências
6. Avaliador revisa propostas + confirma
7. Sistema publica relatório em `farolpublico.com.br/relatorios-{ano}/{cidade}.html`
8. Envia ofício à prefeitura por email (opcional)

## Stack

- **FastAPI** (Python 3.11+) — web/API
- **Celery + Redis** — workers em background
- **Playwright** — browser real (passa Cloudflare, renderiza SPA)
- **PostgreSQL** — banco
- **Anthropic Claude API** — IA de avaliação (Haiku/Sonnet/Opus configurável)
- **HTMX + Tailwind** — frontend leve
- **Coolify** — orquestrador no servidor (PaaS open source)

## Arquitetura

Veja [docs/ARQUITETURA.md](docs/ARQUITETURA.md).

## Instalação

### Local (desenvolvimento)

```bash
docker-compose up -d
```

### Servidor (produção)

Via Coolify — veja [docs/COOLIFY-SETUP.md](docs/COOLIFY-SETUP.md).

## Variáveis de ambiente

Copie `.env.example` para `.env` e preencha. Variáveis críticas:

- `ANTHROPIC_API_KEY` — chave da Anthropic
- `DATABASE_URL` — conexão PostgreSQL
- `REDIS_URL` — conexão Redis
- `FAROL_PORTAL_FTP_*` — credenciais do FTP do Locaweb (pra publicar relatórios)

## Status

Em desenvolvimento. Veja [TODO.md](TODO.md).
