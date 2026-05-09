#!/bin/bash
set -e

# Render entrega DATABASE_URL como postgresql://...
# Normalizar quitando cualquier driver existente
RAW_URL=$(echo "$DATABASE_URL" | sed 's|^postgresql+[a-z]*://|postgresql://|')

# App async: asyncpg
export DATABASE_URL="${RAW_URL/postgresql:\/\//postgresql+asyncpg://}"

# Alembic sync: psycopg2
export DATABASE_URL_SYNC="${RAW_URL/postgresql:\/\//postgresql+psycopg2://}"

echo "==> DATABASE_URL driver: ${DATABASE_URL%%://*}"
echo "==> Ejecutando migraciones Alembic..."
alembic upgrade head

echo "==> Iniciando Uvicorn en puerto $PORT..."
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers 1
