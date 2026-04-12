Segue a narrativa técnica alinhada à skill **agente_storytelling** (estrutura de jornada + concretude; público **comunidade técnica**; tom **analítico/educativo**). Baseei-me no código em `app/main.py`, `app/orchestrator.py`, `app/prompt_assembly.py`, `app/routing_tools.py` e `ai_provider/openai_chat_sanitize.py`.

---

## 1. O ponto de entrada: da caixa de texto ao `agent.run`

A história começa quando o utilizador envia uma mensagem. No frontend, o `fetch` para `/api/chat` monta um JSON com `message`, e opcionalmente `session_id`, `user_id`, `target_agent` e `trace_run_id`. No servidor, `process_chat` em `app/main.py` é o corredor central: resolve sessão em PostgreSQL (se activo), cria ou reidrata a sessão, e chama `await agent.run(request.message, target_agent=..., session_id=..., session_metadata=...)`. A partir daqui, o teu pedido deixa de ser “texto no browser” e passa a ser **estado mutável** (`session_metadata`, mensagens do orquestrador, agente corrente) até voltar como `reply`, `content_blocks`, `tools_used` e `agent_used`.

---

## 2. Preparação do palco: `run()` e a âncora da conversa

Dentro de `ModularOrchestrator.run`, o sistema fixa `session_metadata` e `session_id`, limpa flags como `formatador_ui_applied` do turno anterior, e decide se há **auto-roteamento** (`target_agent is None` → Maestro decide o especialista).

Antes do drama do LLM, a primeira jogada estrutural é **gravar a intenção do utilizador com uma âncora interna**:

```1929:1934:app/orchestrator.py
            self._append_message({
                "role": "user",
                "content": user_input,
                "_orch_anchor": True,
            })
```

Essa chave `_orch_anchor` não vai para a API (é removida ao construir mensagens públicas); serve para a **poda do histórico** não “comer” o início da conversa de forma cega.

---

## 3. Acto I — O Maestro: só uma ferramenta, e ela não existe no MCP

`_prepare_agent_for_run` garante que, em modo automático, se não estás a continuar já com um especialista carregado, o agente activo volta a ser `maestro`. Aí entra a fase `_run_maestro_routing_phase`.

O Maestro não vê `list_tools` do MCP. Ele vê **apenas** a ferramenta virtual `route_to_specialist`, definida em `app/routing_tools.py` como `MAESTRO_TOOLS_ONLY` — um “function calling” OpenAI-style que o orquestrador **intercepta**: não é o servidor MCP que executa o handoff; é o Python que lê os argumentos e chama `set_agent(specialist)`.

O modelo é empurrado a chamar essa função com `tool_choice` fixo para `route_to_specialist` (`_maestro_tool_choice_dict`). Se a API devolver texto em vez de tool call, existe **fallback** por tokens legados (`ANALISE_OS`, `CLUSTERIZACAO`, etc. em `specialist_from_text_fallback`).

Quando o handoff é válido, `set_agent` **carrega o SKILL** do especialista a partir de `app/skills/*.md` e **limpa** `self.messages` — o histórico do Maestro não contamina o especialista. Em seguida, o mesmo `user_input` é reapendido como mensagem `user` “limpa”, já no contexto do novo papel. Para `analise_os`, com certas flags, ainda corre `_refresh_entity_glossary` ao handoff.

Se o Maestro não conseguir rotear, o fluxo termina cedo com uma resposta textual de erro (sem MCP).

---

## 4. Montagem do contexto: a fusão ordenada do system

Enquanto o modelo “pensa”, o system não é um ficheiro único: é **composição determinística** descrita em `build_effective_system_text` em `app/prompt_assembly.py`:

**Ordem:** `shared.md` → `writing.md` → `context-policy.md` → `agents/{agent}.md` → corpo do **SKILL** do agente → instruções por ferramenta (ficheiros `app/prompts/tools/{nome}.md`) → **glossário de entidades** (markdown) → **digest do cache MCP** (e retrieval semântico quando injectado) → blocos de **memória** (resumo, notas, extração) se as flags estiverem ligadas.

A diferença Maestro vs especialista está explícita: no Maestro, os nomes das tools vêm do payload OpenAI (`MAESTRO_TOOLS_ONLY`) e incluem o prompt da tool virtual; no especialista, vêm das tools MCP reais.

O digest MCP pode ser só Python (`build_mcp_cache_digest_section`) ou, se configurado, passar por um **refino com LLM** (`_llm_refine_mcp_digest`) com prompt interno — outra camada de “contexto derivado”, não do utilizador.

O SKILL efectivo enviado ao chat não é só metadata: `_messages_with_skill` funde o texto grande do system **no primeiro bloco `system`** ou injecta um `system` no início se não existir:

```211:227:app/orchestrator.py
def _messages_with_skill(
    skill: str,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    public = [_strip_orch_internal_keys(m) for m in messages]
    if not skill:
        return list(public)
    out = list(public)
    had_system = any(m.get("role") == "system" for m in out)
    for i, m in enumerate(out):
        if m.get("role") == "system":
            existing = (m.get("content") or "").strip()
            merged = f"{skill}\n\n{existing}".strip() if existing else skill
            out[i] = {**m, "content": merged}
    if not had_system:
        out.insert(0, {"role": "system", "content": skill})
    return out
```

Ou seja: **budget de contexto** do frontmatter do SKILL + texto de prompts partilhados + digest + glossário entram na mesma “sopa” que o modelo vê como system+histórico.

---

## 5. A poda: tempo, tokens e o tecto do orçamento

Antes de cada volta ao LLM (Maestro ou especialista), `_cap_messages` → `_prune_messages` corre.

**Primeiro eixo — TTL:** mensagens mais antigas que `orchestrator_max_message_age_seconds` são removidas por segmentos, **exceto** se a primeira mensagem tiver `_orch_anchor`.

**Segundo eixo — tokens estimados:** estima-se o prompt como SKILL fundido + histórico (`_estimate_prompt_tokens_messages_plus_skill`). Compara-se com um limiar (`orchestrator_history_prune_token_threshold`), um alvo após poda (`..._target_fraction`), um **cap absoluto** de número de mensagens, e opcionalmente um **tecto duro** derivado do `context_budget` do SKILL menos `max_tokens` reservados à resposta, custo estimado das definições de tools e margem de segurança (`_effective_input_token_cap`).

Enquanto o prompt for “grande demais”, remove-se o **primeiro segmento** conversacional (via `pop_first_segment`) ou, em último caso, faz-se `pop(0)` na lista — mas **nunca** se remove o segmento que contém a âncora `_orch_anchor` (protecção explícita no `while`).

Isto é a narrativa da **poda**: não é só “cortar texto”; é **política de memória** com três camadas (idade, contagem, orçamento semântico aproximado).

---

## 6. Acto II — Especialista: contexto semântico antes das tools MCP

Depois do Maestro, se o fluxo não terminou cedo, corre `_inject_semantic_context_for_specialist`. Aqui o host chama **MCP de verdade** — `client.call_tool("context_retrieve_similar", {...})` — com timeout e limites de caracteres. O resultado markdown vai para `_semantic_retrieval_markdown` e entra no digest do system (via `build_mcp_cache_digest_section`). É o “lembrar conversas / índice” sem o modelo ter pedido explicitamente; é **montagem proactiva de contexto**.

Há atalhos: saudações curtas não disparam; Maestro não dispara; sem `session_id` não dispara.

---

## 7. Ferramentas virtuais vs físicas: quem executa o quê

**Virtual (só no orquestrador):**

- `route_to_specialist` — só no Maestro; handoff interno.
- `analytics_aggregate_session` — injectada em `_tools_payload_for_specialist` quando há cache de sessão; a execução é **Python local** (`load_dataset_for_aggregate`, `run_analytics_aggregate`) sobre dados já cacheados da sessão, não é um round-trip arbitrário ao MCP (embora os dados possam ter vindo de MCP antes).

**Físicas (MCP):**

- Qualquer outra tool name passa por `_execute_single_tool_call` → `self.client.call_tool(name, args)` com timeout, truncagem (`tool_message_content_max_chars`, `safe_truncate_tool_content`), registo em `tools_used`, e **cache de sessão** (`mcp_tool_cache`) para hits repetidos (`[cache_hit]\n` + resultado).
- Casos especiais: `run_analytics_query` pode registar **datasets de sessão** e injectar `session_dataset_id` no JSON devolvido; `context_retrieve_similar` pode ser **deduplicada** se for igual à injectada pelo host.

**Bloqueio narrativo:** se um especialista tentar `route_to_specialist`, recebe mensagem de tool a explicar que só o Maestro roteia — é uma barreira de **separação de papéis**.

---

## 8. O loop do especialista: pedir dados até poder responder em texto

`_run_specialist_loop` incrementa `step` até ao máximo configurado; em cada iteração: poda → system async (digest pode mudar) → `model.chat` com **todas** as tools MCP (filtradas por allowlist opcional por agente) + possível `analytics_aggregate_session`.

Se o modelo devolver `tool_calls`, a resposta assistant (muitas vezes placeholder) é guardada no histórico e cada tool corre em sequência. Quando **não** há mais tool calls, devolve-se o dicionário com `assistant`, `tools_used` e `agent`.

---

## 9. Pós-processamento: crítica, UI, verificação e layout

Para respostas de especialista (não Maestro terminal), o fluxo pode ainda:

- **`_run_critique_refine_loop`** — avaliador crítico (outro SKILL) com digest MCP; pode aprovar ou pedir refinamento com mais voltas ao modelo.
- **`_run_formatador_ui`** — outra chamada LLM dedicada a embalar a resposta (ex.: blocos JSON para UI).
- **`_run_f3_pipeline`** — verificador numérico contra digest, compositor de layout; o Maestro **salta** esta pipeline (devolve o resultado directamente).

Isto é o “director’s cut” depois do actor principal ter falado.

---

## 10. Memória, observador, trace e resposta HTTP

Com `session_metadata`, o sistema pode actualizar notas de sessão e resumo de conversa (`maybe_update_session_notes`, `maybe_update_conversation_summary`). O observador opcional gera narrativas de eventos. O trace grava `trace_run_id` no payload.

No `finally` de `run`, remove-se `_orch_anchor` das mensagens, limpa-se metadata temporária do retrieve, e faz-se última poda.

`process_chat` separa texto markdown de blocos estruturados (`split_reply_and_blocks`) e devolve JSON ao cliente. Persistência: `replace_conversation_messages` grava o transcript completo (Maestro + especialistas).

---

## 11. O guardião silencioso: sanitização OpenAI

Antes de `chat.completions.create`, `sanitize_openai_chat_messages` (em `ai_provider/openai_chat_sanitize.py`) garante que não há mensagens `tool` órfãs nem `tool_calls` vazios — a API quebra se a cadeia assistant→tool não for válida. É o **enquadramento técnico** para o drama das múltiplas voltas tool não corromper o protocolo.

---

### Síntese em uma frase

**Do browser ao utilizador outra vez:** HTTP → sessão → mensagem com âncora → Maestro com **uma** tool virtual de roteamento → troca de SKILL e histórico limpo → (opcional) **retrieve semântico** via MCP → loop LLM↔**tools MCP/cache/aggregate virtuais** sob poda TTL+token → (opcional) crítica, formatador, pipeline F3 → memória/trace → JSON de resposta.

---

Se quiseres no **formato JSON** completo da skill (`agente_id`, `notas_de_estilo`, `scores`, etc.), diz e eu monto o payload; em Ask mode não altero ficheiros. Para eu **ajustar** a narrativa a um agente concreto (por exemplo só `analise_os`) ou a valores reais das tuas env vars, também posso detalhar em cima disso.