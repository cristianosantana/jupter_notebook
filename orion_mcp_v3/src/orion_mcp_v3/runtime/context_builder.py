"""
Montagem de :class:`~ContextBlock` a partir da saída do pipeline analítico (Fase 3.5).
"""

from __future__ import annotations

import json
from typing import Any

from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.prompts import get_prompt_registry
from orion_mcp_v3.runtime.attention_policy import AttentionPolicy
from orion_mcp_v3.runtime.budget_allocator import allocate

_PROMPTS = get_prompt_registry()
_SYSTEM_TEMPLATE = _PROMPTS.get_text("analytical_context_builder.system")
_USER_ID_TEMPLATE = _PROMPTS.get_fragment("analytical_context_builder.system", "user_id")


class AnalyticalContextBuilder:
    """
    Converte dados MySQL processados (:meth:`DataPipeline.process`) em blocos de contexto.
    Opcionalmente integra memória curta estruturada.
    """

    def __init__(
        self,
        *,
        policy: AttentionPolicy = AttentionPolicy.ANALYTICAL,
    ) -> None:
        self._policy = policy

    async def build(
        self,
        pipeline_output: dict[str, Any],
        memory_curta: dict[str, Any] | None = None,
        user_id: str | None = None,
        token_budget: int = 4000,
    ) -> list[ContextBlock]:
        schema = pipeline_output.get("schema", {})
        row_count = pipeline_output.get("row_count", 0)

        system_lines = [_SYSTEM_TEMPLATE.format(schema=schema, row_count=row_count)]
        if user_id:
            system_lines.append(_USER_ID_TEMPLATE.format(user_id=user_id))
        system_text = "\n".join(system_lines)

        blocks: list[ContextBlock] = [
            ContextBlock(
                text=system_text,
                role=ContextRole.SYSTEM,
                source=ContextSource.BROKER,
                block_id="analytics:system",
                relevance_score=0.0,
                metadata={"builder": "analytical_context_v1"},
            ),
        ]

        payload = {
            "summary": pipeline_output.get("summary", {}),
            "sample": pipeline_output.get("sample", []),
            "insights": pipeline_output.get("insights", []),
        }
        data_content = json.dumps(payload, ensure_ascii=False, default=str)
        blocks.append(
            ContextBlock(
                text=data_content,
                role=ContextRole.DATA,
                source=ContextSource.BROKER,
                block_id="analytics:data",
                relevance_score=1.0,
                metadata={"builder": "analytical_context_v1"},
            )
        )

        if memory_curta:
            memory_content = json.dumps(memory_curta, ensure_ascii=False, default=str)
            blocks.append(
                ContextBlock(
                    text=memory_content,
                    role=ContextRole.CONTEXT,
                    source=ContextSource.MEMORY,
                    block_id="analytics:memory_short",
                    relevance_score=0.55,
                    metadata={"builder": "analytical_context_v1"},
                )
            )

        return list(allocate(blocks, token_budget, policy=self._policy).fitted_blocks)
