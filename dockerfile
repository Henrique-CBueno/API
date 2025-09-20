
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

# Passo 6: Agora que o Prisma está instalado, copie o schema
COPY database/schema.prisma ./database/

# Passo 7: Execute o comando generate usando o módulo Python
RUN python -m prisma generate --schema=./database/schema.prisma

# Passo 8: Copiar todo o código da aplicação
COPY . .

# Passo 9: Expor a porta
EXPOSE 8000

# Passo 10: Comando para iniciar o contêiner
CMD ["sh", "-c", "python -m prisma db push --schema=./database/schema.prisma && uvicorn app:app --host 0.0.0.0 --port 8000 --reload"]
