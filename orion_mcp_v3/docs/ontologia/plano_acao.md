## Critérios usados para ordenar por criticidade

Antes do plano, os critérios que decidem a ordem (do mais crítico ao menos crítico):

1. **Silêncio do erro** — falha visível/loud (quebra, exception) é menos grave que falha silenciosa (resposta errada entregue com confiança ao usuário).
2. **Está ativo agora vs. é risco latente** — algo já causando erro em produção pesa mais que uma fragilidade teórica ainda não observada.
3. **Raio de impacto (blast radius)** — quantos `fact_keys`/dimensões/turnos passam por aquele ponto do pipeline.
4. **Acoplamento estrutural** — proximidade com `build_context_key()`, `FallbackPolicy`, gramática de `FactKey` (mudar aqui é "hardware", conforme discutido).
5. **Dependência entre itens** — se corrigir A sem corrigir B deixa um buraco na correção (ex.: um gate que pode ser furado por outra via).
6. **Confiança declarada vs. completude real** — uma resposta com confiança 0.9 que na verdade cobre uma fração do que foi perguntado é mais grave que uma resposta que se recusa a responder, porque o usuário não tem como saber que precisa desconfiar.

---

## Seção 0 — Auditoria de dados reais (concluída)

Rodada sobre 23 turnos de `public_chat_pipeline` e 8 turnos de `analytics_pipeline`. Resultado: dois achados novos, não previstos no plano original, e confirmação de que o caminho de falha "alta" (gap declarado) já funciona corretamente. Nenhuma evidência a favor ou contra os itens 3–6 do plano original — os logs disponíveis não cobrem o estágio de destilação, e a amostra não exercitou o caminho de `IndexKey` desconhecida.

**Pendência que fica registrada, não resolvida:** para auditar a Seção 5 (rejeição dura na destilação) com dados reais, é necessário um terceiro log — do estágio de resolução `dimension`/`metric_kind` dentro do `distillery` propriamente dito. O `analytics_pipeline` capturado é do gerador/broker, uma camada antes.

---

## Seção 1 (mais crítico, novo) — Interpretação de expressões de intervalo/lista como filtro literal único

- **O que é:** o `intent.interpret` pode transformar uma expressão que descreve um **universo de valores a comparar** (ex.: "qual parcela, de 1x a 10x, teve maior crescimento") em um `entity_filter` de **valor único** (ex.: `parcelas=1X`), fazendo o `fact.plan` gerar apenas uma `fact_key` em vez de um conjunto para ranking.
- **Por que é o mais crítico de todos:** é o único item, entre tudo discutido até agora, com evidência direta de produzir uma **resposta factualmente incompleta entregue com confiança alta (0.9)** a uma pergunta real. O sistema chega a mencionar a própria limitação dentro do texto da resposta ("é o único registro disponível"), mas embutida como se fosse parte natural do resultado de um ranking — não como um alerta. Um usuário lendo rápido sai convencido de que houve uma comparação real entre 10 opções.
- **Diferença em relação ao bug histórico já corrigido:** a correção anterior tratava múltiplos `entity_filters` sendo descartados. Aqui o problema é anterior a isso — um único `entity_filter` malformado, construído a partir da má leitura de uma expressão de intervalo. É uma causa raiz nova dentro da mesma família de sintoma (perda silenciosa de abrangência).
- **Dependências:** nenhuma das seções abaixo depende deste item, mas ele deveria ser corrigido antes de qualquer trabalho em cima do `intent.interpret` para as Seções 2 e 3, para não misturar causas na mesma revisão.
- **Ação recomendada:** revisar como `intent.interpret` reconhece e representa expressões de intervalo/enumeração (ex.: "de 1x a 10x", "entre X e Y", "qualquer uma das formas de pagamento") — decidir se a saída correta é: (a) uma operação de tipo `ranking` sem `entity_filter` fixo, deixando o `fact.plan` expandir para todas as entidades daquele eixo, ou (b) um novo tipo de `entity_filter` que representa um **conjunto** de valores, não um valor único. Em paralelo, tratar como regra de segurança imediata: sempre que uma resposta de ranking for baseada em `n=1` registro, a confiança relatada deve refletir isso — não deveria sair como 0.9 nesse cenário, independentemente da causa raiz ser corrigida ou não.
- **Critério de conclusão:** uma pergunta de ranking sobre um eixo com múltiplos valores possíveis gera `fact_keys` cobrindo todos os valores relevantes do eixo (ou, quando isso não for viável, a resposta declara explicitamente e com destaque — não como nota de rodapé — que a comparação foi parcial, com confiança ajustada para refletir isso.

---

## Seção 2 (crítico, novo) — Colisão entre nome de Dimension e valor literal de outra Dimension

- **O que é:** quando o valor de um `entity_filter` contém, como substring, o nome de uma dimensão diferente da dimensão correta (ex.: "Prestação de **Serviços**" → dimensão errada `servico`; "Cortesia **Concessionária**" → dimensão errada `concessionaria`, quando a dimensão real de ambos é `tipo_de_venda`), o `intent.interpret` rotula o `entity_filter` com a dimensão errada.
- **Por que vem logo depois do Achado 0:** nos dois casos observados, o sistema se recuperou — a resposta final saiu correta porque o `fact.plan` conseguiu resolver via correspondência de entidade, independentemente do rótulo de dimensão errado. Mas essa recuperação é um efeito colateral de outro mecanismo (heurística de match), não uma garantia de design. O preço já visível é silencioso: a requirement "total" pareada descarta o filtro (`discarded_scope: not_in_schema`) sem qualquer menção na resposta ao usuário.
- **Por que é diferente da Seção 1 original do plano anterior (gate de `IndexKey`):** aquele item tratava de `IndexKey` desconhecida chegando ao `FallbackPolicy` sem validação. Este item é anterior — é o próprio rótulo de **Dimension** dentro do `entity_filter` nascendo errado no `intent.interpret`, antes de qualquer `fact_key` ser montada. Reforça a direção já discutida de mover parte da validação para mais cedo no pipeline, mas com uma causa concreta agora identificada: colisão de string entre nome de dimensão e valor de catálogo.
- **Dependências:** relacionado à Seção 3 abaixo (antigo item 1: gate estrutural de `IndexKey`), mas não depende dela — pode ser corrigido antes, já que atua num estágio anterior do pipeline.
- **Ação recomendada:** mapear, a partir do catálogo de valores conhecidos de `tipo_de_venda` (e de outras dimensões com o mesmo risco), quais termos têm probabilidade de colidir com nomes de dimensão existentes no catálogo. Decidir se a correção fica no `intent.interpret` (dar ao LLM contexto explícito do catálogo de valores por dimensão antes da extração) ou numa camada de correção pós-extração que reclassifica o `entity_filter` quando o valor bate com um item conhecido de outra dimensão. Também vale expor o `discarded_scope` de forma visível quando ele afeta uma requirement que compõe a resposta final — não só como campo de log interno.
- **Critério de conclusão:** os dois casos observados (e casos análogos do mesmo padrão) resolvem com a dimensão correta atribuída na primeira tentativa, sem depender do mecanismo de recuperação por heurística — e qualquer `discarded_scope` que ainda ocorra fica rastreável até a resposta final, não apenas até o log.

---

## Seção 3 (antigo item 1) — Gate estrutural de `IndexKey` para `fact_keys dynamic:`

- **O que é:** o `FallbackPolicy` não valida se o `IndexKey` embutido numa `fact_key dynamic:` existe de fato (nem em `CANONICAL_INDEX_META`, nem no índice runtime dos hits) — só valida tema.
- **Situação após a auditoria:** nenhuma evidência a favor ou contra nos 23 turnos — todas as `fact_keys` resolveram com sucesso via `meta_exact` ou `heuristic`, nenhuma via fallback de LLM. Isso não reduz a prioridade estrutural do item (a ausência de sintoma numa amostra pequena não é garantia de ausência do problema), mas significa que, diferente das Seções 1 e 2, este item segue sendo uma correção preventiva, não uma correção de algo já observado quebrando.
- **Dependências:** mesma relação de antes com a Seção 4 (parser `@` vs `:`) — devem ser tratadas juntas ou o parser primeiro.
- **Ação recomendada:** mantém-se a proposta anterior — dois níveis de confiança (catálogo canônico vs. runtime-only vs. desconhecido), com logging estruturado de rejeições.
- **Critério de conclusão:** inalterado — toda `fact_key dynamic:` que chega ao `FallbackPolicy` tem origem rastreável e classificada.

---

## Seção 4 (antigo item 2) — Alinhamento do parser da gramática (`@` vs `:`)

- **O que é:** o parser aceita `:` além de `@` como separador, mas o escritor canônico só produz `@`.
- **Situação após a auditoria:** sem alteração — não há evidência nos logs de uso do separador `:`, o que é esperado, já que o escritor canônico não o produz. O risco permanece teórico mas estrutural.
- **Dependências:** deve ser resolvido junto ou antes da Seção 3, como antes.
- **Ação recomendada:** inalterada.
- **Critério de conclusão:** inalterado.

---

## Seção 5 (antigo item 3) — Divergência do mapa produtor↔consumidor (`DIMENSION_TO_INDEX_KEY`)

- **O que é:** mapa `Dimension → IndexKey` desalinhado entre produtor e consumidor, com pelo menos um caso confirmado no código (`por_concessionaria`).
- **Situação após a auditoria:** o `matched_key` `faturamento_e_comissao_por_concessionaria` apareceu 2 vezes na amostra, sem sintoma visível associado — nem confirma nem descarta o impacto prático da divergência. Seria necessário um turno que dependesse especificamente da resolução cruzada produtor↔consumidor dessa dimensão para observar o efeito.
- **Dependências:** inalterada — antes da Seção 6, independente das Seções 1–4.
- **Ação recomendada:** inalterada.
- **Critério de conclusão:** inalterado.

---

## Seção 6 (antigo item 4) — Rejeição dura na destilação (dimension/metric_kind desconhecidos)

- **O que é:** valores desconhecidos de `dimension`/`metric_kind` são gravados com warning em vez de rejeitados na `MemoryCurtaEntry`.
- **Situação após a auditoria:** **não auditável** com os logs disponíveis — nenhum dos dois arquivos captura esse estágio. Fica como item pendente de auditoria futura (ver pendência registrada na Seção 0), não como item resolvido nem descartado.
- **Dependências:** inalterada — depende da Seção 3 estar no ar.
- **Ação recomendada:** inalterada, com adendo: antes de agir, buscar ou instrumentar um log específico do estágio de resolução dentro do `distillery` para poder aplicar a mesma auditoria feita aqui.
- **Critério de conclusão:** inalterado.

---

## Seção 7 (antigo item 5) — Fallback de desambiguação de `IndexKey` restrito a allowlist de hits

- **O que é:** `_llm_disambiguate_index` só escolhe dentro dos hits do turno, sem fallback para o catálogo legado.
- **Situação após a auditoria:** `used_llm_disambiguation` foi `False` em 100% dos 23 turnos — nenhuma evidência de que esse caminho está sendo exercitado na prática, na amostra observada.
- **Dependências:** inalterada.
- **Ação recomendada:** inalterada — reforço: com a nova amostra, a recomendação de "avaliar frequência real antes de investir" fica ainda mais justificada, já que a frequência observada até agora é zero.
- **Critério de conclusão:** inalterado.

---

## Seção 8 (antigo item 6, menos crítico) — Vazamento de scope/entidade e enums não confirmados

- **O que é:** os dois subitens de menor gravidade do plano original.
- **Situação após a auditoria:** o mecanismo de `discarded_scope` (telemetria + sanitização) apareceu ativo e funcionando como projetado em 4 dos 23 turnos — mas, como o Achado 1 mostrou (Seção 2 deste plano atualizado), o mecanismo está mascarando um problema de rotulagem incorreta rio acima, não apenas descartando ruído legítimo como presumido antes. Isso não muda a criticidade deste item específico (a telemetria em si está correta), mas reforça que ele não deve ser lido como "sem problema" — é sintoma de outra coisa, já capturada na Seção 2.
- **Dependências:** inalterada.
- **Ação recomendada:** inalterada para o subitem de enums (monitoramento). Para o subitem de scope leakage, adicionar uma nota cruzando com a Seção 2: ao corrigir a rotulagem de dimensão no `intent.interpret`, revalidar se a frequência de `discarded_scope` cai — se cair a praticamente zero, confirma que a maior parte da telemetria hoje é sintoma da Seção 2, não ruído de entrada legítimo.
- **Critério de conclusão:** inalterado, mais a verificação cruzada acima.