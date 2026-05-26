#!/bin/sh
set -eu

KB_DIR="${KB_DIR:-kb/hbcu}"
INDEX_DB="${KB_DIR}/index/hbcu_fts.db"

# Build the FTS index on first boot if it doesn't exist
if [ ! -f "$INDEX_DB" ]; then
    echo "[entrypoint] Index not found — building now..."
    python hbcu_rag.py index --kb "$KB_DIR"
    echo "[entrypoint] Index built."
else
    echo "[entrypoint] Index found at $INDEX_DB"
fi

exec gunicorn \
    --bind "0.0.0.0:${PORT:-5000}" \
    --workers 2 \
    --timeout 240 \
    --access-logfile - \
    --error-logfile - \
    app:app
