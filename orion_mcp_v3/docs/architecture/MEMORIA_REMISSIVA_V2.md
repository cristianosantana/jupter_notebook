# Memória Remissiva V2

**Projeto:** Orion MCP v3

**Camada:** Memory Augmentation Layer, camadas 2 e 3

**Status:** implementado como rotina independente de destilação supervisionada. Ainda não está acoplado ao runtime do chat público.

## Objetivo

Este subsistema consolida conversas supervisionadas de negócio em um índice remissivo vetorial. A ideia é transformar interações longas, com validações humanas, números e contexto operacional, em uma base materializada que possa ser consultada futuramente por um Chat Público para usuários leigos.

A implementação segue o padrão de índice de livro remissivo:

- `memory_curta` guarda a página de conteúdo validado: resposta consolidada, métricas e perguntas recentes.
- `memory_embeddings` guarda várias entradas curtas de índice para cada conteúdo validado, apontando para `memory_curta` por `origin_id`.
- `memory_essence` guarda conceitos, achados e regras estáveis extraídos das conversas.
- `memory_compression_log` audita cada janela processada pela rotina de destilação.

O objetivo principal é evitar diluição semântica. Em vez de vetorizar textos longos cheios de números, o sistema vetoriza perguntas curtas e objetivas que apontam para um conteúdo validado único.

## Escopo Implementado

Foi implementada a fundação completa da memória remissiva V2:

- Migração `010_remissive_memory_schema.sql`, que recria as tabelas `memory_curta`, `memory_embeddings`, `memory_essence` e `memory_compression_log`.
- Migração `011_memory_compression_log_wide_keys.sql`, que aumenta campos de auditoria para aceitar chaves e estados reais gerados pela rotina.
- Migração `012_memory_essence_wide_keys.sql`, que aumenta campos de tema e confiança em `memory_essence`.
- Idempotência adicional em `003_memory_embeddings.sql`, para coexistir com a recriação V2 durante aplicação ordenada de migrações.
- Modelos de domínio em `src/orion_mcp_v3/memory/remissive_models.py`.
- Leitor read-only de conversas supervisionadas em `src/orion_mcp_v3/memory/supervised_conversation_reader.py`.
- Store de persistência remissiva em `src/orion_mcp_v3/memory/remissive_memory_store.py`.
- Comando independente de destilação em `scripts/distill_supervised_memory.py`.
- Testes focados para schema, store, leitura, parsing de payload do LLM e serialização do resultado CLI.

## Separação do Runtime do Chat

A rotina V2 não altera o processo atual de chat.

Ela não foi registrada no lifespan da API, não foi integrada às rotas de chat, não substitui o retriever atual, não escreve em `chat_turn_embeddings` e não muda o fluxo de indexação por turno.

As tabelas `conversation_state` e `chat_turn_embeddings` são somente entrada para a rotina diária. A saída materializada fica nas tabelas `memory_*`.

## Fluxo Diário

O fluxo implementado é:

1. Um cron externo chama `scripts/distill_supervised_memory.py` com uma janela temporal.
2. `SupervisedConversationReader` lê sessões em `conversation_state` e turnos indexados em `chat_turn_embeddings` em modo read-only.
3. O comando monta um prompt com as janelas supervisionadas.
4. O LLM retorna um JSON estruturado com `knowledge`, `essence` e `compression_log`.
5. `parse_distillation_payload` valida, normaliza e aplica filtros mínimos de qualidade ao JSON.
6. `RemissiveMemoryStore` grava o lote nas tabelas `memory_*`.
7. O comando imprime um resumo JSON com `windows_read`, `knowledge_written` e `origin_ids`.

Comando base:

```bash
python3 scripts/distill_supervised_memory.py \
  --start 2026-06-03T00:00:00Z \
  --end 2026-06-04T00:00:00Z
```

Exemplo de cron diário:

```cron
5 2 * * * cd /home/lenovo/code/jupter_notebook/orion_mcp_v3 && python3 scripts/distill_supervised_memory.py --start "$(TZ=UTC date -d '1 day ago' +\%Y-\%m-\%dT00:00:00Z)" --end "$(TZ=UTC date +\%Y-\%m-\%dT00:00:00Z)" >> logs/distill_supervised_memory.log 2>&1
```

O `TZ=UTC` torna o cálculo da janela explicitamente UTC, sem depender do fuso local do servidor antes da formatação da data.

## Modelo de Dados

`memory_curta` é a fonte de verdade do conhecimento validado. Cada registro tem um `context_key` único e recebe upsert. Quando um item de conhecimento é atualizado, o conteúdo validado é substituído, `last_seen_at` é renovado e as perguntas de índice relacionadas são recriadas.

O `context_key` é calculado pelo código, não pelo LLM. O parser exige campos semânticos em `knowledge[]`: `user_id`, `category`, `theme`/`tema` e `periodo`/`period` opcional. A chave final usa o formato `{user_id}:{category_slug}:{theme_slug}` ou `{user_id}:{category_slug}:{theme_slug}:{periodo}`.

Qualquer `context_key`, UUID, hash ou slug livre retornado pelo modelo é ignorado. Isso mantém o upsert idempotente mesmo quando o LLM oscila na forma textual da resposta.

`memory_embeddings` é o índice N:M. Cada linha contém uma pergunta curta vetorizada em `embedding`, com `origin_type = 'memory_curta'` e `origin_id` apontando para o conteúdo validado. Isso permite várias perguntas apontarem para a mesma resposta consolidada.

O índice vetorial usa IVFFlat com `vector_cosine_ops` e `WITH (lists = 100)`. Esse valor é uma escolha inicial para a visão materializada atual; quando o volume esperado crescer, ele deve ser revisado próximo de `sqrt(n_linhas)` ou conforme medição real.

A consulta vetorial precisa configurar probes antes do `ORDER BY embedding <=> ...`. O método `RemissiveMemoryStore.search_origin_ids` faz isso dentro de uma transação com `set_config('ivfflat.probes', ..., true)`, usando `10` como padrão. Isso evita que o Chat Público, quando integrado, faça busca IVFFlat com recall baixo sem perceber.

Se `memory_embeddings` permanecer pequeno, abaixo de aproximadamente 10 mil linhas, uma migração futura para HNSW pode ser mais simples operacionalmente, pois remove a necessidade de ajustar probes por consulta e tende a ter recall melhor em bases menores.

`memory_essence` guarda achados estáveis por `(user_id, theme)`. A rotina faz upsert por esse par, atualizando observação, recomendação, métricas estáveis e confiança.

`memory_compression_log` registra a auditoria do processamento. O `batch_key` é idempotente para a janela executada e permite reprocessar a mesma janela sem duplicar logs.

## Parser do LLM

O parser foi endurecido para lidar com variações reais de resposta do modelo:

- Aceita chaves em inglês e aliases em português para itens de conhecimento, mas calcula `context_key` localmente a partir de `theme`/`tema` e `periodo`/`period`.
- Normaliza `confidence` numérico para `high`, `medium` ou `low`.
- Descarta `knowledge` com `validated_answer` menor que 50 caracteres, por ser conteúdo suspeito para virar memória vetorial.
- Descarta `knowledge` com `confidence = low` e registra warning com o identificador disponível do item.
- Aceita `compression_ratio` numérico, percentual e razão textual como `49:1`.
- Serializa detalhes estruturados de `what_was_kept` e `what_was_dropped` como JSON compacto.
- Ignora itens de conhecimento sem `validated_answer` válido.
- Aceita `compression_log` como objeto ou lista com um único objeto.
- Salva a resposta bruta do modelo em `logs/distill_supervised_memory_failed_*.json` quando o parse falha.

## Configuração Necessária

A rotina usa a mesma configuração de banco e LLM do projeto:

- `ORION_POSTGRES_URL` ou `ORION_DATABASE_URL`, para conectar ao PostgreSQL.
- `ORION_LLM_API_KEY`, para chamar o modelo de destilação.
- Configurações existentes de modelo, base URL e embeddings quando definidas no ambiente.

O banco precisa ter `pgvector` instalado, pois `memory_embeddings.embedding` usa `vector(1536)` e índice IVFFlat.

## Idempotência e Reprocessamento

O desenho permite reprocessar uma janela com segurança operacional:

- `memory_curta` faz upsert por `context_key`.
- `memory_embeddings` remove e recria o índice de perguntas de cada `origin_id`.
- `memory_essence` faz upsert por `(user_id, theme)`.
- `memory_compression_log` faz upsert por `batch_key`.

Essa abordagem privilegia a visão materializada mais recente para cada conhecimento validado.

Como a chave é derivada de campos canônicos, reprocessar a mesma janela com o mesmo tema e período atualiza o conteúdo existente em vez de criar duplicatas por UUID, timestamp ou slug instável gerado pelo modelo.

## Rotação de Memórias Antigas

Nem todo conhecimento antigo será reemitido para sempre pela destilação. Um relatório pode mudar de nome, um template SQL pode desaparecer ou um conceito operacional pode deixar de ser relevante.

Para evitar acúmulo silencioso de índice obsoleto, `memory_curta` possui `last_seen_at`. O upsert da rotina diária renova esse campo com `now()` sempre que o `context_key` aparece novamente.

A limpeza periódica deve chamar `RemissiveMemoryStore.delete_stale_knowledge(days=90)` ou executar comando equivalente contra o banco. A remoção ocorre em `memory_curta`; os registros associados em `memory_embeddings` são removidos por `ON DELETE CASCADE`.

Consulta equivalente:

```sql
DELETE FROM "public"."memory_curta"
WHERE "last_seen_at" < now() - INTERVAL '90 days';
```

## Uso Futuro no Chat Público

O consumidor planejado dessas memórias é um Chat Público voltado a usuários leigos. Nesse cenário futuro, o chat poderá transformar perguntas naturais em buscas vetoriais contra `memory_embeddings`, recuperar os `origin_id` mais relevantes e então carregar as respostas consolidadas em `memory_curta`.

Com isso, o usuário público não precisa conhecer nomes de tabelas, relatórios internos, chaves de contexto ou detalhes do processo supervisionado. Ele pergunta em linguagem comum, enquanto o índice remissivo conecta essa pergunta ao conhecimento validado anteriormente por especialistas.

`memory_essence` poderá complementar esse fluxo com regras, achados estáveis e interpretações recorrentes do negócio. O `memory_compression_log` continuará servindo para auditoria e rastreabilidade da origem das memórias.

Essa integração ainda é uma etapa futura. A entrega atual materializa as memórias e preserva o runtime existente sem ativar consumo automático pelo chat.

## Limites Atuais

Esta entrega não implementa consumo pelo Chat Público. Ela prepara as tabelas, contratos e rotina diária que tornam esse consumo possível em uma próxima etapa.

Também não muda a política de recuperação atual do chat privado/supervisionado. O índice remissivo V2 existe como camada materializada independente até uma decisão explícita de integração.

