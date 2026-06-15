**Resposta curta:** os 7 YAMLs do `registry.yaml` são carregados, mas **nem tudo dentro deles é consumido em runtime**. Um prompt inteiro (`analytical_context_builder`) só entra no caminho de testes/legado.

## Inventário

| Arquivo | ID | Consumidor | No pipeline de chat? |
|---|---|---|---|
| `narrator.yaml` | `narrator.base` | `runtime/narrator.py` | Sim |
| `analytical_intent.yaml` | `analytical_intent.system` | `runtime/analytical_intent_interpreter.py` | Sim |
| `answer_presentation.yaml` | `answer_presentation.system` | `runtime/answer_presentation_interpreter.py` | Sim |
| `query_template_selector.yaml` | `query_template_selector.system` | `broker/query_template_selector.py` | Sim |
| `analytical_system.yaml` | `analytical_system.fragments` | `runtime/analytical_system_prompt.py` → `CognitiveOrchestrator` | Sim |
| `email_message_factory.yaml` | `email_message_factory.system` | `api/email/factory.py` → `sender.py` | Sim, quando há `email_to` |
| `analytical_context_builder.yaml` | `analytical_context_builder.system` | `runtime/context_builder.py` | **Não** (só testes) |

`registry.yaml`, `loader.py`, `schemas.py` e `__init__.py` são infraestrutura de carga — não são “prompts” de negócio.

---

## O que está 100% em uso

**YAMLs só com `system:`** — o texto inteiro é usado:
- `analytical_intent.yaml` → intenção analítica (LLM JSON)
- `answer_presentation.yaml` → escopo/ordenação da resposta
- `query_template_selector.yaml` → escolha template vs collection
- `email_message_factory.yaml` → extração JSON para o corpo do e-mail

**`analytical_system.yaml`** — os 10 fragments são lidos em `analytical_system_prompt.py` e injetados como bloco SYSTEM pelo orquestrador:

```21:30:src/orion_mcp_v3/runtime/analytical_system_prompt.py
_IDENTITY = _PROMPTS.get_fragment(_PROMPT_ID, "identity")
_TONE = _PROMPTS.get_fragment(_PROMPT_ID, "tone")
_STRUCTURE_ANALYTICAL = _PROMPTS.get_fragment(_PROMPT_ID, "structure_analytical")
_STRUCTURE_MANAGERIAL_CLOSING = _PROMPTS.get_fragment(_PROMPT_ID, "structure_managerial_closing")
_STRUCTURE_CONVERSATIONAL = _PROMPTS.get_fragment(_PROMPT_ID, "structure_conversational")
_EVIDENCE_RULES = _PROMPTS.get_fragment(_PROMPT_ID, "evidence_rules")
_PERIOD_TEMPLATE = _PROMPTS.get_fragment(_PROMPT_ID, "period_template")
_COVERAGE_TEMPLATE = _PROMPTS.get_fragment(_PROMPT_ID, "coverage_template")
_CONFIDENCE_LOW = _PROMPTS.get_fragment(_PROMPT_ID, "confidence_low")
_ANTI_HALLUCINATION = _PROMPTS.get_fragment(_PROMPT_ID, "anti_hallucination")
```

---

## Uso parcial: `narrator.yaml`

O campo `system` e **5 de 10 fragments** são usados em `narrator.py`:

| Fragment | Usado? |
|---|---|
| `coverage_template` | Sim |
| `evidence_template` | Sim |
| `direct_answer_literal` | Sim |
| `reasoning_template` | Sim |
| `fechamento_gerencial_template` | **Não** |
| `critical_analysis_template` | **Não** |
| `pipeline_failure_template` | **Não** |
| `incomplete_response_template` | **Não** |
| `exhaustive_materialization_template` | **Não** |

O bloco `metadata` (`narrator_modes`, `anti_patterns`, `quality_targets`, `evidence_priority`, `rendering_order`) também **não é lido pelo código** — serve como documentação/spec do prompt.

Os templates não usados parecem planejados para modos futuros (`critical`, `operational_failure`, `exhaustive_materialization`, etc.) que ainda não têm wiring em `narrator.py`.

---

## Fora do pipeline principal: `analytical_context_builder.yaml`

O prompt é carregado por `AnalyticalContextBuilder`, mas essa classe **não aparece** em `chat.py` nem em `cognitive_orchestrator.py` — só em testes (`test_analytical_context_builder.py`) e export em `runtime/__init__.py`.

O próprio YAML marca `metadata.legacy: true`. O fluxo atual usa `build_analytical_system_block()` no orquestrador, não o `AnalyticalContextBuilder`.

---

## Resumo

- **Arquivos no registry:** todos carregados.
- **No chat de produção:** 6 de 7 prompts ativos; `analytical_context_builder` é legado/teste.
- **Conteúdo interno:** `narrator.yaml` tem ~metade dos fragments e todo o `metadata` sem uso em código.
- **Possível duplicação:** `structure_managerial_closing` em `analytical_system.yaml` já cobre fechamento gerencial no SYSTEM; `fechamento_gerencial_template` em `narrator.yaml` ficou órfão.

Se quiser, no modo Agent posso mapear fragmento a fragmento com um script de auditoria ou propor qual wiring falta para os templates órfãos do narrador.