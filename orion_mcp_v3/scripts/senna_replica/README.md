# Senna Replica — suíte de regressão Prolog-first

Harness isolado (padrão Ceolin/Senna): cada erro do LLM vira um **case permanente**.
Python só empacota; o Veredito B é calculado por `[prolog/rules_lib.pl](prolog/rules_lib.pl)` via `swipl`.

## Ciclo de vida (obrigatório)

```
LLM errou
  → 1. Empacotar case com status: known_bug
  → 2. Confirmar diverge (exit 1)
  → 3. Corrigir o pipeline
  → 4. Confirmar converge (exit 0)
  → 5. Promover status → regression_guard
  → 6. CI permanente
```

**Empacotar antes de corrigir.** Nunca corrigir o Fact Engine sem um case vermelho já no repo.
Nunca deixar um `known_bug` passar a convergir sem promover o status.

## Nomenclatura

```
cases/<secao>_<tipo_bug>_<trace_id_curto>/
```

Exemplo: `secao1_ranking_periodo_parcelas_9ee5b6e3`

## Status do case (`case.yaml`)


| `status`                     | Expectativa do harness | No CI (`--suite`)            |
| ---------------------------- | ---------------------- | ---------------------------- |
| `known_bug`                  | diverge (`exit 1`)     | passa                        |
| `regression_guard`           | converge (`exit 0`)    | passa                        |
| qualquer + `exit 2`          | insumos / swipl        | **falha**                    |
| `known_bug` + converge       | —                      | **falha** (promova o status) |
| `regression_guard` + diverge | —                      | **falha** (regressão)        |




## Uso

Requisitos: `swipl` (SWI-Prolog). `PyYAML` é opcional se existir `case.json` ao lado do `case.yaml`.
Para `--from-db`: `asyncpg` + `DATABASE_URL` apontando ao Postgres com `memory_curta`.

```bash
# Case único (desenvolvimento) — devolve exit bruto do Prolog
python3 scripts/run_senna_replica.py \
  scripts/senna_replica/cases/secao1_ranking_periodo_parcelas_9ee5b6e3

# Só emitir generated.pl
python3 scripts/run_senna_replica.py ... --emit-only

# Empacotar do BD (harness isolado — não importa public_chat)
python3 scripts/run_senna_replica.py --from-db \
  scripts/senna_replica/cases/secao1_cumulative_range_gwm_vn_fin \
  --question "Qual a diferença entre o total de comissão ..." \
  --operation cumulative \
  --dimension tipo_os \
  --index-key comissao_por_tipo_de_os_por_concessionaria \
  --operand-labels 'Venda Normal|Financiamento'

# Suíte CI (interpreta status × exit)
python3 scripts/run_senna_replica.py --suite scripts/senna_replica/cases

# Testes unitários
python3 -m pytest scripts/senna_replica/tests/test_senna_replica.py -v
```

`generated.pl` é gitignored — nunca commitar. O case §1 inclui `case.yaml` e `case.json` (fallback sem PyYAML).

## Testes executados

Perguntas semente usadas no ciclo Senna (empacotar → diverge → fix → converge).
Rodar via `--from-db` (exemplo no case cumulative) ou pela suíte quando o case já existir em `cases/`.


| #   | Pergunta                                                                                                                                                                                                     | Case / operação                                                                   |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------- |
| 1   | Qual a diferença entre o total de comissão por tipo_os 'Venda Normal' e por 'Financiamento' para a concessionária GWM BAMAQ, somando as comissões de janeiro até maio de 2026?                               | `secao1_cumulative_range_gwm_vn_fin` **·** `cumulative`                           |
| 2   | Qual foi a variação percentual do faturamento por Cartão de Crédito entre janeiro e junho de 2026?                                                                                                           | `secao1_period_growth_cartao_jan_jun` · `period_growth`                           |
| 3   | Em março de 2026, qual a participação de 'Prestação de Serviços' sobre o faturamento total por tipo de venda, e como isso se compara a fevereiro?                                                            | `secao1_share_prestacao_mar_fev` · proxy `period_growth` (falta share)            |
| 4   | Qual concessionária teve a maior queda de comissão entre janeiro a maio de 2026?                                                                                                                             | `secao1_queda_comissao_concessionaria_b74becc8` · `period_decline`                |
| 5   | Das vendas parceladas em cartão de crédito em janeiro de 2026, qual parcela (1x a 10x) teve o maior crescimento percentual até junho?                                                                        | `secao1_ranking_periodo_parcelas_9ee5b6e3` · `period_growth`                      |
| 6   | Qual foi o serviço mais vendido maio de 2026, e ele se manteve o líder em junho de 2026?                                                                                                                     | `secao1_leader_change_growth_confundido_08143610` · `leader_change`               |
| 7   | Em quais meses entre janeiro e abril de 2026 o Pix ultrapassou o Cartão de Crédito como principal forma de pagamento, e qual foi a diferença percentual nesses meses?                                        | `secao1_timeseries_pix_cartao_jan_abr` · `time_series`                            |
| 8   | Comparando fevereiro até junho de 2026, o faturamento com 'Cortesia Concessionária' cresceu mais rápido, em termos percentuais, do que o faturamento total de 'Prestação de Serviços'?                       | `secao1_growth_cortesia_vs_prestacao_fev_jun` · `period_growth` (falta bool)      |
| 9   | Qual foi a soma do faturamento de estética automotiva (BH Estética, MFP, Carsoul, GB Estética, Xtreme PPF) em todo o 1º semestre de 2026, e qual dessas empresas teve a participação mais estável mês a mês? | `secao1_cumulative_estetica_1h2026` · `cumulative` (proxy `taxas_cartao_credito`) |


Exemplos `--from-db` (reempacota `memory.json` a partir do BD):

```bash
# 1 — cumulative GWM VN vs Financiamento
python3 scripts/run_senna_replica.py --from-db \
  scripts/senna_replica/cases/secao1_cumulative_range_gwm_vn_fin \
  --question "Qual a diferença entre o total de comissão por tipo_os 'Venda Normal' e por 'Financiamento' para a concessionária GWM BAMAQ, somando as comissões de janeiro até maio de 2026?" \
  --operation cumulative \
  --dimension tipo_os \
  --index-key comissao_por_tipo_de_os_por_concessionaria \
  --operand-labels 'Venda Normal|Financiamento'

# 2 — period_growth Cartão jan–jun
python3 scripts/run_senna_replica.py --from-db \
  scripts/senna_replica/cases/secao1_period_growth_cartao_jan_jun \
  --question "Qual foi a variação percentual do faturamento por Cartão de Crédito entre janeiro e junho de 2026?" \
  --operation period_growth \
  --dimension forma_pagamento \
  --index-key faturamento_por_forma_pagamento \
  --operand-labels 'Cartão de Crédito'

# 3 — share Prestação (proxy period_growth; falta op share)
python3 scripts/run_senna_replica.py --from-db \
  scripts/senna_replica/cases/secao1_share_prestacao_mar_fev \
  --question "Em março de 2026, qual a participação de 'Prestação de Serviços' sobre o faturamento total por tipo de venda, e como isso se compara a fevereiro?" \
  --operation period_growth \
  --dimension tipo_de_venda \
  --index-key faturamento_por_tipo_venda \
  --operand-labels 'Prestação de Serviços'

# 4 — period_decline maior queda comissão
python3 scripts/run_senna_replica.py --from-db \
  scripts/senna_replica/cases/secao1_queda_comissao_concessionaria_b74becc8 \
  --question "Qual concessionária teve a maior queda de comissão entre janeiro a maio de 2026?" \
  --operation period_decline \
  --dimension concessionaria \
  --index-key comissao_por_concessionaria_tipo_os

# 5 — period_growth parcelas cartão
python3 scripts/run_senna_replica.py --from-db \
  scripts/senna_replica/cases/secao1_ranking_periodo_parcelas_9ee5b6e3 \
  --question "Das vendas parceladas em cartão de crédito em janeiro de 2026, qual parcela (1x a 10x) teve o maior crescimento percentual até junho?" \
  --operation period_growth \
  --dimension parcelas \
  --index-key parcelamento_cartao

# 6 — leader_change serviço maio/junho
python3 scripts/run_senna_replica.py --from-db \
  scripts/senna_replica/cases/secao1_leader_change_growth_confundido_08143610 \
  --question "Qual foi o serviço mais vendido maio de 2026, e ele se manteve o líder em junho de 2026?" \
  --operation leader_change \
  --dimension servico \
  --index-key producao_por_servico

# 7 — time_series Pix vs Cartão jan–abr
python3 scripts/run_senna_replica.py --from-db \
  scripts/senna_replica/cases/secao1_timeseries_pix_cartao_jan_abr \
  --question "Em quais meses entre janeiro e abril de 2026 o Pix ultrapassou o Cartão de Crédito como principal forma de pagamento, e qual foi a diferença percentual nesses meses?" \
  --operation time_series \
  --dimension forma_pagamento \
  --index-key faturamento_por_forma_pagamento \
  --operand-labels 'Pix|Cartão de Crédito'

# 8 — period_growth Cortesia vs Prestação (falta bool comparativo)
python3 scripts/run_senna_replica.py --from-db \
  scripts/senna_replica/cases/secao1_growth_cortesia_vs_prestacao_fev_jun \
  --question "Comparando fevereiro até junho de 2026, o faturamento com 'Cortesia Concessionária' cresceu mais rápido, em termos percentuais, do que o faturamento total de 'Prestação de Serviços'?" \
  --operation period_growth \
  --dimension tipo_de_venda \
  --index-key faturamento_por_tipo_venda \
  --operand-labels 'Cortesia Concessionária|Prestação de Serviços'

# 9 — cumulative estética 1º semestre (proxy taxas_cartao_credito)
python3 scripts/run_senna_replica.py --from-db \
  scripts/senna_replica/cases/secao1_cumulative_estetica_1h2026 \
  --question "Qual foi a soma do faturamento de estética automotiva (BH Estética, MFP, Carsoul, GB Estética, Xtreme PPF) em todo o 1º semestre de 2026, e qual dessas empresas teve a participação mais estável mês a mês?" \
  --operation cumulative \
  --dimension estabelecimento \
  --index-key taxas_cartao_credito \
  --operand-labels 'BH ESTÉTICA|MFP ESTETICA AUTOMOTIVA|CARSOUL|GB ESTÉTICA|XTREME PPF'
```



## Isolamento `--from-db`

Infra vendored em `infra/` (`remissive_reader`, `pool`, `knowledge`, `noop_trace`) + `period_range.py`.
Sem `from orion_mcp_v3.public_chat...` no caminho live.

## Insumos de um case

- `case.yaml` — status, secao, intent **manual**, runtime_verdict
- `memory.json` — rows **completas** de `memory_curta` (o JSONL de pipeline redige `key_metrics`)
- `trace.jsonl` — extrato opcional do `public_chat_pipeline` (metadados / verificação)



## Critério de review — `rules_lib.pl`

- Toda lógica de Veredito B vive **só** em `prolog/rules_lib.pl`.
- Case novo com `intent.operation` (ou agregação) ainda não coberta **deve** estender a lib no mesmo PR.
- Operações atuais: `period_growth`, `period_decline`, `ranking_desc`, `ranking_asc`,
`leader_change`, `cumulative`, `time_series`.
- Dimensão só nos fatos; proibido catálogo estático `dominio(dimensao, [...])` nas regras.
- PR que só adiciona case sem estender a lib quando a operação é nova → barrar.
- Se B reporta `cobertura_incompleta` e A emitiu vencedor concreto → **diverge** (`exit 1`), padrão Senna.



## Exit codes (harness / swipl)


| Code | Significado                         |
| ---- | ----------------------------------- |
| 0    | Converge                            |
| 1    | Diverge                             |
| 2    | Insuficiente / erro / swipl ausente |




## Referências

- `[docs/ontologia/prompt_replicacao_prolog_perguntas.md](../../docs/ontologia/prompt_replicacao_prolog_perguntas.md)`
- `[docs/ontologia/ranking_parcelas_senna_pattern.pl](../../docs/ontologia/ranking_parcelas_senna_pattern.pl)`



# O `--index-key` **não é uma coluna isolada**. No `--from-db` ele casa principalmente com:



### 1. `memory_curta.context_key` (busca SQL)

O packer monta patterns `LIKE` e consulta `LOWER(context_key)`:

```26:31:scripts/senna_replica/infra/remissive_reader.py
_LOAD_CURTA_BY_CONTEXT_KEY_THEME = """
SELECT "id", "category", "context_key", "validated_answer", "key_metrics"
FROM "public"."memory_curta"
WHERE LOWER("context_key") LIKE $1
...
```

Exemplo de `context_key`:

`sistema_background:fechamento_gerencial:comissao_por_concessionaria_tipo_os:periodo-2026-01`

O “tema” (3º segmento) é o que o `index-key` tenta achar — com aliases (`tipo_os` ↔ `tipo_de_os`, etc.).

### 2. Chaves de `memory_curta.key_metrics` (JSON)

Depois dos hits, o packer escolhe a chave real em `key_metrics` (ex.: `comissao_por_tipo_de_os_por_concessionaria`) e grava isso no `case.yaml` como `intent.index_key`.

No parse do `memory.json`, o mesmo valor resolve a entrada dentro de `key_metrics` de cada hit.

---

**Resumo:** SQL filtra por `context_key`; o valor canônico do case vem das **chaves de** `key_metrics`. Os dois costumam ser o mesmo “slug” de tema, às vezes com naming ligeiramente diferente.