# Orion MCP v3

Pacote base (`connection_hub`: Postgres, MySQL, Redis), migrações de memória conversacional em PostgreSQL e especificação Redis.

## Documentação (ecossistema)

| Documento | Conteúdo |
|-----------|------------|
| [`docs/README.md`](docs/README.md) | Índice da pasta `docs/` |
| **[`docs/architecture/ORION_V3_MASTER_ARCHITECTURE.md`](docs/architecture/ORION_V3_MASTER_ARCHITECTURE.md)** | Índice mestre: infraestrutura analytics × plano incremental × cognição |
| [`docs/execution/PLANO_EXECUCAO.md`](docs/execution/PLANO_EXECUCAO.md) | Roadmap técnico incremental |
| [`docs/roadmaps/ROADMAP_COM_MYSQL_INTEGRADO.md`](docs/roadmaps/ROADMAP_COM_MYSQL_INTEGRADO.md) | Pipeline analytics + MySQL |
| [`docs/architecture/ARQUITETURA_COGNITIVA_CENTRAL.md`](docs/architecture/ARQUITETURA_COGNITIVA_CENTRAL.md) | Arquitetura cognitiva superior |

## Arranque rápido

```bash
cd orion_mcp_v3
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Migrações PostgreSQL

Variável **`POSTGRES_URL`** ou **`DATABASE_URL`** em `.env` na raiz desta pasta.

No **host** (fora do Docker), use `127.0.0.1` ou `localhost` e a **porta exposta** do Postgres — não use o hostname interno do compose (`cs_postgres`), pois não resolve no seu sistema.

```bash
python3 scripts/apply_migrations.py
```

É necessário **pgvector instalado no servidor PostgreSQL** (embeddings em `memory_embeddings`). Se aparecer `extension "vector" is not available`, instale o pacote no OS ou use uma imagem Docker com pgvector — ver o README das migrações.

Detalhes: [`src/orion_mcp_v3/infra/postgres/migrations/README.md`](src/orion_mcp_v3/infra/postgres/migrations/README.md).

Migrações MySQL futuras podem seguir o mesmo padrão em `src/orion_mcp_v3/infra/mysql/migrations/` (script dedicado quando existir).

## Redis (keyspace)

[`src/orion_mcp_v3/infra/redis/MEMORY_KEYSPACE.md`](src/orion_mcp_v3/infra/redis/MEMORY_KEYSPACE.md)


## Executar Tests

No projeto **`orion_mcp_v3`** os testes estão em `tests/` e o `pyproject.toml` define `pytest` em extras de desenvolvimento e `pythonpath = ["src"]`.

### Passos típicos

1. Na raíz do pacote (`orion_mcp_v3/`):

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

2. Executar todos os testes:

```bash
pytest tests/ -v
```


### O Analista

"Atue como um Arquiteto de Software Principal e Analista de Sistemas Sênior. Sua missão é analisar o projeto fornecido com o objetivo de propor melhorias estruturais, de processo e de performance.

Gere um documento técnico e detalhado estruturado estritamente nos seguintes tópicos:

1. Arquitetura e Estrutura do Projeto
Descrição da organização dos componentes/módulos e o papel de cada um.

Acoplamento e dependências entre as partes (identifique se há dependências circulares ou nós complexos).

2. Mapeamento Ponta a Ponta do Processo (Caminhos e Fluxos)
Explique o ciclo de vida do processo do início ao fim, passo a passo.

Mapeie todos os caminhos possíveis, incluindo o fluxo principal (happy path), caminhos alternativos, fluxos de exceção e tratamentos de erro.

3. Diagnóstico de Problemas e Gargalos
Pontos cegos no código ou na lógica de negócios.

Gargalos de performance, concorrência, memória ou processamento.

Dívidas técnicas evidentes.

4. Plano de Ação e Melhorias
Sugestões práticas de refatoração ou redesenho de fluxo para tornar o projeto mais resiliente, escalável e fácil de manter.

5. Utilize diagramas de sequência em texto (estilo Mermaid) para ilustrar o fluxo dos dados e a interação entre os componentes.

Adote um tom analítico, técnico, direto e extremamente detalhado."

### Geração de Memorias

A rotina é:

```bash
python3 scripts/distill_supervised_memory.py \
  --start 2026-06-09T00:00:00Z \
  --end 2026-06-10T00:00:00Z
```

Para cron diário, você precisa passar a janela do dia anterior. Exemplo rodando todo dia às 02:00:

```cron
0 2 * * * cd /home/lenovo/code/jupter_notebook/orion_mcp_v3 && python3 scripts/distill_supervised_memory.py --start "$(date -u -d 'yesterday 00:00' +\%Y-\%m-\%dT\%H:\%M:\%SZ)" --end "$(date -u -d 'today 00:00' +\%Y-\%m-\%dT\%H:\%M:\%SZ)" >> logs/distill_supervised_memory.log 2>&1
```

Ela espera no `.env`:
- `ORION_POSTGRES_URL` ou `ORION_DATABASE_URL`
- `ORION_LLM_API_KEY`
- configs de embedding já existentes, como `ORION_EMBEDDING_MODEL` e `ORION_EMBEDDING_DIMENSIONS`

Opcional:
- `--limit 500` para limitar quantas sessões ler na janela.