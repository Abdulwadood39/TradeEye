#!/usr/bin/env bash
# Run Alembic migrations from anywhere in the repo.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"

export PYTHONPATH="$ROOT"
exec "$ROOT/.venv/bin/alembic" "$@"
