# Orion Chat Client

Cliente web mínimo para consumir a API HTTP do **orion_mcp_v3**, colocado na **raiz do repositório** (`orion_chat_client/`) para poder reutilizar com outras versões ou clones do backend.

## Contrato da API

- **POST** `/api/v1/chat`
- **GET** `/api/v1/sessions` — lista sessões; cada item inclui `conversation_id`, `turn_count` e **`messages`** (lista de `{ role, content, created_at, message_id }`, até `ORION_SESSION_LIST_MAX_MESSAGES` mensagens por sessão).
- **GET** `/api/v1/chat/options` — `policies` (valores de `AttentionPolicy`), `max_tokens_min` / `max_tokens_max`, `max_tokens_presets`, defaults.

### Nova conversa (primeira mensagem)

Envie `conversation_id: null` (ou omita o campo). O backend cria o UUID, processa o turno e devolve o id em `meta.conversation_id`. As mensagens seguintes devem reutilizar esse id no corpo.

```json
{
  "message": "Qual forma de pagamento domina o faturamento entre janeiro e abril de 2026?",
  "conversation_id": null,
  "stream": false,
  "max_tokens": 20000,
  "policy": "analytical"
}
```

### Continuar uma sessão

```json
{
  "message": "Segunda pergunta…",
  "conversation_id": "5da144f1-0930-4ce2-beb1-1c9da0cf768c",
  "stream": false,
  "max_tokens": 20000,
  "policy": "analytical"
}
```

- `max_tokens`: intervalo devolvido por **GET** `/api/v1/chat/options` (hoje 64–32000, alinhado ao `ChatRequest`).
- `policy`: lista em **GET** `/api/v1/chat/options` → campo `policies`.

## Desenvolvimento

1. Arranque a API (exemplo na raiz do pacote `orion_mcp_v3`):

   ```bash
   uvicorn orion_mcp_v3.api.main:app --reload --host 0.0.0.0 --port 8000
   ```

2. Instale e arranque o frontend:

   ```bash
   cd orion_chat_client
   npm install
   npm run dev
   ```

   Por defeito o Vite corre na porta **5174** e faz **proxy** de `/api` → `http://127.0.0.1:8000`, para evitar CORS em desenvolvimento.

3. Se a API estiver noutro host/porta em dev, defina no `.env`:

   ```bash
   VITE_DEV_PROXY_TARGET=http://127.0.0.1:9000
   ```

## Build para produção

```bash
cd orion_chat_client
npm run build
```

Defina a base absoluta da API (sem barra final):

```bash
export VITE_ORION_API_BASE=https://seu-servidor.example.com
npm run build
```

Os pedidos vão para `{VITE_ORION_API_BASE}/api/v1/...` (chat, sessions, chat/options). Garanta CORS (`ORION_API_CORS_ORIGINS`) no backend se o site for servido noutro domínio.

## Relação com `project_mcp_v1/frontend`

O chat completo do `project_mcp_v1` é outro produto. Este directório é **só** o cliente Orion reutilizável; não substitui o frontend do `project_mcp_v1`.
