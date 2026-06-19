from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from orion_mcp_v3.memory.remissive_models import RemissiveConversationWindow, RemissiveKnowledgeItem, SupervisedMemoryBatch, build_context_key
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
                    "theme": "Faturamento mensal",
                    "periodo": "2026-05",
                    "validated_answer": (
                        "Faturamento validado de maio com base na conferência supervisionada "
                        "dos indicadores financeiros e operacionais do período."
                    ),
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
    assert "PROIBIDO resumir" in llm.prompts[0]
    assert "evidencias factuais preservadas" in llm.prompts[0]
    assert "NUNCA gere context_key" in llm.prompts[0]
    assert "category, context_key" not in llm.prompts[0]
    assert len(store.batches) == 1
    assert store.batches[0].knowledge[0].context_key == "sistema_background:financeiro:faturamento_mensal:2026-05"
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
                        "tema": "Fechamento Gerencial",
                        "periodo": "2026-05",
                        "conteudo_resposta_validada": (
                            "Faturamento validado de maio com base na conferência supervisionada "
                            "dos indicadores financeiros e operacionais do período."
                        ),
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
    assert batch.knowledge[0].context_key == "sistema_background:financeiro:fechamento_gerencial:2026-05"
    assert batch.knowledge[0].validated_answer.startswith("Faturamento validado de maio")
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
                        "theme": "Fechamento Gerencial",
                        "resposta_validada": (
                            "Faturamento validado de maio com base na conferência supervisionada "
                            "dos indicadores financeiros e operacionais do período."
                        ),
                        "index_questions": ["Qual foi o faturamento de maio?"],
                    }
                ],
            }
        )
    )

    assert batch.knowledge[0].validated_answer.startswith("Faturamento validado de maio")


def test_parse_distillation_payload_ignores_model_context_key_and_builds_canonical_key() -> None:
    module = _load_script_module()

    batch = module.parse_distillation_payload(
        json.dumps(
            {
                "knowledge": [
                    {
                        "user_id": "sistema_background",
                        "category": "Financeiro",
                        "theme": "Comissão por Concessionária",
                        "periodo": "2025-08",
                        "context_key": "a3f9-uuid-instavel",
                        "validated_answer": (
                            "A comissão por concessionária foi validada com base nos dados "
                            "supervisionados do fechamento financeiro do período informado."
                        ),
                        "index_questions": ["Qual foi a comissão por concessionária?"],
                    }
                ],
            }
        )
    )

    assert (
        batch.knowledge[0].context_key
        == "sistema_background:financeiro:comissao_por_concessionaria:2025-08"
    )


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


def test_parse_distillation_payload_skips_short_knowledge_answers() -> None:
    module = _load_script_module()

    batch = module.parse_distillation_payload(
        json.dumps(
            {
                "knowledge": [
                    {
                        "user_id": "sistema_background",
                        "category": "Financeiro",
                        "context_key": "resumo_curto_suspeito",
                        "validated_answer": "Faturamento ok.",
                        "index_questions": ["Qual foi o faturamento?"],
                    }
                ],
            }
        )
    )

    assert batch.knowledge == ()


def test_parse_distillation_payload_skips_low_confidence_knowledge_items(caplog) -> None:
    module = _load_script_module()

    batch = module.parse_distillation_payload(
        json.dumps(
            {
                "knowledge": [
                    {
                        "user_id": "sistema_background",
                        "category": "Financeiro",
                        "context_key": "fechamento_baixa_confianca",
                        "validated_answer": (
                            "O fechamento informado depende de validação adicional, pois os valores "
                            "do período ainda apresentam divergências entre fontes supervisionadas."
                        ),
                        "confidence": "low",
                        "index_questions": ["Qual foi o fechamento do período?"],
                    }
                ],
            }
        )
    )

    assert batch.knowledge == ()
    assert "Item com baixa confiança ignorado: fechamento_baixa_confianca" in caplog.text


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
                    "validated_answer": (
                        "Resposta validada longa o bastante para chegar à validação de chave "
                        "de contexto ausente durante o parse do lote supervisionado."
                    ),
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
    assert payload["model_response"]["knowledge"][0]["validated_answer"].startswith(
        "Resposta validada longa"
    )
    assert "theme | tema" in payload["error"]
    assert payload["input_summary"]["windows_count"] == 1
    assert payload["input_summary"]["total_messages"] == 1
    assert payload["input_summary"]["total_indexed_turns"] == 1
    assert payload["input_summary"]["windows"][0] == {
        "session_id": "sess-1",
        "user_id": "sistema_background",
        "messages_count": 1,
        "indexed_turns_count": 1,
    }


def test_enrich_knowledge_from_windows_replaces_summary_with_assistant_evidence() -> None:
    module = _load_script_module()
    evidence = (
        "direct_answer_set.headline: Faturamento líquido no período 2026-03-01 a 2026-03-31: "
        "R$ 2.713.158,18\n"
        "Formas de pagamento — Total: R$ 2.713.158,18.\n"
        "Cartão de Crédito R$ 1.352.045,28\n"
        "Depósito Bancário R$ 3.690,00\n"
        "Cheque R$ 0,00\n"
        "Permuta R$ 0,00\n"
        "Relatório de março de 2026 com detalhes completos do fechamento gerencial mensal."
    )
    windows = [
        RemissiveConversationWindow(
            session_id="sess-marco",
            user_id="sistema_background",
            messages=[
                {"role": "user", "content": "Fechamento março 2026"},
                {"role": "assistant", "content": evidence},
            ],
            indexed_turns=[],
        )
    ]
    item = RemissiveKnowledgeItem(
        user_id="sistema_background",
        category="fechamento_gerencial_mensal",
        context_key=build_context_key(
            "sistema_background",
            "fechamento_gerencial_mensal",
            "marco_2026",
            "2026-03",
        ),
        validated_answer="Resumo curto de março com Cartão dominante e Parcelamento 10X.",
        index_questions=("Qual foi o fechamento de março?",),
    )
    batch = SupervisedMemoryBatch(knowledge=(item,))

    enriched = module.enrich_knowledge_from_windows(batch, windows)

    assert enriched.knowledge[0].validated_answer == evidence


@pytest.mark.asyncio
async def test_command_prefers_assistant_evidence_over_llm_summary() -> None:
    module = _load_script_module()
    start = datetime(2026, 6, 9, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 6, 10, 0, 0, tzinfo=timezone.utc)
    evidence = (
        "direct_answer_set.headline: Faturamento líquido no período 2026-03-01 a 2026-03-31: "
        "R$ 2.713.158,18\n"
        "Formas de pagamento em março de 2026.\n"
        "Depósito Bancário R$ 3.690,00\n"
        "Cheque R$ 0,00\n"
        "Permuta R$ 0,00\n"
        "Texto factual longo o suficiente para passar na validação mínima da memória remissiva."
    )

    class EvidenceReader(FakeReader):
        async def read_window(self, start, end, *, limit=500):
            self.calls.append((start, end, limit))
            return [
                RemissiveConversationWindow(
                    session_id="sess-marco",
                    user_id="sistema_background",
                    messages=[
                        {"role": "user", "content": "Fechamento março 2026"},
                        {"role": "assistant", "content": evidence},
                    ],
                    indexed_turns=[],
                )
            ]

    store = FakeStore()
    llm = FakeLLM(
        {
            "knowledge": [
                {
                    "user_id": "sistema_background",
                    "category": "fechamento_gerencial_mensal",
                    "theme": "marco_2026",
                    "periodo": "2026-03",
                    "validated_answer": (
                        "Resumo executivo de março com Parcelamento 10X em destaque e "
                        "recomendação de limpeza para registros zero."
                    ),
                    "index_questions": ["Qual a forma de pagamento pior em março de 2026?"],
                }
            ],
            "essence": [],
            "compression_log": {
                "user_id": "sistema_background",
                "from_state": "conversation_state",
                "to_state": "memory_v2",
                "messages_compressed": 1,
            },
        }
    )

    result = await module.DistillSupervisedMemoryCommand(EvidenceReader(), store, llm).run(start, end)

    assert result.knowledge_written == 1
    assert store.batches[0].knowledge[0].validated_answer == evidence


def test_enrich_matches_only_same_year_month() -> None:
    module = _load_script_module()
    march_evidence = (
        "direct_answer_set.headline: Faturamento líquido no período 2026-03-01 a 2026-03-31: "
        "R$ 2.713.158,18\n"
        "Depósito Bancário R$ 3.690,00\n"
        "Texto factual de março longo o suficiente para passar na validação mínima da memória."
    )
    may_evidence = (
        "direct_answer_set.headline: Faturamento líquido no período 2026-05-01 a 2026-05-31: "
        "R$ 2.691.655,56\n"
        "Parcelamento 10X R$ 847.408,80\n"
        "Texto factual de maio longo o suficiente para passar na validação mínima da memória."
    )
    windows = [
        RemissiveConversationWindow(
            session_id="sess-marco",
            user_id="sistema_background",
            messages=[{"role": "assistant", "content": march_evidence}],
            indexed_turns=[],
        ),
        RemissiveConversationWindow(
            session_id="sess-maio",
            user_id="sistema_background",
            messages=[{"role": "assistant", "content": may_evidence}],
            indexed_turns=[],
        ),
    ]
    march_item = RemissiveKnowledgeItem(
        user_id="sistema_background",
        category="fechamento_gerencial_mensal",
        context_key=build_context_key(
            "sistema_background",
            "fechamento_gerencial_mensal",
            "marco_2026",
            "2026-03",
        ),
        validated_answer="Resumo errado de março.",
        index_questions=("Qual foi o fechamento de março?",),
    )
    jan_item = RemissiveKnowledgeItem(
        user_id="sistema_background",
        category="fechamento_gerencial_mensal",
        context_key=build_context_key(
            "sistema_background",
            "fechamento_gerencial_mensal",
            "janeiro_2026",
            "2026-01",
        ),
        validated_answer="Resumo errado de janeiro.",
        index_questions=("Qual foi o fechamento de janeiro?",),
    )
    batch = SupervisedMemoryBatch(knowledge=(march_item, jan_item))

    enriched = module.enrich_knowledge_from_windows(batch, windows)

    assert enriched.knowledge[0].validated_answer == march_evidence
    assert enriched.knowledge[1].validated_answer == "Resumo errado de janeiro."


def test_enrich_does_not_fallback_single_window_for_other_months() -> None:
    module = _load_script_module()
    may_evidence = (
        "direct_answer_set.headline: Faturamento líquido no período 2026-05-01 a 2026-05-31: "
        "R$ 2.691.655,56\n"
        "Texto factual de maio longo o suficiente para passar na validação mínima da memória."
    )
    windows = [
        RemissiveConversationWindow(
            session_id="sess-maio",
            user_id="sistema_background",
            messages=[{"role": "assistant", "content": may_evidence}],
            indexed_turns=[],
        )
    ]
    march_item = RemissiveKnowledgeItem(
        user_id="sistema_background",
        category="fechamento_gerencial_mensal",
        context_key=build_context_key(
            "sistema_background",
            "fechamento_gerencial_mensal",
            "marco_2026",
            "2026-03",
        ),
        validated_answer="Resumo errado de março.",
        index_questions=("Qual foi o fechamento de março?",),
    )
    batch = SupervisedMemoryBatch(knowledge=(march_item,))

    enriched = module.enrich_knowledge_from_windows(batch, windows)

    assert enriched.knowledge[0].validated_answer == "Resumo errado de março."


def test_enrich_prefers_indexed_turns_over_messages() -> None:
    module = _load_script_module()
    short_message = (
        "direct_answer_set.headline: Faturamento líquido no período 2026-03-01 a 2026-03-31: "
        "R$ 100,00"
    )
    full_indexed = (
        "direct_answer_set.headline: Faturamento líquido no período 2026-03-01 a 2026-03-31: "
        "R$ 2.713.158,18\n"
        "Depósito Bancário R$ 3.690,00\n"
        "Texto factual completo longo o suficiente para passar na validação mínima da memória."
    )
    windows = [
        RemissiveConversationWindow(
            session_id="sess-marco",
            user_id="sistema_background",
            messages=[{"role": "assistant", "content": short_message}],
            indexed_turns=[{"role": "assistant", "content": full_indexed}],
        )
    ]
    item = RemissiveKnowledgeItem(
        user_id="sistema_background",
        category="fechamento_gerencial_mensal",
        context_key=build_context_key(
            "sistema_background",
            "fechamento_gerencial_mensal",
            "marco_2026",
            "2026-03",
        ),
        validated_answer="Resumo curto.",
        index_questions=("Qual foi o fechamento de março?",),
    )
    batch = SupervisedMemoryBatch(knowledge=(item,))

    enriched = module.enrich_knowledge_from_windows(batch, windows)

    assert enriched.knowledge[0].validated_answer == full_indexed
