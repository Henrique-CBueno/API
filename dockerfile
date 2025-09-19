# Estágio de build
FROM python:3.12-slim as builder

# Definir variáveis de ambiente para o build
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Definir o diretório de trabalho
WORKDIR /app

# Instalar ferramentas essenciais e uv
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && pip install uv

# Copiar arquivos de dependências
COPY pyproject.toml .

# Instalar dependências
RUN uv pip install --system --no-cache .

# Copiar schema do Prisma e gerar cliente
COPY database/schema.prisma ./database/
RUN python -m prisma generate --schema=./database/schema.prisma

# Estágio final
FROM python:3.12-slim

# Definir variáveis de ambiente para produção
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Criar usuário não-root
RUN useradd -m -u 1000 appuser && \
    apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar dependências e arquivos do estágio de build
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /app/database/schema.prisma ./database/schema.prisma

# Copiar código da aplicação
COPY . .

# Definir permissões corretas
RUN chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Expor porta
EXPOSE ${PORT}

# Comando para iniciar a aplicação
CMD ["sh", "-c", "python -m prisma db push --schema=./database/schema.prisma && uvicorn app:app --host 0.0.0.0 --port=${PORT} --workers=4"]
