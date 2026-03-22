# 🎼 Análise de Skills — Maestro de Agentes
**Data:** 22 de Março de 2026  
**Analisador:** Skill Creator  
**Escopo:** 5 skills (agente_dados, agente_financeiro, agente_mysql, avaliador_coerencia, maestro)

---

## ✅ PONTOS FORTES DA ARQUITETURA

### 1. **Separação de Responsabilidades — Atomicidade Excelente**
Cada skill tem domínio **muito bem definido**:
- `agente_mysql`: apenas **carregamento** (não analisa)
- `agente_dados`: **estatística + qualidade** (não faz finanças)
- `agente_financeiro`: **métricas financeiras** (não faz estratégia)
- `avaliador_coerencia`: **ranqueamento imparcial** (não responde diretamente)
- `maestro`: **orquestração pura** (não executa análise)

✅ **Isso evita:** conflitos de responsabilidade, respostas redundantes, ambiguidade em invocação.

### 2. **Padrão JSON Input/Output — Consistência Forte**
```json
{
  "agente_id": "...",
  "pode_responder": boolean,
  "resposta": "...",
  "scores": {"relevancia", "completude", "confianca", "score_final"},
  "limitacoes_da_resposta": "..."
}
```
Todos os agentes seguem esse contrato. **Muito bom para:**
- Parsing automático pelo Maestro
- Comparação de scores pelo Avaliador
- Transferência de contexto entre skills

### 3. **Sistema de Scores Unificado**
Fórmula: `relevancia × 0.4 + completude × 0.3 + confiança × 0.3`
- ✅ Reproducível
- ✅ Ponderação clara
- ✅ Usado consistentemente por todos os agentes

### 4. **Modo DataFrame com 2 Fases — Arquitetura Sofisticada**
```
FASE 1 (EXTRAÇÃO)  → Define perguntas agregadas estruturadas
FASE 2 (INTERPRETAÇÃO) → Recebe agregados reais, entrega insights
```
**Benefícios:**
- Agente não precisa implementar lógica de agregação
- Separa "o que perguntar" de "como interpretar"
- Escala bem com múltiplos agentes consultando mesmos dados

### 5. **Documentação Clara com Exemplos Práticos**
Cada skill inclui:
- Template de input/output
- Exemplos de JSON
- Protocolos passo-a-passo
- Casos especiais (ex: coluna `cancelado`)

---

## ⚠️ INCONSISTÊNCIAS E GAPS ENCONTRADOS

### 1. **GAP: Skill `agente_mysql` — Falta Clareza sobre Múltiplas Tabelas**

**Problema:**
```md
- **Limitações — este agente NÃO faz:**
  - Queries complexas com JOIN entre múltiplas tabelas (escopo: 1 tabela por invocação)
```

Mas no contexto de Maestro, frequentemente você precisa de:
```
SELECT os.id, concessionaria.nome, SUM(os.valor)
FROM ordem_servico os
LEFT JOIN concessionaria c ON os.concessionaria_id = c.id
GROUP BY concessionaria.nome
```

**Recomendação:**
Adicionar suporte a **carregamento com prefetch de related tables** através de um novo conceito: `DefinicaoTabela` (que você já mencionou em memory!)

```yaml
nome: agente_mysql_v2
...
description: >
  ...operação adicional: carregar tabela principal com LEFT JOIN 
  automático para tabelas relacionadas baseado em foreign keys.
```

**Implementação sugerida:**
```json
{
  "tabela_principal": "ordem_servico",
  "juntar_com": [
    {
      "tabela": "concessionaria",
      "on": "order_servico.concessionaria_id = concessionaria.id",
      "modo": "LEFT"
    }
  ],
  "limite": 50000
}
```

---

### 2. **INCONSISTÊNCIA: Nomes de Colunas — `cancelado` vs `cancelada`**

Ambos `agente_dados` e `agente_financeiro` mencionam:
```
(usar o nome da coluna que existir: `cancelado` ou `cancelada`)
```

**Problema:** Isso é frágil. Não há validação.

**Recomendação:**
Centralizar essa **detecção em `agente_mysql`** e reportar ao Maestro:

```json
{
  "metadados": {
    "coluna_cancelamento": "cancelada",  // ← agente_mysql detecta
    "eh_booleana": true,
    "valor_cancelado": 1
  }
}
```

Então `agente_dados` recebe:
```json
{
  "coluna_cancelamento_detectada": "cancelada"
}
```

---

### 3. **MISSING BEHAVIOR: Como o Maestro Retorna Respostas Excluídas?**

No `avaliador_coerencia`:
```json
{
  "respostas_excluidas": [],
  ...
}
```

Mas na entrega ao usuário, `maestro` apenas diz:
```
ℹ️ Agentes não qualificados: [nome — motivo], se houver
```

**Problema:** Usuário não sabe *por quê* uma resposta foi excluída. Apenas sabe que foi.

**Recomendação:**
Maestro deve incluir **detalhes de exclusão**:
```
ℹ️ Agentes não qualificados:
  • agente_juridico — Score 0.42 (abaixo do threshold 0.65). 
    Motivo: Pergunta era sobre análise de dados, fora do escopo jurídico.
```

---

### 4. **AMBIGUIDADE: Quando `agente_mysql` Retorna `pode_responder: false`**

Cenários não cobertos:
- ❓ Tabela não existe — o que retornar em `metadados`?
- ❓ Conexão falha — quantas tentativas?
- ❓ Limite de linhas excedido — carregar parcial ou erro?

**Recomendação:**
Adicionar seção **Error Handling** ao `agente_mysql`:

```markdown
## Tratamento de Erros

| Cenário | pode_responder | resposta | metadados |
|---------|---|---|---|
| Tabela não existe | false | "Tabela XYZ não encontrada no schema" | {"erro": "TABLE_NOT_FOUND"} |
| Conexão falha | false | "Falha ao conectar. Verifique credenciais." | {"erro": "CONNECTION_ERROR"} |
| Limite excedido | true | "Carregadas X linhas de Y totais" | {"linhas_carregadas": X, "linhas_totais": Y} |
| Schema vazio | true | "Tabela existe mas 0 linhas" | {"linhas_totais": 0} |
```

---

### 5. **FALTA DE VALIDAÇÃO: Payload Format Checking**

Nenhum agente valida se o payload recebido está no formato correto.

**Exemplo problema:**
```python
# Isso não é validado
payload = {
  "fase": "extracao",
  "df_variavel": "df_vendas"
  # ⚠️ Faltam df_info, df_colunas, df_amostra_sanitizada, df_perfil
}
```

**Recomendação:**
Adicionar **Protocol Validation** (pydantic-like) em cada agente:

```markdown
## Validação de Payload

**FASE 1 (extração):**
```python
assert "fase" in payload and payload["fase"] == "extracao"
assert "df_variavel" in payload  # obrigatório
assert "df_info" in payload      # obrigatório
assert "pergunta" in payload     # obrigatório

# Se algum falhar:
return {
  "pode_responder": false,
  "justificativa_viabilidade": "Payload inválido. Faltam campos: df_info, df_colunas"
}
```
```

---

### 6. **INCOMPLETO: Registro de Skills no Maestro**

A tabela "Registro de Agentes" lista skills, mas **falta informação crítica**:

| Skill ID | Nome | Domínio | **FALTANDO →** | Quando Selecionar |
|--|--|--|--|--|
| agente_financeiro | ... | Finanças | `pode_responder_sem_dataframe` | ... |

**Recomendação:**
Adicionar metadados para o Maestro decidir melhor:

```markdown
| Skill ID | Nome | Domínio | Requer DataFrame? | Score Min Inclusão |
|--|--|--|--|--|
| agente_financeiro | Analista Financeiro | Finanças | Não obrigatório | 0.65 |
| agente_dados | Analista de Dados | Dados | Altamente recomendado | 0.65 |
| agente_mysql | MySQL Loader | Infraestrutura | N/A (executa antes) | N/A |
```

---

## 📐 RECOMENDAÇÕES ESTRUTURAIS

### Recomendação #1: Criar `agente_orquestrador_dados`

Sua memória menciona "operações com LEFT JOIN" e "DefinicaoTabela". Essa é uma terceira responsabilidade.

**Proposta:**
- `agente_mysql` = carregar **1 tabela** com metadados simples
- **`agente_orquestrador_dados` (NEW)** = compor múltiplas tabelas com JOINs

```yaml
name: agente_orquestrador_dados
model: gpt-5-mini
description: >
  Especialista em compor e orquestrar dados de múltiplas tabelas MySQL
  usando JOIN, LEFT JOIN, e agregações entre domínios.
```

**Fluxo:**
```
Maestro
  ↓
agente_orquestrador_dados (PHASE 1: Define estratégia de JOIN)
  ↓
agente_mysql (PHASE 2: Executa carregar com LEFT JOIN)
  ↓
agente_dados / agente_financeiro (PHASE 3: Analisa DataFrame unificado)
```

**Benefício:** Separa "como compor dados" de "como analisar dados".

---

### Recomendação #2: Criar `contrato_de_skill.md`

Toda skill deveria validar seu contrato de entrada/saída.

**Arquivo novo:**
```markdown
# Contrato de Skill

## Schema de Input

Todas as skills recebem:
```json
{
  "pergunta": "string (obrigatório)",
  "contexto_maestro": "string (opcional)",
  "tipo_resposta_esperada": "factual | analítica | técnica | criativa | comparativa"
}
```

## Schema de Output

Todas as skills retornam:
```json
{
  "agente_id": "string",
  "agente_nome": "string",
  "pode_responder": "boolean",
  "resposta": "string",
  "scores": {
    "relevancia": 0.0-1.0,
    "completude": 0.0-1.0,
    "confianca": 0.0-1.0,
    "score_final": 0.0-1.0
  },
  "limitacoes_da_resposta": "string"
}
```

## Validação

Usar pydantic / JSON schema para validar antes de responder.
```

---

### Recomendação #3: Versionar o Sistema de Scores

Atualmente:
```
score = relevancia × 0.4 + completude × 0.3 + confianca × 0.3
```

**Problema:** Se você mudar essa fórmula depois, respostas antigas ficam incomparáveis.

**Recomendação:**
```json
{
  "scores": {
    "relevancia": 0.9,
    "completude": 0.8,
    "confianca": 0.85,
    "score_final": 0.86
  },
  "scores_version": "1.0",  // ← NOVO
  "fórmula_usada": "relevancia × 0.4 + completude × 0.3 + confianca × 0.3"
}
```

---

### Recomendação #4: Documentar Handoff Entre Agentes

Atualmente cada agente tem:
```json
"aspectos_para_outros_agentes": "Interpretação de negócio → agente_negocios."
```

Isso é unidirecional. **Falta documentar os handoffs esperados:**

**Documento novo: `FLUXOS.md`**
```markdown
# Fluxos de Orquestração Esperados

## Fluxo A: Análise de Vendas com Qualidade de Dados

```
USER → "Como estão as vendas de abril?"
  ↓
MAESTRO (identifica: financeiro + dados)
  ↓
AGENTE_MYSQL (carrega df_ordem_servico)
  ↓
AGENTE_DADOS (FASE 1: Define perguntas de qualidade)
AGENTE_FINANCEIRO (FASE 1: Define perguntas de receita)
  ↓
[Executor de Agregações — executa ambos de verdade]
  ↓
AGENTE_DADOS (FASE 2: Interpreta qualidade)
AGENTE_FINANCEIRO (FASE 2: Interpreta receita)
  ↓
AVALIADOR_COERENCIA (ranqueia as 2 respostas)
  ↓
MAESTRO (sintetiza: "Vendas cresceram 15%, mas com XX% de nulls em campo Y")
```

## Fluxo B: Análise Comparativa (vendas vs. cancelamento)

... (similar)
```

---

### Recomendação #5: Criar Skill para Agregação de Dados

Atualmente, quem **executa** as perguntas agregadas que `agente_dados` e `agente_financeiro` definem?

**Falta implementada:** `agente_agregador` ou similar.

**Proposta:**
```yaml
name: agente_agregador
model: gpt-5-mini
description: >
  Executa perguntas estruturadas em JSON sobre um DataFrame,
  retornando dados agregados sem expor linhas individuais.
```

**Input:**
```json
{
  "perguntas_dados": [
    {"metric_id": "fat_30d", "tipo": "sum", "coluna_valor": "valor_venda_real"}
  ],
  "dataframe_variavel": "df_os_servicos"
}
```

**Output:**
```json
{
  "resultado_extracao": {
    "fat_30d": 125000.50,
    "ticket_medio_geral": 1250.00
  }
}
```

---

## 🔍 MATRIZ DE COMPLETUDE

| Aspecto | Status | Observação |
|---------|--------|-----------|
| **Separação de Responsabilidades** | ✅ Excelente | Cada skill tem domínio claro |
| **Contrato de Input/Output** | ✅ Bom | JSON padronizado |
| **Sistema de Scores** | ✅ Bom | Fórmula clara, mas sem versionamento |
| **Modo DataFrame Fase 1/2** | ✅ Sofisticado | Bem arquitetado |
| **Tratamento de Erros** | ⚠️ Incompleto | Faltam cenários específicos |
| **Validação de Payload** | ❌ Ausente | Nenhuma skill valida entrada |
| **Múltiplas Tabelas (JOIN)** | ⚠️ Limitado | agente_mysql rejeita, falta orquestrador |
| **Fluxos Documentados** | ⚠️ Incompleto | Apenas mencionado em `aspectos_para_outros_agentes` |
| **Executor de Agregações** | ❌ Ausente | Skill não existe, falta no fluxo |
| **Colisão de Colunas** | ⚠️ Frágil | `cancelado` vs `cancelada` sem validação |

---

## 🎯 ROADMAP DE MELHORIAS (Prioridade)

### **P0 — Crítico (Faça Primeiro)**
1. [ ] Adicionar **Contrato de Skill** global (validação JSON)
2. [ ] Implementar **Skill Agregador** (quem executa as perguntas?)
3. [ ] Documentar **Fluxos de Orquestração** esperados

### **P1 — Alto (Próximas Iterações)**
4. [ ] Criar **agente_orquestrador_dados** para múltiplas tabelas
5. [ ] Adicionar **Detecção de Colunas** centralizada (cancelado/cancelada)
6. [ ] Estender `agente_mysql` com **Error Handling** explícito
7. [ ] Versionamento de **Sistema de Scores**

### **P2 — Médio (Refinamento)**
8. [ ] Adicionar **Testes de Integração** entre skills
9. [ ] Documentar **Edge Cases** por skill
10. [ ] Criar **Dashboard de Rastreamento** (Maestro logs)

---

## 📊 EXEMPLO DE FLUXO CORRIGIDO

**Pergunta:** "Como estavam as vendas em março? Tem algum problema de qualidade nos dados?"

### **Hoje (com gaps):**
```
Maestro → agente_dados + agente_financeiro
  ⚠️ Problema: Ambos pedem agregações, mas ninguém as executa
  ⚠️ Problema: agente_mysql não faz JOIN (se precisar de concessionarias)
```

### **Depois (proposta):**
```
1. Maestro → agente_orquestrador_dados
   "Preciso de (ordem_servico LEFT JOIN concessionaria)"
   ← Retorna estratégia de JOIN

2. Maestro → agente_mysql
   "Carregue ordem_servico LEFT JOIN concessionaria"
   ← Retorna df_vendas_completo

3. Maestro → agente_dados (FASE 1) + agente_financeiro (FASE 1)
   Ambos retornam: perguntas_dados JSON

4. Maestro → agente_agregador
   "Execute essas 10 perguntas agregadas sobre df_vendas_completo"
   ← Retorna resultado_extracao com todos os agregados

5. Maestro → agente_dados (FASE 2) + agente_financeiro (FASE 2)
   "Aqui estão os dados agregados reais, interprete"
   ← Ambos retornam análises fundamentadas

6. Maestro → avaliador_coerencia
   "Rankear essas 2 análises"
   ← Retorna respostas ordenadas

7. Maestro → Usuário
   "Vendas cresceram 15%, qualidade está OK (0.2% nulls)"
```

---

## 🎁 CHECKLIST PARA PRÓXIMA VERSÃO

- [ ] Contratos de skill documentados em `contrato_de_skill.md`
- [ ] Skill Agregador implementado
- [ ] Fluxos de orquestração diagramados em `FLUXOS.md`
- [ ] agente_mysql com tratamento de erros detalhado
- [ ] agente_orquestrador_dados para múltiplas tabelas
- [ ] Testes de integração entre skills
- [ ] Versionamento de scores
- [ ] Detecção centralizada de colunas em agente_mysql

---

**Fim da Análise.**  
*Suas skills têm **excelente fundação**. As recomendações acima ajudam a escalar de forma robusta.*
