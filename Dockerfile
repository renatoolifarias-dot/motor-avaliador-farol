# Dockerfile do Motor Avaliador
# Imagem base com Playwright + Python 3.11 (pesada mas inclui Chromium pronto)
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app

# Locale UTF-8 (acentos)
RUN apt-get update && apt-get install -y --no-install-recommends \
    locales \
    && sed -i '/pt_BR.UTF-8/s/^# //g' /etc/locale.gen \
    && locale-gen \
    && rm -rf /var/lib/apt/lists/*
ENV LANG=pt_BR.UTF-8 LANGUAGE=pt_BR:pt LC_ALL=pt_BR.UTF-8 TZ=America/Bahia

# Copia metadados primeiro (cache de layers)
COPY pyproject.toml ./
COPY README.md ./

# Instala dependências Python
RUN pip install --no-cache-dir -e . && \
    playwright install --with-deps chromium

# Copia código
COPY app ./app
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

EXPOSE 8000

# Comando padrão (uvicorn) — em produção usar gunicorn com workers
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
