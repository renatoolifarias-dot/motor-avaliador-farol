# Setup do Coolify no servidor

Coolify é uma plataforma open source que transforma seu VPS em algo parecido com Heroku/Railway. Vamos instalar agora e depois usar ele pra fazer o deploy do motor.

## Pré-requisitos

- Servidor Ubuntu 22.04 ou 24.04 (4 CPU / 8 GB RAM / 80 GB)
- Usuário `farol` com sudo (criado conforme `SETUP-USUARIO-SSH.md`)
- DNS apontando `avaliador.farolpublico.com.br` pro IP do servidor

## Instalação automática (recomendado)

Conecte via SSH como `farol` e execute:

```bash
ssh farol@<IP_DO_SERVIDOR>
```

Já dentro do servidor, baixe e rode o instalador oficial:

```bash
curl -fsSL https://cdn.coollabs.io/coolify/install.sh | sudo bash
```

O script vai:
1. Instalar Docker
2. Instalar Docker Compose
3. Baixar Coolify
4. Subir Coolify na porta 8000

Aguarde ~3-5 minutos. No fim aparece:

```
Coolify is reachable at:
http://<IP_DO_SERVIDOR>:8000
```

## Primeiro acesso

1. Abra `http://<IP_DO_SERVIDOR>:8000` no navegador
2. Crie a conta inicial (admin) — guarde a senha
3. Já vai cair no painel

## Configurar SSL + domínio do Coolify

Pra acessar o Coolify direto pelo subdomínio com HTTPS:

1. Aponte outro subdomínio (ex: `coolify.farolpublico.com.br`) pro IP do servidor (mesmo passo do DNS-SETUP.md)
2. No painel Coolify: **Settings → Configuration**:
   - **Instance's Domain**: `https://coolify.farolpublico.com.br`
   - Marque **HTTPS**
   - Salve
3. Aguarde ~30s pra Coolify gerar o certificado Let's Encrypt
4. Acesse `https://coolify.farolpublico.com.br` — agora com SSL ✓

## Criar projeto "Motor Avaliador"

1. No painel Coolify: **Projects → + Create**
2. Nome: `motor-avaliador`
3. Descrição: `Motor de avaliação ITGP — Farol Público`
4. Salve

## Adicionar PostgreSQL

1. Dentro do projeto, **+ Add Resource → Database → PostgreSQL**
2. Versão: 16
3. Nome: `farol-db`
4. Database name: `farol_avaliador`
5. User: `farol`
6. Coolify gera senha automática (você vai copiar pra usar no `.env` da app)
7. Salve — Coolify sobe o container e expõe internamente

## Adicionar Redis

1. **+ Add Resource → Database → Redis**
2. Nome: `farol-redis`
3. Persistência: Sim (RDB snapshot)
4. Salve

## Adicionar a app FastAPI (Motor)

### Pré-requisito: ter o código no GitHub

Crie um repositório no GitHub privado (ou público) com os arquivos de `04-codigo/motor-avaliador/`. Pode fazer assim:

```bash
# No seu PC, dentro de C:\CLAUDE\NIBS\Cidade Trasparente\04-codigo\motor-avaliador
git init
git add .
git commit -m "Esqueleto inicial"
gh repo create motor-avaliador-farol --private --source=. --remote=origin --push
```

(Precisa do `gh` cli ou criar o repo pelo site do GitHub e adicionar como remote.)

### No Coolify:

1. **+ Add Resource → Application → Public Repository (ou Private com auth GitHub)**
2. Cole a URL do repo
3. Branch: `main`
4. Build pack: **Dockerfile**
5. Dockerfile location: `Dockerfile` (raiz)
6. Domains: `avaliador.farolpublico.com.br`
7. Port mapping: `8000:8000`
8. **Environment Variables**: cole as do `.env.example` preenchidas:
   - `DATABASE_URL=postgresql+psycopg://farol:<SENHA_POSTGRES>@farol-db:5432/farol_avaliador`
   - `REDIS_URL=redis://farol-redis:6379/0`
   - `CELERY_BROKER_URL=redis://farol-redis:6379/1`
   - `CELERY_RESULT_BACKEND=redis://farol-redis:6379/2`
   - `ANTHROPIC_API_KEY=sk-ant-api03-...`
   - `SECRET_KEY=<gera string aleatória longa>`
   - `SESSION_SECRET=<outra string aleatória longa>`
   - Demais variáveis (`PORTAL_FTP_*`)
9. **Deploy**

Coolify vai:
- Clonar o repo
- Buildar a imagem Docker
- Subir o container
- Gerar SSL Let's Encrypt
- Apontar tráfego pro container

Em ~5-10 minutos `https://avaliador.farolpublico.com.br` estará no ar.

## Adicionar o Worker (Celery)

Mesma app, segunda configuração:

1. **+ Add Application** (no mesmo projeto)
2. Mesmo repo, mesma branch
3. Build pack: Dockerfile
4. Container command: sobrescrever o CMD padrão pra:
   ```
   celery -A app.workers.celery_app worker --loglevel=info --concurrency=2
   ```
5. SEM port mapping (worker não responde HTTP)
6. Mesmas env vars
7. Deploy

## Validar

Acesse `https://avaliador.farolpublico.com.br/health`:

```json
{"status":"ok","app":"Avaliador Farol Público","env":"production"}
```

Se aparecer isso, está tudo no ar.

## Manutenção

- **Atualizar código**: `git push` no repo. Coolify detecta e rebuilda automaticamente (se "Auto Deploy" estiver ligado).
- **Logs**: clica no app → "Logs" no painel Coolify
- **Backups DB**: Coolify tem aba de backup do PostgreSQL configurável.

## Troubleshooting

**"Não consigo acessar :8000"** — provavelmente o firewall do VPS bloqueia. Libere temporariamente:
```bash
sudo ufw allow 8000/tcp
```

**SSL não gera** — verifique que o DNS já propagou (`nslookup avaliador.farolpublico.com.br` aponta pro IP correto).

**App não sobe** — clica em "Logs" no Coolify, procure mensagens de erro. Geralmente é variável de ambiente faltando ou DB sem migrations.
