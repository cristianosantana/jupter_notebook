# Documentação — Orion MCP v3

Índice da pasta **`docs/`**. O **índice mestre** entre roadmaps está em [`architecture/ORION_V3_MASTER_ARCHITECTURE.md`](architecture/ORION_V3_MASTER_ARCHITECTURE.md).

---

## Estrutura de diretórios

| Pasta | Conteúdo |
|-------|----------|
| **[`architecture/`](architecture/)** | Índice mestre (`ORION_V3_MASTER_ARCHITECTURE.md`) + arquitetura cognitiva (`ARQUITETURA_COGNITIVA_CENTRAL.md`). |
| **[`execution/`](execution/)** | Plano técnico incremental — [`PLANO_EXECUCAO.md`](execution/PLANO_EXECUCAO.md). |
| **[`roadmaps/`](roadmaps/)** | Roadmap genérico (`ROADMAP_EXECUTÁVEL.md`) + pipeline analytics MySQL (`ROADMAP_COM_MYSQL_INTEGRADO.md`). |
| **[`guides/`](guides/)** | Guias de referência — ex.: [`COMO_GEMINI_FUNCIONA.md`](guides/COMO_GEMINI_FUNCIONA.md). |
| **[`legacy/`](legacy/)** | Material histórico / v2 — ex.: overview v2. |
| **[`notes/`](notes/)** | Notas de desenho e variantes (ex.: [`notes/mysql-memory-unified/`](notes/mysql-memory-unified/)). |

---

## Atalhos frequentes

| Documento | Caminho |
|-----------|---------|
| Índice mestre (3 níveis: infra × execução × cognição) | [`architecture/ORION_V3_MASTER_ARCHITECTURE.md`](architecture/ORION_V3_MASTER_ARCHITECTURE.md) |
| Memória remissiva V2 — destilação supervisionada e índice N:M | [`architecture/MEMORIA_REMISSIVA_V2.md`](architecture/MEMORIA_REMISSIVA_V2.md) |
| O que implementar primeiro | [`execution/PLANO_EXECUCAO.md`](execution/PLANO_EXECUCAO.md) |
| Dados reais MySQL + broker | [`roadmaps/ROADMAP_COM_MYSQL_INTEGRADO.md`](roadmaps/ROADMAP_COM_MYSQL_INTEGRADO.md) |
| Roadmap por fases 0–6 (genérico) | [`roadmaps/ROADMAP_EXECUTÁVEL.md`](roadmaps/ROADMAP_EXECUTÁVEL.md) |
| Como o sistema “pensa” (especificação) | [`architecture/ARQUITETURA_COGNITIVA_CENTRAL.md`](architecture/ARQUITETURA_COGNITIVA_CENTRAL.md) |

---

## Código relacionado

- Pacote Python: [`../src/orion_mcp_v3/`](../src/orion_mcp_v3/)
- Redis keyspace: [`../src/orion_mcp_v3/infra/redis/MEMORY_KEYSPACE.md`](../src/orion_mcp_v3/infra/redis/MEMORY_KEYSPACE.md)
