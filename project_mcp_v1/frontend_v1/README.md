# SmartChat Streamlit (`frontend_v1/`)

Interface alternativa ao frontend React (Vite), com a mesma API FastAPI (`POST /api/chat`, `GET /api/sessions`, `GET /api/sessions/{id}`). O Streamlit chama URLs absolutas (`API_BASE_URL`); não há proxy como no Vite.

## Arranque

1. Arranque a API (ex.: `uvicorn` na raiz do projecto) na porta por omissão **8000**.
2. Confirme CORS: por omissão, `app/config.py` inclui `http://localhost:8501` e `http://127.0.0.1:8501`. Se usar `.env`, acrescente essas origens a `CORS_ORIGINS` separadas por vírgula.
3. Instale dependências e execute o Streamlit a partir desta pasta:

```bash
cd frontend_v1
pip install -r requirements.txt
export API_BASE_URL=http://127.0.0.1:8000
# opcional: filtrar sessões na API
export DEMO_USER_ID=o_seu_user_id
streamlit run app.py
```

O browser abre em **http://localhost:8501** por omissão.

## Variáveis de ambiente

| Variável | Significado |
|----------|-------------|
| `API_BASE_URL` | Base da API (omissão: `http://127.0.0.1:8000`). |
| `DEMO_USER_ID` | `user_id` enviado no chat e em `GET /api/sessions` quando definido. |

## Estrutura

- `app.py` — entrada fina (`run_app()`).
- `smartchat/` — pacote modular: `config`, `state`, `services/api`, `message_processing` (sem Streamlit), `views`, `styles.py`, `assets/custom.css`.

## Testes (`pytest`)

```bash
cd frontend_v1
PYTHONPATH=. pytest tests/
```
