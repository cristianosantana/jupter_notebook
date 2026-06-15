Sim — **e isso já acontece hoje**, com um detalhe importante sobre *onde* cada instrução entra.

## O que já está predefinido

O campo `system` de `narrator.yaml` é carregado na inicialização do módulo e usado como preamble fixo em toda chamada do narrador:

```29:30:src/orion_mcp_v3/runtime/narrator.py
_PROMPTS = get_prompt_registry()
_SYSTEM_PREAMBLE = _PROMPTS.get_text("narrator.base")
```

Na montagem das mensagens:

```113:129:src/orion_mcp_v3/runtime/narrator.py
    preamble = system_preamble or _SYSTEM_PREAMBLE
    ...
    system_text = preamble.strip()
    if _direct_answer_requires_literal_preservation(result):
        system_text += _DIRECT_ANSWER_LITERAL_TEMPLATE
    if reasoning:
        system_text += "\n" + reasoning.strip()
    if coverage:
        system_text += "\n" + coverage.strip()
    ...
    messages: list[ChatMessage] = [ChatMessage(role="system", content=system_text)]

    if result.prompt_text.strip():
        messages.append(ChatMessage(role="user", content=result.prompt_text))
```

Ou seja: **as ~220 linhas de regras do `system` em `narrator.yaml` vão sempre na mensagem `role=system` do LLM**, salvo override explícito (`system_preamble=...`, usado só em testes).

O teste `test_narrator_system_message_contains_anti_hallucination` confirma isso — o conteúdo inclui regras como “Nunca invente”, `answer_mode=executive`, etc.

---

## Duas camadas de “system” no pipeline

Na prática o LLM recebe **dois blocos de instrução**:

| Camada | Origem | Onde vai |
|---|---|---|
| Identidade/regras do **narrador** | `narrator.yaml` → `system` | Mensagem nativa `system` da API |
| Identidade/regras **analíticas** | `analytical_system.yaml` | Dentro de `prompt_text`, como `[SYSTEM]\n...` no `user` |

O orquestrador injeta `analytical_system` nos blocos empacotados; o `prompt_render` coloca tudo num único texto user:

```10:18:src/orion_mcp_v3/runtime/prompt_render.py
def render_blocks_to_prompt(blocks: Sequence[ContextBlock]) -> str:
    ...
    for b in blocks:
        header = b.role.value
        parts.append(f"[{header.upper()}]\n{b.text.strip()}")
```

Isso é intencional: o narrador tem **papel** (`narrator.yaml`) e **contexto da volta** (`analytical_system` + evidência + reasoning no user).

---

## O que ainda **não** está “predefinido” dinamicamente

O `system` base está sempre lá. O que **não** é ligado automaticamente são os **fragments extras** do mesmo YAML:

- `fechamento_gerencial_template`
- `critical_analysis_template`
- `pipeline_failure_template`
- `incomplete_response_template`
- `exhaustive_materialization_template`
- `metadata` (`narrator_modes`, `anti_patterns`, etc.)

Só estes fragments são acrescentados sob condição:

| Fragment | Quando |
|---|---|
| `direct_answer_literal` | `answer_mode=literal`, `result_scope.mode=all` ou `operation=list` |
| `reasoning_template` | existe bloco `reasoning_result` |
| `coverage_template` / `evidence_template` | há metadados de cobertura/evidência |

Regras do `system` como `answer_mode=operational_failure`, `response_contract.mode=exhaustive_materialization` ou fechamento gerencial **estão escritas no YAML**, mas **não têm fragment correspondente injetado** — dependem do LLM interpretar o texto estático + o que vier no `reasoning_json` / evidência no user message.

---

## Leitura do seu pedido

Se a intenção é:

> “O narrador deve nascer com a identidade e regras do `system` de `narrator.yaml`”

**Já está assim.** Não precisa de mudança para o bloco base.

Se a intenção é:

> “Cada modo (`executive`, `operational_failure`, fechamento gerencial, materialização completa) deve ter instrução **garantida** no system, não só descrita no YAML”

**Aí falta wiring** — o mesmo padrão de `direct_answer_literal`: detectar sinal no `CognitiveOrchestrationResult` e concatenar o fragment certo ao `system_text`.

---

## Risco arquitetural a ter em mente

Como `analytical_system` vai embutido no `user`, modelos podem dar mais peso ao contexto imediato (evidência, facts) do que às regras longas do `system` do narrador. Se a narração estiver “esquecendo” regras do `narrator.yaml`, a correção típica é:

1. Ligar os fragments condicionais que já existem no YAML, ou  
2. Reduzir sobreposição com `analytical_system.yaml` (deixar identidade no narrador, estrutura de resposta no analytical_system), ou  
3. Repetir regras críticas no final do system (como já faz `anti_hallucination` em `analytical_system_prompt.py`).

Se quiser implementar o wiring dos modos faltantes, mude para Agent mode e posso propor o mapa sinal → fragment com mudanças mínimas em `narrator.py`.