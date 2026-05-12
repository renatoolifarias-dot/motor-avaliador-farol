# TODO — Motor Avaliador Farol Público

## Sprint 1 — Infraestrutura e fundamentos (em curso)
- [x] Esqueleto FastAPI + Docker
- [x] Documentação arquitetura
- [x] Instruções DNS subdomínio
- [x] Instruções criação usuário SSH
- [ ] Modelos SQLModel (usuarios, indicadores, avaliacoes, itens, paginas, logs)
- [ ] Migrations Alembic
- [ ] Auth completo (bcrypt + sessões + CSRF)
- [ ] Admin de usuários
- [ ] Tela configurações (API key)
- [ ] Seed dos 122 indicadores ITGP no banco
- [ ] Script instalação Coolify
- [ ] Servidor configurado (DNS apontado + Coolify rodando + 1º deploy)

## Sprint 2 — Crawler com browser real
- [ ] Service `crawler_playwright.py` (navega, extrai texto, links internos)
- [ ] Detecção de Cloudflare e espera adequada
- [ ] Download de PDFs (com retry)
- [ ] Detecção de "padrão Potemkin" (página vazia)
- [ ] Detecção de timestamps de desatualização
- [ ] Worker Celery `crawl_portal(url)`

## Sprint 3 — IA + avaliação
- [ ] Cliente Anthropic com tool use (fetch_url recursivo)
- [ ] Anexar PDFs nativamente
- [ ] Worker Celery `avaliar_dimensao(avaliacao_id, dim_key)`
- [ ] Persistência das propostas IA no banco
- [ ] Tela de progresso ao vivo (WebSocket ou SSE)

## Sprint 4 — Revisão e relatório
- [ ] Tela revisão (lista indicadores com nota IA + justificativa)
- [ ] Botão "Confirmar tudo" e overrides individuais
- [ ] Gerador de relatório HTML/PDF (com logo)
- [ ] Worker `publicar_portal(avaliacao_id)` — FTP pro Locaweb

## Sprint 5 — Polimento e ofício
- [ ] Logo novo Farol Público (PNG) integrado
- [ ] Email transacional pra ofício
- [ ] Logs estruturados (structlog)
- [ ] Backups automáticos PostgreSQL
- [ ] Monitoramento básico (Uptime Kuma)
- [ ] Primeira avaliação real ponta-a-ponta com cidade nova

## Sprint 6 — Escala
- [ ] Otimização pra avaliações em paralelo
- [ ] Cache de Diários Oficiais (indexação full-text)
- [ ] Mapa de fornecedores de portal por município
- [ ] Avaliação em lote (varrer região inteira)
- [ ] Dashboard de QA (compara avaliações sub-agent vs oficiais)

## Sprint 7 — Os 8 requisitos de transparência (ver `docs/REQUISITOS-TRANSPARENCIA.md`)
- [ ] Modelo de dados estendido: campos `o_que_falta`, `desconto_motivos`, `fontes_consultadas`, `confianca`, `revisado_humano`
- [ ] Prompt IA gera `o_que_falta` (recomendação acionável por indicador)
- [ ] Página `/relatorios-{ano}/{cidade}` no portal público — relatório navegável com filtros (⭐ item 7)
- [ ] Botão "Solicitar recurso" em cada indicador
- [ ] Formulário `/canal/alteracao` (item 5)
- [ ] Formulário `/canal/site-correto` (item 6)
- [ ] Página `/edital-{ano}` editável (item 4)
- [ ] Página `/sobre` com itens 1, 2, 3, 8
- [ ] Página `/metodologia` (item 3)
- [ ] Rodapé global com 4 disclaimers (1, 2, 3, 8)
- [ ] Banner "🤖 Avaliação por IA" no topo dos relatórios (item 1)
- [ ] Email transacional pra recursos (queue na revisão do avaliador)
- [ ] Atribuição INI/NIBS no cabeçalho e rodapé (item 8)
