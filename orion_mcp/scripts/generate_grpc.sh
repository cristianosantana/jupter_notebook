#!/usr/bin/env sh
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python3 -m grpc_tools.protoc \
  -I src/orion_mcp/mcp_adapter/proto \
  --python_out=src/orion_mcp/mcp_adapter/grpc_gen \
  --grpc_python_out=src/orion_mcp/mcp_adapter/grpc_gen \
  src/orion_mcp/mcp_adapter/proto/orion_mcp_tools.proto
# Ajustar import relativo ao pacote (grpc_tools emite import plano).
python3 <<'PY'
from pathlib import Path
p = Path("src/orion_mcp/mcp_adapter/grpc_gen/orion_mcp_tools_pb2_grpc.py")
text = p.read_text()
old = "import orion_mcp_tools_pb2 as orion__mcp__tools__pb2"
new = "from orion_mcp.mcp_adapter.grpc_gen import orion_mcp_tools_pb2 as orion__mcp__tools__pb2"
if old in text:
    p.write_text(text.replace(old, new, 1))
PY
