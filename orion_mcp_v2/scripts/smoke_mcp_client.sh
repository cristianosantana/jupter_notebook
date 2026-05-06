#!/usr/bin/env bash
# Smoke do Serviço C: lista tools via MCP_SERVER_URL (servidor SSE já em execução).
# Requisitos: pip install -e ".", servidor MCP com MySQL válido e transporte SSE.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export MCP_SERVER_URL="${MCP_SERVER_URL:-http://127.0.0.1:8765/sse}"

if [[ -z "${MCP_SERVER_URL:-}" ]]; then
  echo "MCP_SERVER_URL vazio" >&2
  exit 2
fi

exec python scripts/mcp_remote_client.py
