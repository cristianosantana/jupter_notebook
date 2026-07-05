#!/usr/bin/env python3
"""
Cron entrypoint — Destilacao Supervisionada de Memoria Remissiva V2.

Uso:
    python3 scripts/distill_supervised_memory.py \
        --start 2026-06-01T00:00:00Z \
        --end   2026-06-02T00:00:00Z

Saida JSON (stdout):
    {"windows_read": N, "knowledge_written": N, "origin_ids": [...]}

A logica de negocio vive em src/orion_mcp_v3/distillery/:
    field_parsers.py  -- extracao de campos do payload LLM
    catalog.py        -- catalogos de dimension/metric_kind e resolvedores
    payload_parser.py -- parse_distillation_payload + enrich_knowledge_from_windows
    prompt_builder.py -- build_distillation_prompt
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import unicodedata
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
SRC  = ROOT / "src"
SCRIPTS = ROOT / "scripts"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from orion_mcp_v3.config.settings import get_settings, get_settings_uncached
from orion_mcp_v3.memory.remissive_memory_store import RemissiveMemoryStore
from orion_mcp_v3.memory.remissive_models import (
    RemissiveConversationWindow,
    SupervisedMemoryBatch,
)
from orion_mcp_v3.memory.supervised_conversation_reader import SupervisedConversationReader
from orion_mcp_v3.protocols.llm import LLMProvider
from orion_mcp_v3.providers.openai_embedding import OpenAIEmbeddingService
from orion_mcp_v3.providers.openai_provider import OpenAIProvider

from distillery import (
    DistillationResult,
    build_distillation_prompt,
    enrich_knowledge_from_windows,
    parse_distillation_payload,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocolos
# ---------------------------------------------------------------------------

class ConversationReader(Protocol):
    async def read_window(
        self, start: datetime, end: datetime, *, limit: int = 500
    ) -> list[RemissiveConversationWindow]: ...

    async def mark_processed(self, windows: Sequence[RemissiveConversationWindow]) -> None: ...


class MemoryStore(Protocol):
    async def persist_batch(self, batch: SupervisedMemoryBatch) -> list[int]: ...


# ---------------------------------------------------------------------------
# Comando principal
# ---------------------------------------------------------------------------

class DistillSupervisedMemoryCommand:
    """Orquestra leitura, destilacao LLM, parse e persistencia."""

    def __init__(
        self,
        reader: ConversationReader,
        store: MemoryStore,
        llm: LLMProvider,
        *,
        response_log_dir: Path | None = None,
    ) -> None:
        self._reader   = reader
        self._store    = store
        self._llm      = llm
        self._log_dir  = response_log_dir or ROOT / "logs"

    async def run(
        self, start: datetime, end: datetime, *, limit: int = 500
    ) -> DistillationResult:
        windows = await self._reader.read_window(start, end, limit=limit)
        if not windows:
            logger.info("Nenhuma janela no periodo %s -> %s.", start, end)
            return DistillationResult(windows_read=0, knowledge_written=0, origin_ids=[])

        logger.info("Janelas lidas: %d", len(windows))
        origin_ids: list[int] = []
        knowledge_written = 0
        for period_key, period_windows in _group_windows_by_period(windows):
            logger.info("Destilando grupo de periodo %s: %d janela(s)", period_key, len(period_windows))
            prompt = build_distillation_prompt(period_windows)
            response = await self._llm.generate(
                prompt,
                temperature=0,
                max_tokens=get_settings().distillation_max_tokens,
            )

            try:
                batch = enrich_knowledge_from_windows(
                    parse_distillation_payload(response.text), period_windows
                )
            except ValueError as exc:
                log_path = _write_failed_response(
                    response.text,
                    error=str(exc),
                    windows=period_windows,
                    log_dir=self._log_dir,
                )
                raise ValueError(f"{exc}. Resposta bruta salva em: {log_path}") from exc

            batch = _stamp_batch_key(batch, start, end, period_windows, group_key=period_key)
            period_origin_ids = await self._store.persist_batch(batch)
            await self._reader.mark_processed(period_windows)
            origin_ids.extend(period_origin_ids)
            knowledge_written += len(batch.knowledge)

        logger.info(
            "Destilacao concluida -- knowledge: %d, origin_ids: %s",
            knowledge_written, origin_ids,
        )
        return DistillationResult(
            windows_read=len(windows),
            knowledge_written=knowledge_written,
            origin_ids=origin_ids,
        )


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

_MONTH_NAMES = {
    "janeiro": 1,
    "jan": 1,
    "fevereiro": 2,
    "fev": 2,
    "marco": 3,
    "março": 3,
    "mar": 3,
    "abril": 4,
    "abriu": 4,
    "abr": 4,
    "maio": 5,
    "mai": 5,
    "junho": 6,
    "jun": 6,
    "julho": 7,
    "jul": 7,
    "agosto": 8,
    "ago": 8,
    "setembro": 9,
    "set": 9,
    "outubro": 10,
    "out": 10,
    "novembro": 11,
    "nov": 11,
    "dezembro": 12,
    "dez": 12,
}


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.lower())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _message_text(message: Mapping[str, Any]) -> str:
    content = message.get("content")
    return content.strip() if isinstance(content, str) else ""


def _period_from_text(text: str) -> str | None:
    if not text.strip():
        return None
    numeric = re.search(r"\b(20\d{2})-(0[1-9]|1[0-2])\b", text)
    if numeric:
        return f"{numeric.group(1)}-{numeric.group(2)}"

    normalized = _normalize_text(text)
    year_match = re.search(r"\b(20\d{2})\b", normalized)
    if not year_match:
        return None
    year = year_match.group(1)
    for month_name, month in _MONTH_NAMES.items():
        normalized_month = _normalize_text(month_name)
        if re.search(rf"\b{re.escape(normalized_month)}\b", normalized):
            return f"{year}-{month:02d}"
    return None


def _period_from_window(window: RemissiveConversationWindow) -> str | None:
    for source in (window.messages, window.indexed_turns):
        for message in source:
            if str(message.get("role", "")).strip().lower() != "user":
                continue
            period = _period_from_text(_message_text(message))
            if period:
                return period
    for source in (window.messages, window.indexed_turns):
        for message in source:
            period = _period_from_text(_message_text(message))
            if period:
                return period
    return None


def _group_windows_by_period(
    windows: Sequence[RemissiveConversationWindow],
) -> list[tuple[str, list[RemissiveConversationWindow]]]:
    grouped: dict[str, list[RemissiveConversationWindow]] = {}
    order: list[str] = []
    for window in windows:
        period = _period_from_window(window) or f"sem_periodo:{window.session_id}"
        if period not in grouped:
            grouped[period] = []
            order.append(period)
        grouped[period].append(window)
    return [(period, grouped[period]) for period in order]


def _result_payload(result: DistillationResult) -> dict[str, Any]:
    return {
        "windows_read": result.windows_read,
        "knowledge_written": result.knowledge_written,
        "origin_ids": list(result.origin_ids),
    }

def _stamp_batch_key(
    batch: SupervisedMemoryBatch,
    start: datetime,
    end: datetime,
    windows: Sequence[RemissiveConversationWindow],
    *,
    group_key: str,
) -> SupervisedMemoryBatch:
    if batch.compression_log is None:
        return batch
    log     = batch.compression_log
    user_id = log.user_id or (windows[0].user_id if windows else "sistema_background")
    return replace(
        batch,
        compression_log=replace(
            log,
            batch_key=f"{start.isoformat()}:{end.isoformat()}:{group_key}:{user_id}",
        ),
    )


def _write_failed_response(
    response_text: str,
    *,
    error: str,
    windows: Sequence[RemissiveConversationWindow],
    log_dir: Path | None = None,
) -> Path:
    log_dir = log_dir or ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path  = log_dir / f"distill_supervised_memory_failed_{stamp}.json"
    try:
        parsed: Any = json.loads(response_text)
    except json.JSONDecodeError:
        parsed = response_text
    path.write_text(
        json.dumps(
            {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "error": error,
                "input_summary": {
                    "windows_count": len(windows),
                    "total_messages": sum(len(w.messages) for w in windows),
                    "total_indexed_turns": sum(len(w.indexed_turns) for w in windows),
                    "windows": [
                        {
                            "session_id": window.session_id,
                            "user_id": window.user_id,
                            "messages_count": len(window.messages),
                            "indexed_turns_count": len(window.indexed_turns),
                        }
                        for window in windows
                    ],
                },
                "model_response": parsed,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Wiring de dependencias (producao)
# ---------------------------------------------------------------------------

async def _build_command() -> tuple[DistillSupervisedMemoryCommand, asyncpg.Pool]:
    load_dotenv(ROOT / ".env")
    settings = get_settings_uncached(_env_file=None)
    dsn = settings.postgres_url.strip() or os.getenv("ORION_DATABASE_URL", "").strip()
    if not dsn:
        raise RuntimeError("Defina ORION_POSTGRES_URL ou ORION_DATABASE_URL.")
    if not settings.llm_api_key.strip():
        raise RuntimeError("Defina ORION_LLM_API_KEY para destilacao real.")

    pool = await asyncpg.create_pool(
        dsn,
        min_size=settings.postgres_pool_min,
        max_size=settings.postgres_pool_max,
    )
    embedding = OpenAIEmbeddingService(
        api_key=settings.llm_api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        base_url=settings.llm_base_url or None,
    )
    llm = OpenAIProvider(
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        base_url=settings.llm_base_url or None,
    )
    return (
        DistillSupervisedMemoryCommand(
            SupervisedConversationReader(pool),
            RemissiveMemoryStore(pool, embedding),
            llm,
        ),
        pool,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start", required=True, help="Inicio da janela ISO-8601 UTC.")
    p.add_argument("--end",   required=True, help="Fim da janela ISO-8601 UTC.")
    p.add_argument("--limit", type=int, default=500, help="Maximo de sessoes lidas.")
    return p


async def _run_cli(args: argparse.Namespace) -> None:
    command, pool = await _build_command()
    try:
        result = await command.run(
            _parse_dt(args.start), _parse_dt(args.end), limit=args.limit
        )
    finally:
        await pool.close()
    print(json.dumps(_result_payload(result), ensure_ascii=True))


def main() -> None:
    asyncio.run(_run_cli(_parser().parse_args()))


if __name__ == "__main__":
    main()
