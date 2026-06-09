from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from orion_mcp_v3.memory.remissive_models import RemissiveConversationWindow
from orion_mcp_v3.protocols.llm import LLMResponse


SCRIPT = Path("scripts/distill_supervised_memory.py")


def _load_script_module():
    spec = importlib.util.spec_from_file_location("distill_supervised_memory", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeReader:
    def __init__(self) -> None:
        self.calls: list[tuple[datetime, datetime, int]] = []

    async def read_window(
        self,
        start: datetime,
        end: datetime,
        *,
        limit: int = 500,
    ) -> list[RemissiveConversationWindow]:
        self.calls.append((start, end, limit))
        return [
            RemissiveConversationWindow(
                session_id="sess-1",
                user_id="sistema_background",
                messages=[{"role": "user", "content": "Qual foi o faturamento?"}],
                indexed_turns=[{"message_id": "sess-1:1", "content": "Qual foi o faturamento?"}],
            )
        ]


class FakeLLM:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        self.prompts.append(prompt)
        return LLMResponse(text=json.dumps(self.payload))


class FakeStore:
    def __init__(self) -> None:
        self.batches = []

    async def persist_batch(self, batch):
        self.batches.append(batch)
        return [301]


@pytest.mark.asyncio
async def test_command_distills_window_with_fake_llm_and_persists_batch() -> None:
    module = _load_script_module()
    start = datetime(2026, 6, 9, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 6, 10, 0, 0, tzinfo=timezone.utc)
    reader = FakeReader()
    store = FakeStore()
    llm = FakeLLM(
        {
            "knowledge": [
                {
                    "user_id": "sistema_background",
                    "category": "Financeiro",
                    "context_key": "faturamento_2026_05",
                    "validated_answer": "Faturamento validado de maio.",
                    "recent_questions": ["Qual foi o faturamento?"],
                    "key_metrics": {"faturamento": 2696125.56},
                    "index_questions": ["Qual foi o faturamento de maio?"],
                }
            ],
            "essence": [
                {
                    "user_id": "sistema_background",
                    "theme": "fechamento_mensal",
                    "key_finding": "Maio tem faturamento validado.",
                    "confidence": "high",
                }
            ],
            "compression_log": {
                "user_id": "sistema_background",
                "from_state": "conversation_state",
                "to_state": "memory_v2",
                "messages_compressed": 1,
                "compression_ratio": 0.5,
                "what_was_kept": "Faturamento validado.",
                "what_was_dropped": "Pergunta original duplicada.",
            },
        }
    )

    result = await module.DistillSupervisedMemoryCommand(reader, store, llm).run(start, end, limit=25)

    assert result == module.DistillationResult(windows_read=1, knowledge_written=1, origin_ids=[301])
    assert reader.calls == [(start, end, 25)]
    assert "sess-1" in llm.prompts[0]
    assert len(store.batches) == 1
    assert store.batches[0].knowledge[0].context_key == "faturamento_2026_05"
    assert store.batches[0].essence[0].theme == "fechamento_mensal"
    assert store.batches[0].compression_log.messages_compressed == 1
    assert (
        store.batches[0].compression_log.batch_key
        == "2026-06-09T00:00:00+00:00:2026-06-10T00:00:00+00:00:sistema_background"
    )


def test_parse_distillation_payload_rejects_non_json_text() -> None:
    module = _load_script_module()

    with pytest.raises(ValueError, match="JSON"):
        module.parse_distillation_payload("Aqui esta o resumo: {bad json}")


def test_distillation_result_serializes_without_dict_attribute() -> None:
    module = _load_script_module()
    result = module.DistillationResult(windows_read=1, knowledge_written=2, origin_ids=[10, 11])

    assert not hasattr(result, "__dict__")
    assert module._result_payload(result) == {
        "windows_read": 1,
        "knowledge_written": 2,
        "origin_ids": [10, 11],
    }


def test_parse_distillation_payload_normalizes_numeric_confidence() -> None:
    module = _load_script_module()

    batch = module.parse_distillation_payload(
        json.dumps(
            {
                "knowledge": [],
                "essence": [
                    {
                        "user_id": "sistema_background",
                        "theme": "fechamento_mensal",
                        "confidence": 0.95,
                    }
                ],
            }
        )
    )

    assert batch.essence[0].confidence == "high"


def test_parse_distillation_payload_serializes_structured_compression_details() -> None:
    module = _load_script_module()

    batch = module.parse_distillation_payload(
        json.dumps(
            {
                "knowledge": [],
                "essence": [],
                "compression_log": {
                    "user_id": "sistema_background",
                    "from_state": "conversation_state",
                    "to_state": "memory_v2",
                    "what_was_kept": ["faturamento validado", "perguntas indice"],
                    "what_was_dropped": {"duplicadas": 3},
                },
            }
        )
    )

    assert batch.compression_log is not None
    assert batch.compression_log.what_was_kept == '["faturamento validado", "perguntas indice"]'
    assert batch.compression_log.what_was_dropped == '{"duplicadas": 3}'


def test_parse_distillation_payload_accepts_ratio_string_compression_ratio() -> None:
    module = _load_script_module()

    batch = module.parse_distillation_payload(
        json.dumps(
            {
                "knowledge": [],
                "essence": [],
                "compression_log": {
                    "user_id": "sistema_background",
                    "from_state": "conversation_state",
                    "to_state": "memory_v2",
                    "compression_ratio": "49:1",
                },
            }
        )
    )

    assert batch.compression_log is not None
    assert batch.compression_log.compression_ratio == 49.0


def test_parse_distillation_payload_accepts_single_item_compression_log_list() -> None:
    module = _load_script_module()

    batch = module.parse_distillation_payload(
        json.dumps(
            {
                "knowledge": [],
                "essence": [],
                "compression_log": [
                    {
                        "user_id": "sistema_background",
                        "from_state": "raw_windows_v2",
                        "to_state": "memoria_remissiva_v2",
                        "messages_compressed": 3,
                    }
                ],
            }
        )
    )

    assert batch.compression_log is not None
    assert batch.compression_log.from_state == "raw_windows_v2"
    assert batch.compression_log.messages_compressed == 3


def test_parse_distillation_payload_accepts_portuguese_knowledge_keys() -> None:
    module = _load_script_module()

    batch = module.parse_distillation_payload(
        json.dumps(
            {
                "conhecimento_lote": [
                    {
                        "contexto_chave": "fechamento_gerencial_2026_05",
                        "conteudo_resposta_validada": "Faturamento validado de maio.",
                        "variacoes_perguntas_indice": [
                            "Qual foi o faturamento de maio?",
                            "Quanto a empresa vendeu em maio?",
                        ],
                        "categoria": "Financeiro",
                    }
                ],
                "auditoria": {"registros_analisados": 1},
            }
        )
    )

    assert len(batch.knowledge) == 1
    assert batch.knowledge[0].user_id == "sistema_background"
    assert batch.knowledge[0].category == "Financeiro"
    assert batch.knowledge[0].context_key == "fechamento_gerencial_2026_05"
    assert batch.knowledge[0].validated_answer == "Faturamento validado de maio."
    assert batch.knowledge[0].index_questions == (
        "Qual foi o faturamento de maio?",
        "Quanto a empresa vendeu em maio?",
    )


def test_parse_distillation_payload_accepts_common_validated_answer_aliases() -> None:
    module = _load_script_module()

    batch = module.parse_distillation_payload(
        json.dumps(
            {
                "knowledge": [
                    {
                        "context_key": "fechamento_gerencial_2026_05",
                        "resposta_validada": "Faturamento validado de maio.",
                        "index_questions": ["Qual foi o faturamento de maio?"],
                    }
                ],
            }
        )
    )

    assert batch.knowledge[0].validated_answer == "Faturamento validado de maio."


def test_parse_distillation_payload_skips_empty_knowledge_items() -> None:
    module = _load_script_module()

    batch = module.parse_distillation_payload(
        json.dumps(
            {
                "knowledge": [
                    {
                        "user_id": "sistema_background",
                        "category": "empty_sessions",
                        "context_key": "janelas_49_vazias",
                        "validated_answer": "",
                        "recent_questions": [],
                        "key_metrics": {"sessions_count": 49},
                        "index_questions": [],
                    }
                ],
                "essence": [
                    {
                        "user_id": "sistema_background",
                        "theme": "ausencia_de_conteudo",
                        "observation": "Todas as janelas fornecidas estão sem mensagens.",
                        "confidence": 0.99,
                    }
                ],
                "compression_log": {
                    "user_id": "sistema_background",
                    "from_state": "49 raw session windows vazias",
                    "to_state": "1 resumo sintetizado",
                    "messages_compressed": 0,
                    "compression_ratio": 49.0,
                },
            }
        )
    )

    assert batch.knowledge == ()
    assert len(batch.essence) == 1
    assert batch.compression_log is not None


@pytest.mark.asyncio
async def test_command_logs_raw_model_response_when_parse_fails(tmp_path) -> None:
    module = _load_script_module()
    start = datetime(2026, 6, 9, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 6, 10, 0, 0, tzinfo=timezone.utc)
    reader = FakeReader()
    store = FakeStore()
    llm = FakeLLM(
        {
            "knowledge": [
                {
                    "validated_answer": "Resposta sem chave de contexto.",
                    "index_questions": ["pergunta sem resposta"],
                }
            ]
        }
    )

    command = module.DistillSupervisedMemoryCommand(
        reader,
        store,
        llm,
        response_log_dir=tmp_path,
    )

    with pytest.raises(ValueError, match="Resposta bruta salva em"):
        await command.run(start, end)

    logs = list(tmp_path.glob("distill_supervised_memory_failed_*.json"))
    assert len(logs) == 1
    payload = json.loads(logs[0].read_text(encoding="utf-8"))
    assert payload["model_response"]["knowledge"][0]["validated_answer"] == "Resposta sem chave de contexto."
    assert "context_key" in payload["error"]
    assert payload["input_summary"]["windows_count"] == 1
    assert payload["input_summary"]["total_messages"] == 1
    assert payload["input_summary"]["total_indexed_turns"] == 1
    assert payload["input_summary"]["windows"][0] == {
        "session_id": "sess-1",
        "user_id": "sistema_background",
        "messages_count": 1,
        "indexed_turns_count": 1,
    }
