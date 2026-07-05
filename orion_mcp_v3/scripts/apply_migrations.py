#!/usr/bin/env python3
"""
Aplica ficheiros SQL em src/orion_mcp_v3/infra/postgres/migrations/ sem precisar de `psql`.

Uso (na pasta orion_mcp_v3):

  export POSTGRES_URL="postgresql://..."   # ou usar .env
  pip install -r requirements.txt
  python3 scripts/apply_migrations.py

Variáveis aceites: POSTGRES_URL, DATABASE_URL (primeira definida ganha).
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
from asyncpg.exceptions import FeatureNotSupportedError
from dotenv import load_dotenv


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _migrations_dir() -> Path:
    return (
        _project_root()
        / "src"
        / "orion_mcp_v3"
        / "infra"
        / "postgres"
        / "migrations"
    )


def _split_sql_statements(sql_text: str) -> list[str]:
    """Divide por ';' final de instrução; ignora linhas só com comentário '--'."""
    statements: list[str] = []
    buf: list[str] = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if not stripped and not buf:
            continue
        if stripped.startswith("--") and not buf:
            continue
        buf.append(line)
        if stripped.endswith(";"):
            block = "\n".join(buf).strip()
            buf = []
            if block:
                statements.append(block)
    if buf:
        block = "\n".join(buf).strip()
        if block:
            statements.append(block)
    return statements


def _dsn() -> str:
    load_dotenv(_project_root() / ".env")
    url = os.environ.get("ORION_POSTGRES_URL") or os.environ.get("ORION_DATABASE_URL")
    if not url or not url.strip():
        print(
            "Defina ORION_POSTGRES_URL ou ORION_DATABASE_URL no ambiente ou em orion_mcp_v3/.env",
            file=sys.stderr,
        )
        sys.exit(1)
    return url.strip()


async def _run() -> None:
    dsn = _dsn()
    mig_dir = _migrations_dir()
    if not mig_dir.is_dir():
        print(f"Pasta de migrações inexistente: {mig_dir}", file=sys.stderr)
        sys.exit(1)

    files = sorted(mig_dir.glob("*.sql"))
    if not files:
        print(f"Nenhum .sql em {mig_dir}", file=sys.stderr)
        sys.exit(1)

    try:
        conn = await asyncpg.connect(dsn)
    except OSError as exc:
        _print_connect_help(dsn, exc)
        sys.exit(1)
    except Exception as exc:
        print(f"Erro ao ligar ao Postgres: {exc}", file=sys.stderr)
        _print_connect_help(dsn, exc)
        sys.exit(1)
    try:
        await _ensure_pgvector(conn)
        for path in files:
            print(f"-- {path.name}")
            text = path.read_text(encoding="utf-8")
            for stmt in _split_sql_statements(text):
                await conn.execute(stmt)
        print("OK: migrações aplicadas.")
    finally:
        await conn.close()


async def _ensure_pgvector(conn: asyncpg.Connection) -> None:
    """Tabela memory_embeddings e índice ivfflat dependem da extensão vector (pgvector)."""
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    except FeatureNotSupportedError as exc:
        _print_pgvector_help(exc)
        sys.exit(1)


def _print_pgvector_help(exc: BaseException) -> None:
    print(f"Erro: extensão pgvector não disponível neste servidor PostgreSQL.\n{exc}", file=sys.stderr)
    print(
        "\nO pacote pgvector tem de estar instalado **no sistema onde corre o Postgres**, "
        "não só no cliente Python.\n",
        file=sys.stderr,
    )
    print(
        "• Docker: use uma imagem com pgvector, por exemplo:\n"
        "    pgvector/pgvector:pg16\n"
        "  ou instale o pacote equivalente na imagem base.\n",
        file=sys.stderr,
    )
    print(
        "• Debian/Ubuntu (nome do pacote pode variar com a versão do servidor):\n"
        "    sudo apt install postgresql-16-pgvector\n",
        file=sys.stderr,
    )
    print(
        "• Depois reinicie o Postgres e volte a correr:\n"
        "    python3 scripts/apply_migrations.py\n",
        file=sys.stderr,
    )


def _print_connect_help(dsn: str, exc: BaseException) -> None:
    """Explica falhas típicas (DNS do hostname Docker no host)."""
    print(f"Detalhe: {exc}", file=sys.stderr)
    try:
        host = urlparse(dsn.replace("postgresql+asyncpg://", "postgresql://")).hostname
    except Exception:
        host = None
    print(
        "\nSe `POSTGRES_URL` usa um hostname só válido na rede Docker "
        "(ex.: cs_postgres), no seu PC esse nome não resolve — daí "
        '"Temporary failure in name resolution".',
        file=sys.stderr,
    )
    print(
        "Corrija o .env para apontar ao Postgres acessível da máquina onde corre o script, "
        "por exemplo:\n"
        "  postgresql://postgres:secret@127.0.0.1:5432/dev\n"
        "(use a porta que o compose publica no host, ex. -p 5432:5432).\n",
        file=sys.stderr,
    )
    if host:
        print(f"Hostname actual na URL: {host!r}\n", file=sys.stderr)


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
