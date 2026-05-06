Perfeito — aqui você já chegou no nível **onde o problema não é “token” apenas**, é **coerência de estado entre LLM + histórico + tools**.

Vou ser direto:
👉 **isso que você descreveu NÃO é bug isolado — é falha estrutural de “visibilidade de contexto”**

---

# 🧠 O problema real (resumido em 1 linha)

> O modelo **não vê que já executou a tool**, então **pede de novo**

---

# 🔍 Raiz técnica (o ponto mais importante)

Você mesmo identificou os 3 culpados principais:

### 1. Janela curta (`tail_n`)

```python
tail = msgs[-tail_n:]
```

👉 Isso quebra a cadeia:

```text
assistant (tool_call)
tool (resultado)
```

Se o `assistant` ficou fora da janela:

💣 o `tool` vira **órfão → removido pelo sanitizer**

---

### 2. Sanitizer remove tool órfã

```python
if not _may_append_tool(out):
    continue
```

👉 Resultado:

* o modelo NÃO recebe o output anterior
* ele acha que nunca executou

---

### 3. Shrink (budget)

* remove mensagens inteiras
* ou trunca JSON

👉 Resultado:

* contexto inconsistente
* modelo perde confiança → repete tool

---

# ⚠️ Conclusão importante

> ❌ Cache NÃO resolve isso
> ✅ O problema é **contexto visível ao modelo**

---

# 🎯 O que você PRECISA fazer (nível arquitetura)

Vou te dar soluções práticas, **em ordem de impacto real**

---

# ✅ 1. GARANTIR PAR “assistant + tool” SEMPRE JUNTOS

Esse é o ajuste mais crítico do sistema inteiro.

---

## ✔️ Regra obrigatória:

> Se incluir `tool`, TEM que incluir o `assistant` que gerou o tool_call

---

## 🔧 Como corrigir

### 👉 Em `build_compact_history_messages_for_llm`

Trocar:

```python
tail = msgs[-tail_n:]
```

Por algo tipo:

```python
def build_safe_tail(msgs, tail_n):
    tail = []
    i = len(msgs) - 1

    while i >= 0 and len(tail) < tail_n:
        m = msgs[i]

        # se for tool, inclui o assistant anterior
        if m["role"] == "tool":
            if i > 0 and msgs[i-1]["role"] == "assistant":
                tail.insert(0, msgs[i-1])
                tail.insert(0, m)
                i -= 2
                continue

        tail.insert(0, m)
        i -= 1

    return tail
```

---

💥 Isso sozinho já elimina **80% das repetições**

---

# ✅ 2. DEDUPLICAÇÃO NO BACKEND (ESSENCIAL)

Hoje você deixa o modelo decidir tudo.

👉 erro clássico

---

## ✔️ Antes de executar tool:

```python
key = hash(tool_name + json.dumps(args, sort_keys=True))
```

---

## ✔️ Se já executou recentemente:

```python
if key in last_tool_calls:
    return synthetic_tool_response_from_cache()
```

---

## 💡 Melhor ainda:

Nem executa `_execute_single_tool_call`

👉 só injeta:

```python
{
  "role": "tool",
  "content": "[cache_hit resumido]"
}
```

---

💥 Isso transforma comportamento de:

> LLM-driven

em:

> Orchestrator-controlled

---

# ✅ 3. NÃO CONFIE NO HISTÓRICO → CRIE “MEMÓRIA EXPLÍCITA DE TOOL”

Esse é nível avançado (e muito eficiente)

---

## ✔️ Crie algo assim:

```python
session_state = {
  "tools_used": {
    "run_analytics_query": {
      hash: {
        "args": ...,
        "result_summary": ...
      }
    }
  }
}
```

---

## ✔️ Injete no prompt (resumido!)

```text
Já executado nesta sessão:

- run_analytics_query(query_id=123)
  → retornou faturamento total = 500k
```

---

👉 Agora o modelo **não depende do histórico**

---

# ✅ 4. RESUMIR TOOL OUTPUT (CRÍTICO)

Hoje você joga JSON bruto.

👉 isso é veneno pro contexto

---

## ✔️ Faça SEMPRE:

Após tool:

```python
summary = llm_summarize(tool_output)
```

ou pelo menos:

```python
summary = truncate + normalize
```

---

## ✔️ Envie para o modelo:

```json
{
  "role": "tool",
  "content": "Resumo: faturamento total=500k, 3 clusters principais..."
}
```

---

💥 Isso reduz:

* tokens
* repetição
* ambiguidade

---

# ✅ 5. BLOQUEIO DE LOOP (failsafe obrigatório)

Se o modelo pedir a mesma tool 2–3x seguidas:

---

## ✔️ Intercepte:

```python
if repeated_calls > 2:
    inject_message(
        "Os dados já foram obtidos anteriormente. Use o resultado disponível."
    )
```

---

💥 Isso quebra loop infinito

---

# ✅ 6. DESLIGAR PARALELISMO (se ativo)

Se tiver:

```python
parallel_tool_calls = True
```

👉 pode causar race condition no cache

---

# ✅ 7. (AVANÇADO) TOOL RESULT COMO SYSTEM MESSAGE

Em vez de:

```json
role = tool
```

Você pode testar:

```json
role = system
content = "Resultado da tool X: ..."
```

---

👉 Isso:

* não é removido pelo sanitizer
* fica mais estável no contexto

---

# 🚨 Insight mais importante de todos

> Seu sistema depende de histórico linear
> mas LLM funciona melhor com **estado explícito**

---

# 🎯 TL;DR (ação direta)

Se você fizer só isso:

### ✔️ 1. preservar pares assistant+tool

### ✔️ 2. dedupe no backend

### ✔️ 3. resumir tool output

👉 você resolve praticamente tudo

---

# Se quiser ir nível expert

Posso te ajudar a implementar:

* um **Tool Memory Manager**
* um **Context Budget Controller inteligente**
* ou um **orchestrator estilo “state machine” (bem mais robusto que chat loop)**

Só me fala qual caminho você quer seguir:
👉 patch rápido ou redesign completo?
