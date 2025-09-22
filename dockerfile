# Passo 1: Imagem base
FROM python:3.12-slim

# Passo 2: Definir o diretório de trabalho
WORKDIR /app

# Passo 3: Instalar dependências básicas do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Passo 4: Copiar o arquivo de dependências
COPY pyproject.toml . 

# Passo 5: Instalar TODAS as dependências do projeto
RUN pip install --no-cache-dir .

# Passo 6: Copiar o schema do Prisma
COPY database/schema.prisma ./database/

# Passo 7: Gerar cliente Prisma
RUN python -m prisma generate --schema=./database/schema.prisma

# Passo 8: Copiar todo o código da aplicação
COPY . .


# Passo 9: Rodar DB push + seed antes de iniciar a aplicação
CMD python -m prisma db push --schema=./database/schema.prisma && \
    python ./database/seeds/product_seeds.py && \
    python ./database/seeds/seed.py && \
    uvicorn app:app --host 0.0.0.0 --port 8000 --reload
