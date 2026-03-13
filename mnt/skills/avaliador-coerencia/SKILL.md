---
name: avaliador-coerencia
description: >
  Avalia e ranqueia respostas de múltiplos agentes especializados em relação a uma pergunta original.
  Use esta skill sempre que houver um conjunto de respostas de agentes que precisam ser comparadas,
  filtradas e ordenadas por qualidade e relevância. Recebe o payload completo do Maestro com a pergunta
  e todas as respostas coletadas, aplica critérios multidimensionais de avaliação, e retorna as respostas
  ranqueadas com scores e indicação de quais passam no threshold de qualidade.
---

# Avaliador de Coerência

Skill independente responsável por avaliar objetivamente a qualidade e relevância das respostas
dos agentes em relação à pergunta original.

---

## Input Esperado

```json
{
  "pergunta_original": "<pergunta do usuário>",
  "tipo_resposta_esperada": "factual | analítica | técnica | criativa | comparativa",
  "respostas_coletadas": [
    {
      "agente_id": "agente-financeiro",
      "agente_nome": "Analista Financeiro",
      "resposta": "...",
      "scores_agente": {
        "relevancia": 0.9,
        "completude": 0.8,
        "confianca": 0.85,
        "score_final": 0.86
      },
      "limitacoes_da_resposta": "..."
    }
  ]
}
```

---

## Critérios de Avaliação

```txt
Para cada resposta recebida, pontuar de 0 a 10:

| Critério | Peso | O que avaliar |
|----------|------|--------------|
| **Alinhamento** | 30% | A resposta responde diretamente o que foi perguntado? |
| **Coerência Interna** | 20% | É internamente consistente, sem contradições? |
| **Precisão Técnica** | 20% | A informação é tecnicamente correta para o domínio? |
| **Complementaridade** | 15% | Adiciona perspectiva única em relação às outras respostas? |
| **Utilidade Prática** | 15% | É acionável e útil para o usuário? |
```

## Escalas de Referência

**Alinhamento (30%):**

- 9–10: Responde direta e completamente
- 7–8: Responde com pequenos desvios
- 5–6: Responde parcialmente
- 3–4: Tangencial à pergunta
- 0–2: Não responde

**Coerência Interna (20%):**

- 9–10: Sem contradições, argumentação sólida
- 7–8: Pequenas inconsistências sem impacto
- 5–6: Contradições que reduzem qualidade
- 0–4: Contradições relevantes

**Precisão Técnica (20%):**

- 9–10: Preciso e fundamentado
- 7–8: Pequenas imprecisões aceitáveis
- 5–6: Simplificações que afetam qualidade
- 0–4: Imprecisões relevantes

**Complementaridade (15%):**

- 9–10: Perspectiva única não coberta por nenhum outro agente
- 7–8: Complementa bem com leve sobreposição
- 5–6: Sobreposição significativa
- 0–4: Duplica sem agregar valor

**Utilidade Prática (15%):**

- 9–10: Altamente acionável
- 7–8: Útil com pequenas adaptações
- 5–6: Moderadamente útil
- 0–4: Pouco acionável

---

## Fórmula de Cálculo

```txt
score_coerencia = (alinhamento/10 × 0.30) +
                  (coerencia_interna/10 × 0.20) +
                  (precisao_tecnica/10 × 0.20) +
                  (complementaridade/10 × 0.15) +
                  (utilidade_pratica/10 × 0.15)

score_total = (score_coerencia × 0.60) + (score_final_agente × 0.40)
```

> O score de coerência tem peso 60% pois o Avaliador tem visão global de todas as respostas.
> O score do agente tem peso 40% pois é auto-avaliação do especialista.

---

## Threshold de Inclusão

```txt
| Score Total | Decisão |
|-------------|---------|
| ≥ 0.75 | ✅ Altamente qualificada — incluir com destaque |
| 0.65 – 0.74 | ✅ Qualificada — incluir |
| 0.50 – 0.64 | ⚠️ Marginal — incluir com ressalva |
| < 0.50 | ❌ Não qualificada — excluir |
```

---

## Detecção de Conflitos entre Agentes

```txt
Antes de retornar, verificar contradições entre respostas:

| Tipo de Conflito | Ação |
|-----------------|------|
| **Contradição direta** (afirmações opostas) | Sinalizar explicitamente, apresentar ambas |
| **Perspectiva divergente** (ênfases diferentes) | Preservar ambas como complementares |
| **Agente fora do domínio** | Penalizar Complementaridade (0–2) |
| **Respostas redundantes** | Penalizar Complementaridade, manter a mais completa |
```

---

## Output do Avaliador

```json
{
  "avaliacao_completa": [
    {
      "agente_id": "agente-financeiro",
      "agente_nome": "Analista Financeiro",
      "scores_avaliador": {
        "alinhamento": 9,
        "coerencia_interna": 9,
        "precisao_tecnica": 9,
        "complementaridade": 8,
        "utilidade_pratica": 9,
        "score_coerencia": 0.89
      },
      "score_total": 0.88,
      "status": "qualificada",
      "observacoes": "Resposta central e tecnicamente precisa."
    }
  ],
  "ranking_final": ["agente-financeiro", "agente-negocios", "agente-juridico"],
  "conflitos_detectados": [],
  "respostas_excluidas": [],
  "threshold_utilizado": 0.65
}
```

---

## Uso Independente

Esta skill pode ser usada fora do Maestro para avaliar qualquer conjunto de textos em relação
a uma pergunta, bastando formatar o input conforme o schema acima.
