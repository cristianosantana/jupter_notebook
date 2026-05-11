# Orion MCP

Sucessor state-driven do `project_mcp_v1`. Documentação viva:

- [ARCHITECTURE.md](ARCHITECTURE.md) — invariantes e mandamentos
- [docs/](docs/) — arquitetura, módulos, API (validados no CI)
- OpenAPI: `GET /openapi.json` ao correr a API

```bash
cd orion_mcp
pip install -e ".[dev]"
orion-api
```

**`ModuleNotFoundError: No module named 'orion_mcp'`** com `uvicorn ... --reload`: o subprocesso do reload nem sempre vê o pacote se não estiver instalado no venv. Usa **uma** destas opções:

1. **Recomendado (sem instalar no venv):** na pasta `orion_mcp/`, `python3 run_server.py` — arranca `python -m uvicorn` com `PYTHONPATH=.../src` no ambiente.
2. **Após `pip install -e .` no mesmo venv do uvicorn:** `orion-api` ou `uvicorn orion_mcp.api.main:app --reload`.
3. **Uma linha manual:** `cd orion_mcp && PYTHONPATH=src python3 -m uvicorn orion_mcp.api.main:app --reload`

## PostgreSQL e pgvector

Sem o pacote **pgvector** no servidor, a migração `002_memory_embeddings.sql` fica **adiada** (a API sobe na mesma; memória longa em vector só depois de instalares a extensão).

- **Debian/Ubuntu (Postgres 16):** instalar o pacote que fornece `/usr/share/postgresql/16/extension/vector.control` (nome típico: `postgresql-16-pgvector`, conforme os teus repositórios).
- **Docker:** imagem base com pgvector, por exemplo `pgvector/pgvector:pg16`.
- Depois de instalado, reinicia o Postgres e volta a arrancar a Orion; na próxima execução de `run_migrations` a `002` aplica-se automaticamente.

## Memória longa: índice ANN (HNSW) e worker Celery

- **`ORION_EMBEDDING_DIMENSIONS` ≤ 2000:** a migração **`003_memory_embeddings_hnsw.sql`** cria índice **HNSW** (`vector_cosine_ops`), alinhado com `ORDER BY embedding <=> …` em `retrieve_memory`. A **`004_memory_embeddings_ivfflat.sql`** fica só **marcada como aplicada** (sem SQL; não precisas de IVFFlat).
- **`ORION_EMBEDDING_DIMENSIONS` > 2000** (ex.: **3072**): no pgvector actual (ex. 0.8.x), **HNSW e IVFFlat limitam-se a 2000 dimensões** para índice — não é possível ter índice ANN na coluna com 3072 dims. As migrações **003** e **004** ficam **marcadas como aplicadas** sem criar índice; **`retrieve_memory` continua a funcionar** (plano sequencial sobre `session_id` + ordenação por distância). Para **índice ANN** com OpenAI, usa **`ORION_EMBEDDING_DIMENSIONS` ≤ 2000** (ex. 1536 ou 2000).
- Se o `CREATE INDEX` da 003 falhar (pgvector antigo), o arranque continua com log de aviso e a 003 não fica registada até correres outra vez.
- Com **`ORION_ENABLE_LONG_MEMORY=true`**, pool Postgres e **`ORION_ENABLE_MEMORY_INDEX_WORKER=true`** (default), após respostas de chat (`GENERATE_RESPONSE` / `GENERATE_INSIGHTS`) o servidor **enfileira** `orion.embed_memory` no broker (`ORION_CELERY_BROKER_URL`). O **worker** faz embedding (OpenAI) + `INSERT` em `memory_embeddings`. Isto **não** conta para o orçamento `max_llm_calls_per_request` do pedido HTTP, mas **consome cota** da API de embeddings.
- Arranque do worker (outro terminal, mesmo `.env`):

```bash
cd orion_mcp && PYTHONPATH=src celery -A orion_mcp.infra.queue.celery_app worker -l info
```

- Para desligar só o enqueue (sem worker): `ORION_ENABLE_MEMORY_INDEX_WORKER=false`.
