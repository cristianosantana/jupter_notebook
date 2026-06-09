#!/usr/bin/env python3
"""Cron entrypoint for supervised remissive memory distillation."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, Sequence

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from orion_mcp_v3.config.settings import get_settings_uncached
from orion_mcp_v3.memory.remissive_memory_store import RemissiveMemoryStore
from orion_mcp_v3.memory.remissive_models import (
    CompressionLogEntry,
    RemissiveConversationWindow,
    RemissiveEssenceItem,
    RemissiveKnowledgeItem,
    SupervisedMemoryBatch,
    build_context_key,
)
from orion_mcp_v3.memory.supervised_conversation_reader import SupervisedConversationReader
from orion_mcp_v3.protocols.llm import LLMProvider
from orion_mcp_v3.providers.openai_embedding import OpenAIEmbeddingService
from orion_mcp_v3.providers.openai_provider import OpenAIProvider


logger = logging.getLogger(__name__)


class ConversationReader(Protocol):
    async def read_window(
        self,
        start: datetime,
        end: datetime,
        *,
        limit: int = 500,
    ) -> list[RemissiveConversationWindow]: ...


class MemoryStore(Protocol):
    async def persist_batch(self, batch: SupervisedMemoryBatch) -> list[int]: ...


@dataclass(frozen=True, slots=True)
class DistillationResult:
    windows_read: int
    knowledge_written: int
    origin_ids: list[int]


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _write_failed_model_response_log(
    response_text: str,
    *,
    error: str,
    input_summary: dict[str, Any] | None = None,
    log_dir: Path | None = None,
) -> Path:
    target_dir = log_dir or (ROOT / "logs")
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = target_dir / f"distill_supervised_memory_failed_{stamp}.json"
    try:
        parsed_response: Any = json.loads(response_text)
    except json.JSONDecodeError:
        parsed_response = response_text
    path.write_text(
        json.dumps(
            {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "error": error,
                "input_summary": input_summary or {},
                "model_response": parsed_response,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _required_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Campo obrigatorio ausente ou invalido: {key}")
    return value.strip()


def _required_str_any(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    joined = " | ".join(keys)
    raise ValueError(f"Campo obrigatorio ausente ou invalido: {joined}")


def _optional_str_any(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        if not isinstance(value, str):
            raise ValueError(f"Campo deve ser string: {key}")
        if value.strip():
            return value.strip()
    return None


def _optional_str(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Campo deve ser string: {key}")
    return value.strip() or None


def _optional_text(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _confidence(data: dict[str, Any]) -> str | None:
    value = data.get("confidence")
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        score = float(value)
        if score >= 0.8:
            return "high"
        if score >= 0.5:
            return "medium"
        return "low"
    raise ValueError("Campo deve ser string ou numero: confidence")


def _compression_ratio(data: dict[str, Any]) -> float | None:
    value = data.get("compression_ratio")
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", ".")
        if not text:
            return None
        if text.endswith("%"):
            return float(text[:-1].strip()) / 100.0
        if ":" in text:
            left, right = text.split(":", 1)
            numerator = float(left.strip())
            denominator = float(right.strip())
            if denominator == 0:
                raise ValueError("compression_ratio nao pode ter denominador zero")
            return numerator / denominator
        return float(text)
    raise ValueError("Campo deve ser numero ou string numerica: compression_ratio")


def _string_tuple(data: dict[str, Any], key: str) -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"Campo deve ser lista de strings: {key}")
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


def _string_tuple_any(data: dict[str, Any], *keys: str) -> tuple[str, ...]:
    for key in keys:
        if key in data:
            return _string_tuple(data, key)
    return ()


def _mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"Campo deve ser objeto JSON: {key}")
    return dict(value)


def _input_summary(windows: Sequence[RemissiveConversationWindow]) -> dict[str, Any]:
    items = [
        {
            "session_id": window.session_id,
            "user_id": window.user_id,
            "messages_count": len(window.messages),
            "indexed_turns_count": len(window.indexed_turns),
        }
        for window in windows
    ]
    return {
        "windows_count": len(items),
        "total_messages": sum(item["messages_count"] for item in items),
        "total_indexed_turns": sum(item["indexed_turns_count"] for item in items),
        "windows": items,
    }


_VALIDATED_ANSWER_KEYS = (
    "validated_answer",
    "conteudo_resposta_validada",
    "resposta_validada",
    "validated_response",
    "answer",
    "resposta",
    "conteudo_validado",
    "conteudo",
)


def _validate_knowledge_item(item: dict[str, Any], validated_answer: str) -> bool:
    item_label = (
        item.get("context_key")
        or item.get("contexto_chave")
        or item.get("theme")
        or item.get("tema")
        or "<sem-identificador>"
    )
    if len(validated_answer.strip()) < 50:
        logger.warning("Item com resposta validada curta ignorado: %s", item_label)
        return False
    if _confidence(item) == "low":
        logger.warning("Item com baixa confiança ignorado: %s", item_label)
        return False
    return True


def _knowledge_item_or_none(item: dict[str, Any]) -> RemissiveKnowledgeItem | None:
    validated_answer = _optional_str_any(item, *_VALIDATED_ANSWER_KEYS)
    if validated_answer is None:
        return None
    if not _validate_knowledge_item(item, validated_answer):
        return None
    user_id = _optional_str(item, "user_id") or "sistema_background"
    category = _optional_str_any(item, "category", "categoria") or "Geral"
    theme = _required_str_any(item, "theme", "tema")
    periodo = _optional_str_any(item, "periodo", "period")
    return RemissiveKnowledgeItem(
        user_id=user_id,
        category=category,
        context_key=build_context_key(user_id, category, theme, periodo),
        validated_answer=validated_answer,
        recent_questions=_string_tuple_any(item, "recent_questions", "perguntas_recentes"),
        key_metrics=_mapping(item, "key_metrics"),
        index_questions=_string_tuple_any(
            item,
            "index_questions",
            "variacoes_perguntas_indice",
        ),
    )


def parse_distillation_payload(text: str) -> SupervisedMemoryBatch:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Resposta do LLM deve ser JSON estrito.") from exc
    if not isinstance(raw, dict):
        raise ValueError("Resposta do LLM deve ser um objeto JSON.")

    knowledge_raw = raw.get("knowledge", raw.get("conhecimento_lote", []))
    essence_raw = raw.get("essence", [])
    log_raw = raw.get("compression_log")
    if not isinstance(knowledge_raw, list):
        raise ValueError("Campo knowledge deve ser lista.")
    if not isinstance(essence_raw, list):
        raise ValueError("Campo essence deve ser lista.")

    knowledge_items: list[RemissiveKnowledgeItem] = []
    for item in knowledge_raw:
        if not isinstance(item, dict):
            continue
        parsed_item = _knowledge_item_or_none(item)
        if parsed_item is not None:
            knowledge_items.append(parsed_item)
    knowledge = tuple(knowledge_items)
    essence = tuple(
        RemissiveEssenceItem(
            user_id=_required_str(item, "user_id"),
            theme=_required_str(item, "theme"),
            observation=_optional_str(item, "observation"),
            key_finding=_optional_str(item, "key_finding"),
            recommendation=_optional_str(item, "recommendation"),
            stable_metrics=_mapping(item, "stable_metrics"),
            confidence=_confidence(item),
        )
        for item in essence_raw
        if isinstance(item, dict)
    )

    compression_log = None
    if log_raw is not None:
        if isinstance(log_raw, list):
            log_raw = next((item for item in log_raw if isinstance(item, dict)), None)
            if log_raw is None:
                raise ValueError("Campo compression_log deve conter objeto JSON.")
        if not isinstance(log_raw, dict):
            raise ValueError("Campo compression_log deve ser objeto JSON.")
        compression_log = CompressionLogEntry(
            user_id=_required_str(log_raw, "user_id"),
            from_state=_required_str(log_raw, "from_state"),
            to_state=_required_str(log_raw, "to_state"),
            messages_compressed=int(log_raw.get("messages_compressed", 0) or 0),
            compression_ratio=_compression_ratio(log_raw),
            what_was_kept=_optional_text(log_raw, "what_was_kept"),
            what_was_dropped=_optional_text(log_raw, "what_was_dropped"),
        )

    return SupervisedMemoryBatch(
        knowledge=knowledge,
        essence=essence,
        compression_log=compression_log,
    )


def _build_prompt(windows: Sequence[RemissiveConversationWindow]) -> str:
    payload = [
        {
            "session_id": window.session_id,
            "user_id": window.user_id,
            "messages": list(window.messages),
            "indexed_turns": list(window.indexed_turns),
        }
        for window in windows
    ]
    return (
        "Destile conversas supervisionadas em memoria remissiva V2.\n"
        "Responda somente JSON estrito com chaves: knowledge, essence, compression_log.\n"
        "knowledge[]: user_id, category, theme, periodo opcional, validated_answer, "
        "recent_questions, key_metrics, index_questions, confidence opcional.\n"
        "NUNCA gere context_key, UUID ou hash; o sistema calcula isso.\n"
        "essence[]: user_id, theme, observation, key_finding, recommendation, "
        "stable_metrics, confidence.\n"
        "compression_log: user_id, from_state, to_state, messages_compressed, "
        "compression_ratio, what_was_kept, what_was_dropped.\n"
        f"Janelas:\n{json.dumps(payload, ensure_ascii=False, default=str)}"
    )


class DistillSupervisedMemoryCommand:
    def __init__(
        self,
        reader: ConversationReader,
        store: MemoryStore,
        llm: LLMProvider,
        *,
        response_log_dir: Path | None = None,
    ) -> None:
        self._reader = reader
        self._store = store
        self._llm = llm
        self._response_log_dir = response_log_dir

    async def run(self, start: datetime, end: datetime, *, limit: int = 500) -> DistillationResult:
        windows = await self._reader.read_window(start, end, limit=limit)
        if not windows:
            return DistillationResult(windows_read=0, knowledge_written=0, origin_ids=[])

        prompt = _build_prompt(windows)
        response = await self._llm.generate(prompt, temperature=0, max_tokens=4096)
        try:
            batch = parse_distillation_payload(response.text)
        except ValueError as exc:
            log_path = _write_failed_model_response_log(
                response.text,
                error=str(exc),
                input_summary=_input_summary(windows),
                log_dir=self._response_log_dir,
            )
            raise ValueError(f"{exc}. Resposta bruta salva em: {log_path}") from exc
        if batch.compression_log is not None:
            log = batch.compression_log
            user_id = log.user_id or windows[0].user_id
            batch = replace(
                batch,
                compression_log=replace(
                    log,
                    batch_key=f"{start.isoformat()}:{end.isoformat()}:{user_id}",
                ),
            )
        origin_ids = await self._store.persist_batch(batch)
        return DistillationResult(
            windows_read=len(windows),
            knowledge_written=len(batch.knowledge),
            origin_ids=origin_ids,
        )


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


async def _run_cli(args: argparse.Namespace) -> None:
    command, pool = await _build_command()
    try:
        result = await command.run(_parse_dt(args.start), _parse_dt(args.end), limit=args.limit)
    finally:
        await pool.close()
    print(json.dumps(_result_payload(result), ensure_ascii=True))


def _result_payload(result: DistillationResult) -> dict[str, Any]:
    return asdict(result)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="Inicio da janela ISO-8601.")
    parser.add_argument("--end", required=True, help="Fim da janela ISO-8601.")
    parser.add_argument("--limit", type=int, default=500, help="Maximo de sessoes lidas.")
    return parser


def main() -> None:
    asyncio.run(_run_cli(_parser().parse_args()))


if __name__ == "__main__":
    main()
