# Objetivo primário

Documentar a tool MCP **`google_search_serpapi`**: pesquisa Google via SerpApi para contexto **externo** complementar às analytics internas.

## Argumentos (MCP)

- **`search_query`** (obrigatório): texto que irias escrever na caixa de pesquisa Google — frase curta ou palavras-chave, **derivado da pergunta do utilizador** (o que queres saber no mundo público).
- **`num_results`** (opcional): quantidade de resultados orgânicos (por defeito 8).

**Isto não é analytics:** nunca passes `query_id`, nomes de análises do catálogo, nem UUIDs. Esses identificadores são só para `list_analytics_queries` / `run_analytics_query`.

| Correcto | Errado |
|----------|--------|
| `search_query`: "regulamentação lavagem automóvel Portugal 2024" | `search_query`: `vendas_por_mes` (é um `query_id`) |
| `search_query`: "SerpApi pricing" | `search_query`: o mesmo texto que usarias em `query_id` para SQL interno |

## Regras não negociáveis

- **Obrigatório** quando a pergunta exige factos da web (notícias, mercado, regulamentação) e ainda não tens resultados dessa tool no transcript — **não inventes** factos externos.
- **Proibido** usar como substituto de `list_analytics_queries` / `run_analytics_query` para métricas da empresa.
- Depois de chamar: indica no texto ao utilizador que o trecho vem de **fontes públicas**; não mistures números web com totais internos sem rotular a fonte.

## Integração com dados internos (entrega)

- Os resultados desta tool servem para **explicar ou contextualizar** o que já obtiveste com `run_analytics_query` / dados MCP: enquadramento de mercado, actualidades ou definições públicas que **iluminem a leitura** dos números internos (ex.: tendência sectorial à luz de um pico de OS).
- **Proibido** usar a web como bloco isolado sem dizer **como** isso ajuda a interpretar as métricas da empresa; **proibido** tratar contagens ou totais vindos da web como se fossem dados da base.
- Narrativa sugerida quando coexistem as duas fontes: (1) o que os **dados internos** mostram; (2) o que as **fontes públicas** acrescentam ao contexto; (3) **interpretação conjunta** e limitações (a web não substitui nem “prova” os totais internos).

## Quando chamar

- Actualidades, benchmarks públicos, definições que não estão no glossário interno.
- Enquadramento externo pedido explicitamente pelo utilizador.

## Quando não chamar

- Pergunta **só** sobre OS, lojas, vendedores, períodos — dados internos.
- A mesma query de pesquisa já consta no digest/cache (evita custo duplicado).
