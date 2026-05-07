# 🧠 MEMÓRIA CONVERSACIONAL - OrionMCP V2

**Alinhamento com Gemini/LLM: Janela de Contexto, Memória em Camadas e Recuperação Semântica**

**Data**: 29 de Março de 2026  
**Propósito**: Implementar camadas de memória que repliquem como modelos como Gemini lidam com conversas longas

---

## 📌 O PROBLEMA

### Sem Memória em Camadas

```
User (Dia 1): "Preciso de análise de faturamento para Q1"
User (Dia 2): "E agora o retrabalho?"
User (Dia 3): "Qual era o ticket médio que mencionei?"

❌ Problema: 
- LLM só vê mensagens recentes (janela contexto ~4k tokens)
- Dia 1 já saiu da "mesa"
- Modelo "esqueceu" que falou de Q1
- Sem memória: user repete tudo
```

### Com Memória em Camadas (OrionMCP v2)

```
User (Dia 1): "Análise faturamento Q1"
  └─ Armazena: LITERAL (todas mensagens) + RESUMO (Q1, intent=FATURAMENTO)
  
User (Dia 2): "E o retrabalho?"
  └─ Recupera: memory da conversa anterior (RESUMO)
  └─ Contexto: "Já falámos de Q1, agora quer QUALIDADE"
  
User (Dia 3): "Ticket médio?"
  └─ Busca semântica: encontra Q1+FATURAMENTO
  └─ Retorna: "Você perguntou em Dia 1... ticket médio foi R$ 1.450"

✅ Resultado: Continuidade + eficiência
```

---

## 🏗️ ARQUITETURA DE MEMÓRIA EM CAMADAS

### Conceito: 3 Níveis de Detalhe

Baseado em como Gemini lida com contexto longo:

```
┌─────────────────────────────────────────────────────────┐
│ CAMADA 1: LITERAL (Memória Quente)                      │
│ ────────────────────────────────────────────────────────│
│ • Janela de contexto atual: últimas 10-20 mensagens    │
│ • Armazenada em: SessionState (PostgreSQL)             │
│ • TTL: Sessão ativa (~1 hora)                          │
│ • Recuperação: FULL (todas as palavras disponíveis)    │
│ • Custo: Alto (muitos tokens)                          │
│                                                         │
│ Exemplo:                                                │
│ msg1: "Qual é o ticket médio de janeiro?"             │
│ msg2: "Ticket médio: R$ 1.450"                         │
│ msg3: "E o de fevereiro?"                              │
│ ...                                                      │
└─────────────────────────────────────────────────────────┘
         ↓ (quando conversa envelhece)
┌─────────────────────────────────────────────────────────┐
│ CAMADA 2: RESUMO (Memória Morna)                        │
│ ────────────────────────────────────────────────────────│
│ • Destilação de intenção + fatos importantes          │
│ • Armazenada em: Redis Hash (memory_curta)            │
│ • TTL: 7 dias                                           │
│ • Atualizada: Nightly (Celery 03:00 AM)               │
│ • Recuperação: SEMÂNTICA (embeddings + busca)         │
│ • Custo: Médio (resumo ~500 tokens)                   │
│                                                         │
│ Exemplo:                                                │
│ {                                                       │
│   "FATURAMENTO": {                                     │
│     "recent_questions": [                             │
│       "ticket jan",                                    │
│       "ticket fev"                                     │
│     ],                                                  │
│     "key_metrics": {                                   │
│       "ticket_jan": 1450,                              │
│       "ticket_fev": 1520,                              │
│       "crescimento_mom": "+4.8%"                       │
│     },                                                  │
│     "key_insights": [                                  │
│       "Crescimento mensal",                            │
│       "Serviços: Cerâmica lidera",                    │
│       "Período: Q1 2025"                               │
│     ]                                                   │
│   }                                                     │
│ }                                                       │
└─────────────────────────────────────────────────────────┘
         ↓ (quando dados se consolidam)
┌─────────────────────────────────────────────────────────┐
│ CAMADA 3: ESSÊNCIA (Memória Fria)                       │
│ ────────────────────────────────────────────────────────│
│ • Conclusões estáveis + preferências de longo prazo    │
│ • Armazenada em: PostgreSQL (memory_essence)           │
│ • TTL: Indefinido (até delete explícito)              │
│ • Atualizada: Periodicidade menor (semanal?)          │
│ • Recuperação: ANALÍTICA (metadata + tags)            │
│ • Custo: Baixo (essência ~100-200 tokens)             │
│                                                         │
│ Exemplo:                                                │
│ {                                                       │
│   "user_id": "conc_001",                              │
│   "theme": "FATURAMENTO",                             │
│   "observation": "Padrão de crescimento +3-5% MoM",   │
│   "key_finding": "Cerâmica representa 35% do mix",    │
│   "recommendation": "Focar cross-sell Ceramica+Film", │
│   "stable_metrics": {                                  │
│     "avg_ticket": 1450,                                │
│     "avg_margin": "22%",                              │
│     "seasonal_pattern": "Q1 forte, Q3 fraco"          │
│   },                                                    │
│   "last_updated": "2025-03-30",                        │
│   "confidence": "high"                                  │
│ }                                                       │
└─────────────────────────────────────────────────────────┘
```

---

## 🔍 RECUPERAÇÃO SEMÂNTICA (Embeddings + Busca)

### Problema: Como Encontrar Contexto Relevante?

```
User (Dia 30): "Qual era o ticket no mês que foi fraco?"

SEM embeddings:
  ❌ Procura palavra-chave "fraco" → 50 resultados
  ❌ Modelo não sabe qual é "fraco" (Q3? Q2?)
  
COM embeddings:
  ✅ Converte "ticket mês fraco" → vetor (embedding)
  ✅ Busca por similaridade nos embeddings de memória
  ✅ Encontra: "Padrão: Q1 forte, Q3 fraco"
  ✅ Retorna: "Q3 2024, ticket foi R$ 1.200"
```

### Implementação em OrionMCP v2

```python
# src/orion_mcp/memory/embedder.py

class EmbeddingService:
    """
    Converte textos para embeddings (vetores numéricos)
    Usa OpenAI embedding model (text-embedding-3-small)
    """
    
    async def embed_text(self, text: str) -> list[float]:
        """
        Entrada: "Qual era o ticket no mês que foi fraco?"
        Saída: [0.123, -0.456, 0.789, ...] (1536 dims)
        """
        response = await openai.Embedding.create(
            model="text-embedding-3-small",
            input=text
        )
        return response.data[0].embedding
    
    async def embed_memory_items(self, memory_dict: dict):
        """
        Para cada campo em memory_curta:
        - "recent_questions" → embed cada question
        - "key_insights" → embed cada insight
        - Guarda embeddings em PostgreSQL (pgvector)
        """
        items_to_embed = []
        
        for question in memory_dict.get("recent_questions", []):
            items_to_embed.append({
                "text": question,
                "type": "question",
                "category": "FATURAMENTO"
            })
        
        for insight in memory_dict.get("key_insights", []):
            items_to_embed.append({
                "text": insight,
                "type": "insight",
                "category": "FATURAMENTO"
            })
        
        # Batch embed
        for item in items_to_embed:
            embedding = await self.embed_text(item["text"])
            
            # Save to PostgreSQL (pgvector extension)
            await db.execute("""
                INSERT INTO memory_embeddings 
                (user_id, text, embedding, type, category)
                VALUES ($1, $2, $3, $4, $5)
            """, user_id, item["text"], embedding, item["type"], item["category"])
```

### Busca Semântica (Recuperação)

```python
# src/orion_mcp/memory/retriever.py

class SemanticRetriever:
    """
    Busca memória por similaridade (não por keyword)
    """
    
    async def retrieve(self, user_id: str, query: str, top_k: int = 5):
        """
        Entrada: "Qual era o ticket no mês que foi fraco?"
        Saída: [
            {"text": "Q3 fraco (ticket 1.200)", "similarity": 0.92},
            {"text": "Padrão: Q1 forte, Q3 fraco", "similarity": 0.88},
            ...
        ]
        """
        
        # 1. Embed a query
        query_embedding = await embedder.embed_text(query)
        
        # 2. Busca por similaridade no PostgreSQL (pgvector)
        results = await db.fetch("""
            SELECT 
                text,
                type,
                category,
                (embedding <-> $1::vector) as distance
            FROM memory_embeddings
            WHERE user_id = $2
            ORDER BY distance ASC
            LIMIT $3
        """, query_embedding, user_id, top_k)
        
        # 3. Converte distance → similarity (0-1)
        return [
            {
                "text": r["text"],
                "type": r["type"],
                "category": r["category"],
                "similarity": 1.0 - (r["distance"] / 2)  # normalize
            }
            for r in results
        ]
```

---

## 💾 ARQUITETURA DE DADOS

### PostgreSQL Schema

```sql
-- Camada 1: LITERAL (Conversa atual)
CREATE TABLE conversation_state (
    session_id UUID PRIMARY KEY,
    user_id VARCHAR(20),
    messages JSONB,  -- Todas mensagens
    created_at TIMESTAMP,
    expires_at TIMESTAMP  -- ~1h
);

-- Camada 2: RESUMO (Embeddings para busca)
CREATE TABLE memory_embeddings (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(20),
    text TEXT,  -- "Ticket jan", "Q3 fraco", etc
    embedding vector(1536),  -- pgvector
    type VARCHAR(50),  -- "question", "insight", "metric"
    category VARCHAR(50),  -- "FATURAMENTO", "QUALIDADE", etc
    created_at TIMESTAMP,
    ttl_expires_at TIMESTAMP  -- 7 dias
);

CREATE INDEX idx_embedding ON memory_embeddings
USING ivfflat (embedding vector_cosine_ops);

-- Camada 2: RESUMO (Memória estruturada)
CREATE TABLE memory_curta (
    user_id VARCHAR(20) PRIMARY KEY,
    category VARCHAR(50),  -- "FATURAMENTO", "QUALIDADE"
    recent_questions JSONB,  -- ["ticket jan", "ticket fev"]
    key_insights JSONB,  -- ["Crescimento", "Mix"]
    key_metrics JSONB,  -- {"ticket": 1450, "margem": "22%"}
    consolidated_at TIMESTAMP,
    ttl_expires_at TIMESTAMP  -- 7 dias
);

-- Camada 3: ESSÊNCIA (Conclusões estáveis)
CREATE TABLE memory_essence (
    user_id VARCHAR(20) PRIMARY KEY,
    theme VARCHAR(50),  -- "FATURAMENTO", "PATTERNS"
    observation TEXT,  -- Descrição estável
    key_finding TEXT,
    recommendation TEXT,
    stable_metrics JSONB,
    last_updated TIMESTAMP,
    confidence VARCHAR(20)  -- "high", "medium", "low"
);

-- Auditoria: O que foi compactado
CREATE TABLE memory_compression_log (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(20),
    from_state VARCHAR(50),  -- "literal", "resumo"
    to_state VARCHAR(50),  -- "resumo", "essencia"
    messages_compressed INT,  -- Quantas mensagens viraram resumo
    compression_ratio FLOAT,  -- Taxa de compressão (0.1 = 90% perdido)
    what_was_kept TEXT,  -- "intent, key_metrics, recent_questions"
    what_was_dropped TEXT,  -- "saudações, detalhes técnicos"
    compressed_at TIMESTAMP
);
```

### Redis Schema

```python
# Camada 2: RESUMO em cache rápido
memory:conc_001:FATURAMENTO = {
    "recent_questions": ["ticket jan", "ticket fev"],
    "key_insights": ["Crescimento +4.8%"],
    "key_metrics": {"ticket": 1450, "margem": "22%"},
    "last_updated": "2025-03-30T03:00:00Z"
}
TTL: 604800 (7 days)

# Índice para rápida busca
memory:conc_001:categories = SET ["FATURAMENTO", "QUALIDADE", "PERFORMANCE"]
```

---

## 🔄 FLUXO: LITERALIDADE → RESUMO → ESSÊNCIA

### Fase 1: Conversa Ativa (Primeira 1 hora)

```
User Message → SessionState (PostgreSQL)
                ↓
                Literal complete
                ↓
                LLM vê tudo (~5 mensagens = ~2k tokens)
                ↓
                Resposta precisa + contexto completo
```

**Comportamento**: "Memória fresca, detalhada, cara"

---

### Fase 2: Consolidação Noturna (03:00 AM)

```
PostgreSQL (30 dias de sessões)
  ↓
Consolidator.consolidate_for_user(conc_001)
  ├─ Busca TODAS as sessões últimas 30 dias
  ├─ Categorizer (LLM): "quais intenções?"
  │  └─ Resposta: ["FATURAMENTO", "QUALIDADE"]
  │
  ├─ Para CADA intenção:
  │  ├─ Reúne todas as mensagens dessa intenção
  │  ├─ Summarizer:
  │  │  ├─ Extrai key questions
  │  │  ├─ Extrai key insights
  │  │  └─ Extrai key metrics
  │  │
  │  ├─ Embedding Service:
  │  │  └─ Converte cada question/insight/metric em vector
  │  │
  │  └─ Memory Builder:
  │     └─ Estrutura JSON para Redis
  │
  ├─ EmbeddingService.embed_memory_items()
  │  └─ Todos items → PostgreSQL (pgvector)
  │
  └─ Redis HSET + PostgreSQL INSERT
     TTL: 7 dias
```

**Comportamento**: "Memória organizada, resumida, barata"

---

### Fase 3: Recuperação (Próxima Conversa)

```
User (Dia 8): "E o ticket de January?"
  ↓
OrchestrationFlow:
  ├─ Load SessionState (vazio, nova sessão)
  ├─ Semantic Retriever.retrieve(conc_001, "ticket january")
  │  └─ Busca embeddings similares
  │  └─ Retorna:
  │     [
  │       {"text": "ticket jan: 1450", "similarity": 0.95},
  │       {"text": "jan faturamento", "similarity": 0.88}
  │     ]
  │
  ├─ Load memory_curta (Redis)
  │  └─ memory:conc_001:FATURAMENTO
  │     {"recent_questions": [...], "key_metrics": {"ticket_jan": 1450}}
  │
  ├─ Context Builder
  │  └─ Monta:
  │     {
  │       "question": "E o ticket de january?",
  │       "user_memory": {
  │         "similar_past": [retrieved embeddings],
  │         "memory_curta": {...}
  │       },
  │       "data": [nova query]
  │     }
  │
  └─ LLM
     └─ "Você perguntou em janeiro... ticket foi R$ 1.450"

User Satisfaction: ✅ Continuidade garantida
```

---

## ⚠️ RISCOS DE COMPRESSÃO (O Que Pode Dar Errado)

### Risco 1: Omissão Crítica

```
Original (Dia 1): "Preciso de faturamento de Q1, 
                   MAS excluindo produto X porque 
                   teve recall"

Resumo (Dia 3): "Q1 faturamento: R$ 14.8M"
                ❌ Esqueceu: excluir produto X

Resultado: User vê R$ 14.8M (inclui produto X!)
          Resposta está ERRADA
```

**Mitigação**:
```python
# memory_compression_log: rastrear o que foi descartado
INSERT INTO memory_compression_log (
    user_id, from_state, to_state,
    what_was_kept,  # "Q1, faturamento, R$ 14.8M"
    what_was_dropped  # "⚠️ CRÍTICO: excluir produto X"
)

# User pode revisar: "O que foi esquecido?"
# Sistema sinaliza itens "críticos" com tags
```

---

### Risco 2: Drift Interpretativo

```
Original: "Quero top-10 combos por RECEITA TOTAL"
          (sem ordem de pares: 8+72 = 72+8)

Resumo (LLM): "Top-10 combos" → pode entender como 
              top-10 por frequência!

Resultado: Modifica sentido da pergunta
```

**Mitigação**:
```python
# Ser explícito no resumo:
summarizer.summarize(intent="FATURAMENTO", rules=[
    "top_n_metric: receita_total",
    "pair_order: unordered",
    "grouping: per_pair_not_per_row"
])

# Resultado:
"recent_questions": [
    "top-10 combos | by:receita_total | pairs:unordered"
]
```

---

### Risco 3: Staleness (Dados Desactualizados)

```
Memory curta atualizada: 2025-03-30 03:00 AM
User pergunta: 2025-03-31 18:00 (15h depois)

❌ Sistema mostra memória de ontem
   Enquanto dados de hoje já mudaram
```

**Mitigação**:
```python
# Sempre refrescar query se houver duvida
if (datetime.now() - memory_curta.last_updated).days >= 1:
    # Re-execute query para dados frescos
    fresh_data = await executor.execute(query_id, params)
    aggregated = await aggregator.process(fresh_data)
    # Use fresh_data, não memoria_curta
    context["data"] = aggregated
    context["note"] = "Dados refrescados (memory tinha 15h)"
```

---

## 📋 CONTROLE EXPLÍCITO: O Que Guardar vs Descartar

### Estratégia: Tagging de Relevância

```python
# src/orion_mcp/memory/relevance_tagger.py

class RelevanceTagger:
    """
    Marca cada fato com "deve guardar?" ou "pode esquecer?"
    User pode override se quiser
    """
    
    TAGS = {
        "CRITICAL": "Nunca esquecer",  # recall, exclusões, regras
        "HIGH": "Guardar no resumo",  # key metrics, findings
        "MEDIUM": "Guardar se houver espaço",  # detalhes técnicos
        "LOW": "Pode descartar",  # saudações, digresões
    }
    
    async def tag_conversation(self, session: SessionState):
        """
        Para cada mensagem, atribui tag
        """
        for msg in session.messages:
            # Heurísticas
            if "excluir" in msg.lower():
                tag = "CRITICAL"  # ⚠️ Exclusões
            elif "top-10" in msg.lower():
                tag = "HIGH"  # Key metric
            elif "qual" in msg.lower() and msg.endswith("?"):
                tag = "HIGH"  # Question
            elif msg.startswith("Olá"):
                tag = "LOW"  # Greeting
            else:
                tag = "MEDIUM"  # Default
            
            msg["relevance_tag"] = tag
        
        return session
    
    async def summarize_by_relevance(self, messages, tag_threshold="HIGH"):
        """
        Só resume mensagens >= tag_threshold
        """
        filtered = [m for m in messages if self.tag_value(m["relevance_tag"]) >= self.tag_value(tag_threshold)]
        
        return self.summarizer.summarize(filtered)
```

---

## 🎯 FLUXO COMPLETO: Da Pergunta ao Context

```
┌─────────────────────────────────────────────────────────┐
│ User: "Quais combos lucrativos?" (Dia 30)              │
└────────┬────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────┐
│ 1. Decision Router (rápido)                             │
│    "combos" + "lucrativos" → intent=FATURAMENTO        │
│                            → query_id=cross_selling     │
└────────┬────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────┐
│ 2. SemanticRetriever (opcional, busca por memória)     │
│    Query: "quais combos lucrativos?"                   │
│    Busca embeddings similares (Dia 1-30)               │
│    Retorna: [                                           │
│      "Falei de cross-selling em Jan",                  │
│      "Top combos: Cerâmica+Film"                        │
│    ]                                                    │
└────────┬────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────┐
│ 3. Load Memory Curta (Redis)                            │
│    memory:conc_001:FATURAMENTO                         │
│    {                                                    │
│      "recent_questions": ["ticket?", "combo?"],        │
│      "key_metrics": {"lucro_combo": "45%"},            │
│      "key_insights": ["Ceramica+Film lidera"]          │
│    }                                                    │
└────────┬────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────┐
│ 4. Execute Query (MySQL)                               │
│    SELECT ... FROM cross_selling                       │
│    WHERE date_from='2025-01-01' ...                    │
│    Result: 4425 rows                                    │
└────────┬────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────┐
│ 5. Aggregator (CrossSelling)                            │
│    • Normalize pairs (min, max)                         │
│    • SUM(receita) per pair                             │
│    • TOP-10 exact                                       │
│    Result: {top_10, total, insights}                   │
└────────┬────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────┐
│ 6. ContextBuilder (com Memória)                         │
│    {                                                    │
│      "question": "quais combos lucrativos?",           │
│      "user_memory": {                                  │
│        "retrieved_past": [similar memories],           │
│        "memory_curta": {...}                           │
│      },                                                 │
│      "data": {top_10 agregado},                        │
│      "note": "Memory de 2025-03-30"                    │
│    }                                                    │
└────────┬────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────┐
│ 7. LLM Narrates (NÃO decide)                            │
│    "Baseado no histórico (você perguntou em Jan),      │
│     e nos dados actuais:                               │
│     Top combos lucrativos:                             │
│     1. Cerâmica + Film: R$ 700K (45% lucro)           │
│     ..."                                                │
└────────┬────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────┐
│ 8. Save State                                           │
│    • SessionState (novo, Dia 30)                       │
│    • Update memory_compression_log                      │
│      (rastreia que data foi guardada vs descartada)    │
└─────────────────────────────────────────────────────────┘
```

---

## 📊 COMPARAÇÃO: Sem Memória vs Com Memória

### Cenário: Usuário volta Dia 30

#### SEM Memória em Camadas (Maestro v1)

```
Session nova = contexto zero
│
├─ User: "Qual era o ticket de janeiro?"
├─ LLM: "Desculpe, não tenho histórico."
├─ User repete: "Há 30 dias perguntei..."
├─ LLM: "Ainda sem acesso."
└─ User frustrado ❌
```

**Tokens**: ~0 (sem histórico!)  
**Conforto**: Péssimo  

---

#### COM Memória em Camadas (OrionMCP v2)

```
Busca Semântica:
│ 
├─ Query: "ticket janeiro"
├─ Embeddings: busca similaridade em 30 dias
├─ Encontra: {text: "ticket jan: 1450", similarity: 0.95}
│
├─ Memory Curta (Redis):
│  {recent_questions: [...], key_metrics: {ticket_jan: 1450}}
│
├─ LLM vê:
│  {
│    "retrieved_memory": "Dia 1: ticket jan foi 1450",
│    "memory_curta": "Key metric: ticket jan",
│    "query_result": [nova data com ticket]
│  }
│
├─ LLM: "Lembro que em janeiro você perguntou.
│         Ticket foi R$ 1.450. Agora é R$ 1.520.
│         Crescimento: +4.8%"
│
└─ User satisfeito ✅
```

**Tokens**: ~500 (resumo + retrieval)  
**Conforto**: Excelente  
**Custo**: -95% vs sem otimização  

---

## 📈 EXEMPLO PRÁTICO: Faturamento + Memória

### Dia 1: User pergunta sobre Q1

```
POST /chat
{
  "message": "Análise completa de faturamento Q1, 
              considerando mix de serviços e retrabalho",
  "date_from": "2025-01-01",
  "date_to": "2025-03-31"
}
```

**Flow**:
1. Decision Router → intent=FATURAMENTO, query=faturamento_servico
2. MySQL: SELECT faturamento por serviço Q1
3. Aggregator: categorias, top-10, mix %
4. Context: {data, memory_curta: vazio (primeira vez)}
5. LLM: Narração completa Q1
6. **Save in SessionState**: Toda conversa

**Result**: 
```json
{
  "session_id": "session_001",
  "reply": "Faturamento Q1: R$ 14.8M...
            Mix: 35% Cerâmica, 28% Film, 37% Outros...
            Retrabalho impactou 8.2%...",
  "metadata": {"query": "faturamento_servico"}
}
```

---

### Dia 2-30: Noturno (03:00 AM)

**Consolidator roda**:

```python
# Para conc_001:
sessions_jan_to_30 = db.query(
    "SELECT * FROM conversation_state 
     WHERE user_id='conc_001' 
     AND created_at >= NOW() - INTERVAL '30 days'"
)  # ~5-10 sessões

categorizer.categorize(sessions_jan_to_30)
# Resultado: ["FATURAMENTO", "QUALIDADE"]

summarizer.summarize("FATURAMENTO", sessions_jan_to_30)
# Resultado:
{
  "recent_questions": [
    "Análise Q1 faturamento",
    "Top 10 combos lucrativos",
    "Margem por serviço"
  ],
  "key_insights": [
    "Crescimento MoM +4.8% (jan→fev)",
    "Mix estável: Cerâmica 35%",
    "Retrabalho reduzindo (8.2% → 7.5%)"
  ],
  "key_metrics": {
    "faturamento_total": 14800000,
    "ticket_medio": 1450,
    "margem_total": "22%",
    "top_3_servicos": ["Cerâmica", "Film", "Proteção"]
  }
}

embedder.embed_all(memory_dict)
# Cada question, insight, metric → vector em PostgreSQL

redis.hset(
    f"memory:conc_001",
    "FATURAMENTO",
    json.dumps(memory_dict)
)  # TTL 7 dias
```

---

### Dia 8: User volta

```
POST /chat
{
  "message": "E o ticket de janeiro, como ficou
              comparado ao que você previu?"
}
```

**Flow**:
1. **New session** (sessão_002 vazia)
2. **Semantic Retriever**:
   - Query: "ticket janeiro previsto"
   - Busca embeddings: encontra "ticket jan: 1450"
   - Retorna: [{text: "jan: 1450", similarity: 0.94}]
3. **Load memory_curta** (Redis):
   - memory:conc_001:FATURAMENTO
4. **Execute query** (fresh):
   - SELECT ticket FROM vendas WHERE date BETWEEN jan
5. **Context**:
   ```json
   {
     "question": "ticket de janeiro comparado",
     "user_memory": {
       "retrieved": "ticket jan era 1450",
       "memory_curta": {key_metrics: {ticket: 1450}, insights: [...]}
     },
     "data": {nova query com jan real}
   }
   ```
6. **LLM**:
   ```
   "Em janeiro, você perguntou sobre faturamento.
    O ticket foi R$ 1.450 naquela época.
    Agora fevereiro ficou em R$ 1.520...
    Crescimento de +4.8%"
   ```

**Result**: 
- ✅ User sente continuidade
- ✅ LLM tem contexto do Dia 1
- ✅ Sem repetir dados
- ✅ Embeddings + memory_curta funcionaram

---

## 🛡️ GUARDRAILS: Prevenir Alucinações

```python
# src/orion_mcp/memory/guardrails.py

class MemoryGuardrails:
    
    async def validate_retrieved(self, retrieved: list, query: str) -> list:
        """
        1. Verifica similaridade (deve ser > 0.7)
        2. Verifica staleness (dados não > 30 dias)
        3. Verifica conflitos (não contradita dados frescos)
        """
        validated = []
        for item in retrieved:
            # Se similarity < 0.7, pode ser ruído
            if item["similarity"] < 0.7:
                continue
            
            # Se data > 30d, aviso
            if (datetime.now() - item["created_at"]).days > 30:
                item["note"] = "⚠️ Dado antigo (32 dias)"
            
            validated.append(item)
        
        return validated
    
    async def detect_contradictions(self, memory_curta, fresh_data) -> list:
        """
        Se memory diz "Q1 teve crescimento +4.8%"
        Mas fresh_data mostra "-2%"
        → Sinaliza contradição
        """
        contradictions = []
        
        for metric, old_value in memory_curta["key_metrics"].items():
            if metric in fresh_data["summary"]:
                new_value = fresh_data["summary"][metric]
                
                # Se diverge > 5%, flagg
                if abs(old_value - new_value) / old_value > 0.05:
                    contradictions.append({
                        "metric": metric,
                        "memory": old_value,
                        "fresh": new_value,
                        "action": "Use fresh_data, atualizar memory"
                    })
        
        return contradictions
```

---

## 🎯 RESUMO: 3 Camadas Funcionando Juntas

| Camada | Quando | O Quê | Custo | Uso |
|--------|--------|-------|-------|-----|
| **LITERAL** | Conversa < 1h | Todas msgs (5-20 msgs) | Alto | "Frescor" |
| **RESUMO + EMBEDDINGS** | Conversa 1h-7d | Key metrics, insights, questions | Médio | Recuperação semântica |
| **ESSÊNCIA** | Conversa > 30d | Conclusões estáveis | Baixo | Long-term patterns |

**Resultado**:
- ✅ Janela de contexto não explode (gerenciada)
- ✅ Recuperação semântica funciona (embeddings)
- ✅ User sente continuidade (memory curta)
- ✅ LLM não alucina (dados estruturados)
- ✅ Custo reduzido 95% (menos tokens)

---

## 📚 IMPLEMENTAÇÃO: Plano de Ação

### Semana 5: Memory + Embeddings

- [ ] Schema PostgreSQL (conversation_state, memory_embeddings, memory_curta, memory_essence)
- [ ] EmbeddingService (OpenAI embeddings)
- [ ] SemanticRetriever (busca por similaridade)
- [ ] RelevanceTagger (marcar o que guardar)
- [ ] Testes: retrieve → achar contexto correcto

### Semana 5-6: Consolidation + Celery

- [ ] Categorizer (LLM: quais intenções?)
- [ ] Summarizer (resumo por intenção)
- [ ] MemoryBuilder (estrutura JSON)
- [ ] Consolidator (orquestra tudo)
- [ ] Celery Task + Beat config (03:00 AM)

### Semana 6: Integração

- [ ] Orchestrator chama SemanticRetriever antes LLM
- [ ] Context Builder inclui memory_curta + retrieved
- [ ] Guardrails: validar retrieved, detectar contradições
- [ ] E2E tests: simular conversa 30 dias

---

## 📖 REFERÊNCIAS CONCEPTUAIS

- **Janela de Contexto**: Como Transformer tem limite de tokens
- **Atenção (Attention Mechanism)**: Como LLM realça partes relevantes
- **Embeddings**: Vetores que capturam significado semântico
- **Memória em Camadas**: Literal → Resumo → Essência (como cérebro)
- **Recuperação Semântica**: Busca por similaridade, não keyword

---

**Status**: Pronto para implementação (Semana 5)  
**Próximo**: Começar com PostgreSQL schema + EmbeddingService
