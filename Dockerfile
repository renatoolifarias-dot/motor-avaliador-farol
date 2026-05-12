# Dockerfile do Motor Avaliador
# Usa Ubuntu 24.04 Noble com Python 3.12 + Playwright pré-instalado
FROM mcr.microsoft.com/playwright/python:v1.48.0-noble

WORKDIR /app

# Locale UTF-8 + timezone
RUN apt-get update && apt-get install -y --no-install-recommends \
    locales tzdata \
    && sed -i '/pt_BR.UTF-8/s/^# //g' /etc/locale.gen \
    && locale-gen \
    && ln -fs /usr/share/zoneinfo/America/Bahia /etc/localtime \
    && rm -rf /var/lib/apt/lists/*
ENV LANG=pt_BR.UTF-8 LANGUAGE=pt_BR:pt LC_ALL=pt_BR.UTF-8 TZ=America/Bahia
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# Copia metadados (cache de layers)
COPY pyproject.toml README.md ./

# Instala dependências Python (Playwright Chromium já está na imagem base)
RUN pip install --no-cache-dir --break-system-packages -e .

# Copia código
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
