#!/bin/sh
# Sobe a API: espera o banco, aplica as migrações e inicia o servidor.
set -e
cd /app
for i in $(seq 1 30); do
  if alembic upgrade head; then
    break
  fi
  echo "banco ainda não está pronto (tentativa $i), aguardando..."
  sleep 2
done
exec uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8080 --proxy-headers
