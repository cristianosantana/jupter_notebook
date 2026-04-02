# SmartChat

Interface React (Vite + TypeScript + Tailwind) para o orquestrador modular.

## Desenvolvimento

1. Arranque a API (ex.: `uvicorn app.main:app --reload` na raiz de `project_mcp_v1`, porta **8000**).
2. `npm install`
3. `npm run dev` — o Vite faz proxy de `/api` para `http://127.0.0.1:8000`.

- `GET /api/sessions` — lista sessões.
- `GET /api/sessions/{session_id}` — detalhe, `messages` (transcript persistido) e `trace_run_id` se existir em `sessions.metadata`.

Opcional: ficheiro `.env` com `VITE_DEMO_USER_ID=...` para filtrar `GET /api/sessions` e associar sessões a um utilizador.

## Build

`npm run build` — saída em `dist/`.
