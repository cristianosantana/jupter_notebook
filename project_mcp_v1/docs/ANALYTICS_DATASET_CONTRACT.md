# Contrato: datasets de analytics e agregação no host

Este documento descreve o contrato entre `run_analytics_query` (MCP), o registo em sessão e a tool virtual **`analytics_aggregate_session`** (host da API, não MCP).

## Handle `session_dataset_id`

- **Não** é input do utilizador final: o assistente obtém o valor do JSON da tool ou do digest; se faltar, reexecuta `run_analytics_query` com os mesmos argumentos (recuperação de contrato host↔LLM).
- Presente no JSON devolvido ao modelo após `run_analytics_query` com dados tabulares (`rows` ou `rows_sample` em modo compacto).
- Campos adicionais injectados pelo host:
  - `dataset_handling_note` — instrução para usar `analytics_aggregate_session`.
  - `dataset_sample_only` — `true` se o dataset for só amostra (`summarize=true`); agregações reflectem apenas essa amostra.

## Metadata da sessão (`sessions.metadata`)

Chave `analytics_datasets`:

- `by_id` — mapa `session_dataset_id` → `{ query_id, row_count, columns, cache_key, relative_path, sample_only, ... }`.
- `order` — ordem FIFO dos ids (para digest e limite `analytics_datasets_max_registered`).
- `cache_key_to_dataset_id` — liga o `mcp_cache_key` de `run_analytics_query` ao handle.

Ficheiros JSON sob `analytics_dataset_spill_dir` (por omissão `logs/analytics_datasets/`): `{session_uuid}_{dataset_id}.json` com `rows`, `columns`, `sample_only`, etc.

## Saída de `analytics_aggregate_session`

Objecto JSON com:

- `ok` — booleano.
- `group_by`, `result_columns`, `rows` (lista de objectos agregados), `row_count`.
- `method_note` — texto curto sobre o método (linhas filtradas, amostra).
- `sample_only` — eco do dataset.
- `error` — string, se `ok` for false.

## Operações e limites

- Configuração: `analytics_aggregate_max_rows`, `analytics_aggregate_timeout_seconds`, `analytics_aggregate_rate_limit_per_session`, `analytics_aggregate_top_k_max` em `Settings` / `.env`.
- **Multi-worker:** spill em disco local exige **sticky session** até ao mesmo worker; em várias instâncias sem sticky, usar armazenamento partilhado (PostgreSQL/object store) — não implementado nesta versão.

## Fluxo recomendado (sequential)

1. `run_analytics_query` → obter `session_dataset_id`.
2. `analytics_aggregate_session` → totais / Top N.
3. Redação final (+ formatador, se aplicável).
