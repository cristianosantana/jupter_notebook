# Senna Replica — suíte de regressão Prolog-first

Harness isolado (padrão Ceolin/Senna): cada erro do LLM vira um **case permanente**.
Python só empacota; o Veredito B é calculado por [`prolog/rules_lib.pl`](prolog/rules_lib.pl) via `swipl`.

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

| `status` | Expectativa do harness | No CI (`--suite`) |
|----------|------------------------|-------------------|
| `known_bug` | diverge (`exit 1`) | passa |
| `regression_guard` | converge (`exit 0`) | passa |
| qualquer + `exit 2` | insumos / swipl | **falha** |
| `known_bug` + converge | — | **falha** (promova o status) |
| `regression_guard` + diverge | — | **falha** (regressão) |

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

# Testes
python3 -m pytest scripts/senna_replica/tests/test_senna_replica.py -v
```

```bash
python3 scripts/run_senna_replica.py --from-db scripts/senna_replica/cases/secao1_cumulative_range_gwm_vn_fin --question "Qual a diferença entre o total de comissão por tipo_os 'Venda Normal' e por 'Financiamento' para a concessionária GWM BAMAQ, somando as comições de janeiro ate maio de 2026?" --operation cumulative --dimension tipo_os --index-key comissao_por_tipo_de_os_por_concessionaria --operand-labels 'Venda Normal|Financiamento'
````

`generated.pl` é gitignored — nunca commitar. O case §1 inclui `case.yaml` e `case.json` (fallback sem PyYAML).

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

| Code | Significado |
|------|-------------|
| 0 | Converge |
| 1 | Diverge |
| 2 | Insuficiente / erro / swipl ausente |

## Referências

- [`docs/ontologia/prompt_replicacao_prolog_perguntas.md`](../../docs/ontologia/prompt_replicacao_prolog_perguntas.md)
- [`docs/ontologia/ranking_parcelas_senna_pattern.pl`](../../docs/ontologia/ranking_parcelas_senna_pattern.pl)
