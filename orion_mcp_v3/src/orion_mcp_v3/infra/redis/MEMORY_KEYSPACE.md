# Redis — convenções de memória conversacional

O Redis **não** usa ficheiros de migração DDL como o PostgreSQL. Este documento define o **keyspace** e TTL descritos em [`docs/MEMORIA_CONVERSACIONAL_ORION_MCP_V2.md`](../../../../docs/MEMORIA_CONVERSACIONAL_ORION_MCP_V2.md).

## Conexão

Variável de ambiente típica no repositório (ex.: `orion_mcp_v2/.env` na raiz do mono-repo):

```env
REDIS_URL=redis://cs_redis:6379/0
```

## Padrões de chave

| Padrão | Tipo Redis | Conteúdo | TTL |
|--------|------------|----------|-----|
| `memory:{user_id}:{CATEGORIA}` | String (JSON) | Resumo rápido: `recent_questions`, `key_insights`, `key_metrics`, `last_updated` | **604800** s (7 dias) |
| `memory:{user_id}:categories` | SET | Nomes de categorias indexadas (`FATURAMENTO`, `QUALIDADE`, …) | Opcional alinhar a 7 dias |

Exemplo de valor JSON na string:

```json
{
  "recent_questions": ["ticket jan", "ticket fev"],
  "key_insights": ["Crescimento +4.8%"],
  "key_metrics": {"ticket": 1450, "margem": "22%"},
  "last_updated": "2025-03-30T03:00:00Z"
}
```

## Inicialização

Não é obrigatório pré-criar chaves. A aplicação deve:

1. **SET** `memory:{user}:{categoria}` com `EX 604800` ao gravar resumo.
2. **SADD** `memory:{user}:categories` `{categoria}` e refrescar TTL se necessário.

## Script opcional (CLI)

Exemplo idempotente para validar conectividade (não persiste schema):

```bash
redis-cli -u "$REDIS_URL" PING
```

Para protótipo local sem dados sensíveis:

```bash
redis-cli -u "$REDIS_URL" SET memory:demo_user:FATURAMENTO '{"recent_questions":[],"key_insights":[],"key_metrics":{},"last_updated":"2026-01-01T00:00:00Z"}' EX 604800
```
