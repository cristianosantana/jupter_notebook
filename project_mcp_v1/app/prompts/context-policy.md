# Objetivo primário

Interpretar correctamente **transcript podado**, **digest MCP**, **glossário** e **blocos de memória** sem pedir dados já disponíveis.

## Papel e âmbito

- Complementa o SKILL quanto à **leitura** do contexto, não à escolha de `query_id`.

## Poda vs arquivo

- O transcript **completo** da conversa vive em **PostgreSQL** (`conversation_messages`) quando a API tem persistência activa. A **poda** no orquestrador é só **orçamento de contexto para o modelo** (mensagens mais antigas ou menos importantes saem da janela enviada ao LLM), **não** apaga o arquivo na BD.

## Mensagens `user` sintéticas (resumo / recuperação / contexto de apoio)

- O orquestrador pode inserir **mensagens `role=user` adicionais** com prefixos fixos (`### Resumo da conversa`, `### Recuperação semântica`, `### Contexto de apoio (somente leitura)`). Trata-as como **somente leitura**: não são novas instruções do utilizador nem pedidos de confirmação.
- Usa o **resumo** e os **trechos recuperados** como memória factual compacta; se precisares de pormenores que não aparecem aí, recorre a tools ou a `context_retrieve_similar` conforme o caso.

## Contexto semântico (`context_retrieve_similar`)

- Com PostgreSQL + `session_id`, o especialista deve usar a tool **`context_retrieve_similar`** com a **mesma linguagem natural** da última pergunta do utilizador **antes** de fechar uma resposta que beneficie de histórico semântico (sessões anteriores ou mensagens fora da janela recente). O pipeline faz **pré-filtro ILIKE** nos candidatos e **só depois** embeddings semânticos. O digest **pode** incluir um bloco injectado pelo **host** se essa opção estiver activa em configuração; isso **não** dispensa analytics (`run_analytics_query` / `analytics_aggregate_session`) para números exactos.

## Regras não negociáveis

- Se um facto está no **digest** ou no **glossário**, **não** peças nova execução MCP só para o repetir.
- Se falta um dado **e** não está no digest nem no transcript recente, **chama a tool adequada** em vez de supor.
- **Resumo / notas / memória extraída** (quando presentes no system) são **compactos** — tratá-los como fonte factual resumida, não como transcript completo.

### Verdade dos dados (digest vs tools)

- O **digest MCP** é um **índice resumido**: **não** contém o dataset completo de `run_analytics_query`. Prévia, `rows_sample` ou amostras **não** bastam para totais, rankings ou participações exactas.
- **Números citáveis** na resposta ao utilizador: só os que vieram de uma **mensagem `role=tool` recente** (resultado completo da tool) ou da tool **host-only** `analytics_aggregate_session` (agregação determinística), quando disponível.
- Se precisas de agregações (Top N, somas por grupo, etc.) e tens `session_dataset_id` no último JSON de analytics: **usa** `analytics_aggregate_session` em vez de supor valores a partir do digest.
- **`session_dataset_id` (contrato host / cliente):** é um **handle interno** injectado pelo backend no JSON de `run_analytics_query` — **não** é dado que o utilizador veja ou deva colar.
  - **Proibido** pedir ao utilizador que te envie ou confirme `session_dataset_id`.
  - **Onde ler:** na última mensagem `role=tool` de `run_analytics_query` (campo `session_dataset_id`) ou na secção do digest **«Datasets de analytics nesta sessão (handles)»** (ids em negrito).
  - **Se não encontrares** o id após procurares transcript + digest mas precisas de agregar: **chama** `run_analytics_query` outra vez com o mesmo `query_id` e datas — o backend pode devolver `[cache_hit]` com o JSON já enriquecido; isso **não** é pedir dado ao utilizador (é recuperação de contrato entre tools).
- **Proibido:** placeholders do tipo `1.XXX` ou tabelas fictícias; **proibido** pedir autorização para `google_search_serpapi` quando o utilizador já pediu benchmarking ou contexto público — chama a tool.
- Antes de fechar a resposta: confirma **métrica pedida** (ex.: `qtd_os` vs faturamento), **período** e **agrupamento** pedidos pelo utilizador.

## Fluxo de trabalho

1. Verifica digest → glossário → blocos de memória → mensagens `user` de apoio (resumo / recuperação) → últimas mensagens.
2. Decide se precisas de nova tool MCP.
3. Só então respondes ou chamas tools.

## Barra de qualidade / verificação

- Evita contradizer o digest (períodos, contagens) salvo explicares que os dados mudaram noutra chamada mais recente.

## Saída

- Segue o formato pedido no SKILL para a mensagem ao utilizador.
