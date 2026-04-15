Perfeito. Vou te entregar um **plano de migração realista, incremental e aplicável no seu código atual**, sem exigir reescrita total — mas já te levando para um **orquestrador orientado a estado (state machine)**.

Vou estruturar como um **roadmap em fases**, com objetivos, mudanças concretas e exemplos.

---

# 🧠 VISÃO FINAL (onde você vai chegar)

Hoje:

```text
mensagens → prune → LLM → tools → repetir
```

Depois:

```text
user_input
   ↓
[state machine]
   ↓
contexto mínimo (inteligente)
   ↓
LLM / tools
   ↓
atualiza estado
```

👉 O histórico deixa de ser “fonte da verdade”
👉 O **state passa a ser**

---

# 🗺️ FASE 0 — Diagnóstico e baseline (1–2 dias)

### 🎯 Objetivo

Entender exatamente onde o token explode e onde ocorre repetição de tool.

---

## ✅ Ações

1. Logar antes da chamada LLM:

```python
log({
  "estimated_tokens": ...,
  "num_messages": len(messages),
  "tool_calls_last_5": ...
})
```

2. Logar repetição:

```python
hash = hash(tool_name + json.dumps(args, sort_keys=True))
```

3. Criar métrica:

* `% de chamadas repetidas`
* `tokens médios por request`

---

## 📌 Resultado esperado

Você terá clareza de:

* quanto vem do system
* quanto vem de tools
* onde ocorre perda de contexto

---

# 🧩 FASE 1 — Introduzir STATE (sem quebrar nada) (2–4 dias)

### 🎯 Objetivo

Criar uma camada paralela ao histórico.

---

## ✅ Criar estrutura de estado

```python
class ConversationState:
    def __init__(self):
        self.intent = None
        self.entities = {}
        self.metric = None

        self.data = {}
        self.insights = []

        self.tool_history = {}
        self.last_tool_results = {}

        self.summary = None
```

---

## ✅ Persistência

Você já tem PostgreSQL → adicione:

```sql
conversation_state JSONB
```

---

## ✅ Atualizar no fluxo

No `run()`:

```python
state = load_state(session_id)

state = update_state_from_user_input(state, user_input)
```

---

## ⚠️ Importante

👉 Nessa fase você **NÃO muda o prompt ainda**

---

## 📌 Resultado esperado

* Estado começa a existir
* Nada quebra

---

# 🧠 FASE 2 — Extrair INTENT + ENTITIES (3–5 dias)

### 🎯 Objetivo

Parar de depender do LLM “adivinhar tudo”

---

## ✅ Criar extractor

Pode começar simples:

```python
def extract_entities(user_input):
    if "faturamento" in user_input:
        return {"metric": "faturamento"}
```

Ou usar LLM:

```python
"extraia metric, período, filtros"
```

---

## ✅ Atualizar state

```python
state.metric = entities.get("metric")
state.entities.update(entities)
```

---

## 📌 Resultado esperado

* você já sabe “sobre o que é a conversa”
* começa a controlar contexto

---

# ⚙️ FASE 3 — TOOL MEMORY (CRÍTICO) (3–6 dias)

### 🎯 Objetivo

Eliminar repetição de tool

---

## ✅ Criar hash de tool

```python
def tool_key(name, args):
    return f"{name}:{json.dumps(args, sort_keys=True)}"
```

---

## ✅ Antes de executar:

```python
key = tool_key(name, args)

if key in state.tool_history:
    return cached_response
```

---

## ✅ Após executar:

```python
state.tool_history[key] = {
  "args": args,
  "summary": summarize(tool_output)
}
```

---

## 📌 Resultado esperado

* tools não repetem
* tokens caem drasticamente

---

# ✂️ FASE 4 — RESUMO DE TOOL OUTPUT (2–4 dias)

### 🎯 Objetivo

Parar de mandar JSON bruto

---

## ✅ Criar summarizer

```python
def summarize_tool_output(data):
    return {
      "faturamento_total": data["total"],
      "top_servico": ...
    }
```

ou via LLM

---

## ✅ Substituir:

ANTES:

```json
tool_output completo
```

DEPOIS:

```json
"Resumo: faturamento=500k, top serviço=X"
```

---

## 📌 Resultado esperado

* -70% tokens
* mais clareza pro LLM

---

# 🧠 FASE 5 — CONTEXT BUILDER (CORE DA MUDANÇA) (4–7 dias)

### 🎯 Objetivo

Parar de mandar histórico → mandar contexto relevante

---

## ✅ Criar builder

```python
def build_context(state, user_input):

    context = []

    if state.metric:
        context.append(f"Métrica atual: {state.metric}")

    if state.data:
        context.append(f"Resumo: {state.data['summary']}")

    if state.insights:
        context.append("Insights:")
        context.extend(state.insights[:3])

    return "\n".join(context)
```

---

## ✅ Trocar montagem de mensagens

ANTES:

```python
messages = history
```

DEPOIS:

```python
messages = [
  {"role": "system", "content": core_prompt},
  {"role": "system", "content": build_context(state, user_input)},
  {"role": "user", "content": user_input}
]
```

---

## 📌 Resultado esperado

* contexto controlado
* sem explosão de tokens

---

# 🔄 FASE 6 — DECISION ENGINE (state machine de verdade) (5–10 dias)

### 🎯 Objetivo

Parar de deixar o LLM decidir tudo

---

## ✅ Criar decisão

```python
def decide_next_action(state):

    if not state.data:
        return "CALL_TOOL"

    if state.metric and not state.insights:
        return "GENERATE_INSIGHTS"

    return "RESPOND"
```

---

## ✅ Orquestrar

```python
action = decide_next_action(state)

if action == "CALL_TOOL":
    ...
elif action == "RESPOND":
    call_llm()
```

---

## 📌 Resultado esperado

* fluxo previsível
* menos dependência do LLM

---

# 🧹 FASE 7 — REMOVER DEPENDÊNCIA DE HISTÓRICO (3–5 dias)

### 🎯 Objetivo

Parar de usar histórico como base

---

## ✅ Manter apenas:

* últimas 2–3 mensagens
* state.summary

---

## ❌ Remover:

* histórico completo
* tool messages antigas

---

## 📌 Resultado esperado

* sistema leve
* previsível

---

# 🚀 FASE 8 — OTIMIZAÇÕES AVANÇADAS

---

## 🔹 Relevance scoring

```python
score = similarity(user_input, state_piece)
```

---

## 🔹 Multi-layer state

```python
state = {
  "raw_data": ...,
  "summary": ...,
  "insights": ...
}
```

---

## 🔹 Anti-loop guard

```python
if same_tool_called_3x:
    bloquear
```

---

# 📊 RESULTADO FINAL ESPERADO

---

## Antes

* 300k tokens
* tools repetindo
* comportamento imprevisível

---

## Depois

* <20k tokens
* zero repetição
* fluxo controlado
* respostas mais inteligentes

---

# 🧠 Insight final

Você não está só “otimizando contexto”.

Você está mudando de:

> 🧱 pipeline passivo

para:

> 🧠 sistema cognitivo com memória estruturada

---

# Se quiser acelerar MUITO

Posso te entregar:

* um **esqueleto de código plugável no seu orchestrator**
* ou refatorar diretamente seus métodos (`run`, `_run_specialist_loop`, etc.)

Só me diz:

👉 quer implementação direta no seu código atual ou prefere ir evoluindo fase por fase?
