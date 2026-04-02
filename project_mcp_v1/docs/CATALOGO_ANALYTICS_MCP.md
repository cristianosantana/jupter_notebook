# Catálogo de análises MCP (`QUERY_REGISTRY`)

**Fonte de verdade:** [mcp_server/analytics_queries.py](../mcp_server/analytics_queries.py) — variável `QUERY_REGISTRY` e conjunto `TABULAR_MULTIROW_QUERY_IDS` (classificação no catálogo).

Cada entrada mapeia um `query_id` a um ficheiro em [mcp_server/query_sql/](../mcp_server/query_sql/). Execução: tool `run_analytics_query` (datas obrigatórias `date_from`, `date_to`). SQL em texto: recurso MCP `analytics://query/{query_id}`.

**Fluxo recomendado para o agente LLM:** em caso de dúvida sobre qual análise executar → chamar a tool **`list_analytics_queries`** → escolher o `query_id` adequado → chamar **`run_analytics_query`** com `date_from` / `date_to`.

## Período e política LLM

- Todas as queries usam `__MCP_DATE_FROM__` e `__MCP_DATE_TO__` no SQL (substituídos pelo servidor).
- **Tabulares multi-linha** (`TABULAR_MULTIROW_QUERY_IDS`): 12 `query_id` (várias linhas por execução; inclui `performance_vendedor_mes`, `performance_vendedor_ano`, `cross_selling`, `faturamento_mensal_recebidos_pendentes`, `faturamento_mensal_recebidos_pendentes_por_concessionaria`, … `propenso_compra_hora_dia_servico`). Com **`summarize=false`**, a tool devolve o campo **`rows`** com todas as linhas da página (até `limit`; usar `offset` para paginar). Com **`summarize=true`**, a resposta fica compacta (`rows_sample`, notas e `llm_summary` quando o sampling MCP existir).
- **Demais `query_id`:** agregado JSON na coluna `resultado`; com `summarize=false` o JSON inclui essas linhas em `rows` como nas restantes.

## Referência cruzada com `30_QUERIES_OTIMIZADAS.md`

Os cinco últimos itens abaixo correspondem ao bloco VENDAS (Queries 1–5) em [30_QUERIES_OTIMIZADAS.md](30_QUERIES_OTIMIZADAS.md).

---

## Entradas (ordem do registo)

| `query_id`                                                    | Ficheiro                                                        | Formato resposta típico                                      | `resource_description`                                                                                   |
| ------------------------------------------------------------- | --------------------------------------------------------------- | ------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------- |
| `cross_selling`                                               | `cross_selling.sql`                                             | Tabular; `summarize=false` → `rows` completos da página      | Pares de serviços na mesma OS; ranking por concessionária e mês.                                         |
| `taxa_retrabalho_servico_produtivo_concessionaria`            | `taxa_retrabalho_servico_produtivo_concessionaria.sql`          | Tabular; `summarize=false` → `rows`                          | Retrabalho vs serviço produtivo por concessionária e período.                                            |
| `taxa_conversao_servico_concessionaria_vendedor`              | `taxa_conversao_servico_concessionaria_vendedor.sql`            | Tabular; `summarize=false` → `rows`                          | Conversão de serviço por concessionária e vendedor.                                                      |
| `servicos_vendidos_por_concessionaria`                        | `servicos_vendidos_por_concessionaria.sql`                      | Tabular; `summarize=false` → `rows`                          | Mix de serviços vendidos e share percentual por concessionária e mês.                                    |
| `sazonalidade_por_concessionaria`                             | `sazonalidade_por_concessionaria.sql`                           | Tabular; `summarize=false` → `rows`                          | Padrão sazonal de volume/OS por concessionária.                                                          |
| `performance_vendedor_mes`                                    | `performance_vendedor_mes.sql`                                  | Tabular; `summarize=false` → `rows`                          | KPIs de vendedor **por mês** (`periodo` = YYYY-MM); mesmas métricas que a análise anual.                 |
| `performance_vendedor_ano`                                    | `performance_vendedor_ano.sql`                                  | Tabular; `summarize=false` → `rows`                          | KPIs de vendedor **por ano civil** (`periodo_ano` = YYYY) no intervalo de datas.                         |
| `faturamento_ticket_concessionaria_periodo`                   | `faturamento_ticket_concessionaria_periodo.sql`                 | Tabular; `summarize=false` → `rows`                          | Faturamento de serviços, qtd OS e ticket médio por concessionária e mês.                                 |
| `faturamento_mensal_recebidos_pendentes`                      | `faturamento_mensal_recebidos_pendentes.sql`                    | Tabular; `summarize=false` → `rows`                          | Por mês (competência): OS distintas, total recebido, pendente e faturamento previsto (caixas/pendentes). |
| `faturamento_mensal_recebidos_pendentes_por_concessionaria`   | `faturamento_mensal_recebidos_pendentes_por_concessionaria.sql` | Tabular; `summarize=false` → `rows`                          | Igual à anterior, com GROUP BY por mês e concessionária (nome via `concessionarias.nome`).               |
| `distribuicao_ticket_percentil`                               | `distribuicao_ticket_percentil.sql`                             | Tabular; `summarize=false` → `rows`                          | Distribuição de ticket por quartis (NTILE) por concessionária.                                           |
| `propenso_compra_hora_dia_servico`                            | `propenso_compra_hora_dia_servico.sql`                          | Tabular; `summarize=false` → `rows`                          | Propensão de compra por hora, dia da semana e tipo de serviço.                                           |
| `volume_os_concessionaria_mom`                                | `volume_os_concessionaria_mom.sql`                              | Uma linha; coluna `resultado` (JSON) — **Query 1** do doc 30 | Volume de OS por concessionária com variação MoM (JSON agregado).                                        |
| `volume_os_vendedor_ranking`                                  | `volume_os_vendedor_ranking.sql`                                | `resultado` JSON — **Query 2**                               | Volume de OS por vendedor e concessionária com ranking (JSON).                                           |
| `ticket_medio_concessionaria_agg`                             | `ticket_medio_concessionaria_agg.sql`                           | `resultado` JSON — **Query 3**                               | Ticket médio e estatísticas por concessionária (JSON).                                                   |
| `ticket_medio_vendedor_top_bottom`                            | `ticket_medio_vendedor_top_bottom.sql`                          | `resultado` JSON — **Query 4**                               | Top 5 e bottom 5 vendedores por ticket médio (JSON).                                                     |
| `taxa_conversao_servicos_os_fechada`                          | `taxa_conversao_servicos_os_fechada.sql`                        | `resultado` JSON — **Query 5**                               | Conversão de linhas de serviço em OS fechadas, global e por loja (JSON).                                 |

---

## Quando usar (`when_to_use`)

Texto igual ao exposto por `list_analytics_queries` / `QUERY_ID_PARAM_HELP`:

- **cross_selling** — Combo de serviços vendidos juntos, cross-sell, frequência de pares na mesma ordem de serviço.
- **taxa_retrabalho_servico_produtivo_concessionaria** — Retrabalho, OS repetidas, qualidade operacional, taxa de retrabalho por unidade.
- **taxa_conversao_servico_concessionaria_vendedor** — Taxa de conversão de proposta/orçamento em venda de serviço, desempenho do vendedor.
- **servicos_vendidos_por_concessionaria** — Quais serviços mais vendidos, participação no faturamento por linha, mix por unidade.
- **sazonalidade_por_concessionaria** — Sazonalidade, meses mais fortes, variação ao longo do ano por concessionária.
- **performance_vendedor_mes** — Ranking de vendedores **por mês** (YYYY-MM), ticket médio, desconto médio, produtividade; para agregação **anual** usar `performance_vendedor_ano`.
- **performance_vendedor_ano** — KPIs de vendedor por concessionária e **ano civil** no intervalo de datas (ranking anual, faturamento/ticket agregados por ano).
- **faturamento_ticket_concessionaria_periodo** — Faturamento mão de obra/serviços, ticket médio por OS, volume por unidade num intervalo de datas.
- **faturamento_mensal_recebidos_pendentes** — Faturamento mensal por competência: macro (total previsto, tendência), recebíveis vs recebido, volume de OS; KPIs derivados (ticket médio, taxas de recebimento e pendência) — ver `when_to_use` completo no catálogo.
- **faturamento_mensal_recebidos_pendentes_por_concessionaria** — Mesma métrica quebrada por mês e concessionária (ABC por unidade, risco pendente vs total, volume de OS por loja).
- **distribuicao_ticket_percentil** — Segmentação por tamanho de ticket, quartis, perfil premium vs baixo ticket.
- **propenso_compra_hora_dia_servico** — Melhor hora/dia para vender, padrão temporal de compra por serviço.
- **volume_os_concessionaria_mom** — Volume mensal de OS, abertas/fechadas/canceladas, taxa de cancelamento e variação mês a mês.
- **volume_os_vendedor_ranking** — Ranking de vendedores por quantidade de OS, fechamentos e taxa de fechamento.
- **ticket_medio_concessionaria_agg** — Ticket médio, mín/máx, desvio padrão e faturamento por concessionária em OS fechadas.
- **ticket_medio_vendedor_top_bottom** — Destaques e caudas de desempenho por ticket médio por vendedor.
- **taxa_conversao_servicos_os_fechada** — Quantidade de serviços (itens) vs OS fechadas; taxa global e por concessionária.

---

## Manutenção

- Ao adicionar ou renomear `query_id`, atualizar `QUERY_REGISTRY`, `QueryId` em [mcp_server/server.py](../mcp_server/server.py), este documento e a tabela em [estrutura-e-recursos.md](estrutura-e-recursos.md).
- Se um novo `query_id` for tabular multi-linha (várias linhas por execução), acrescentar o id a `TABULAR_MULTIROW_QUERY_IDS` em `analytics_queries.py` para o catálogo descrever `rows` vs `summarize`.
