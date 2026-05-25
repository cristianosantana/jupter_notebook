# ADR 0002: Roadmap Para Selecao De Query Com Embeddings

## Status

Proposta.

## Contexto

O seletor semantico de query escolhe um `QueryTemplate` a partir de QueryCards declarados no catalogo. A primeira versao usa a LLM como classificador/reranker seguro sobre todos os cards disponiveis e valida a saida contra `QueryCapabilityCatalog`.

Com o crescimento do catalogo, enviar todos os cards para a LLM pode ficar caro e menos preciso.

## Decisao

A evolucao opcional sera:

```text
pergunta -> embedding da pergunta -> top K QueryCards -> LLM reranker -> validacao -> QueryExpander
```

Embeddings entram apenas para recuperar candidatos provaveis. A decisao online continua sendo ranking/classificacao seguida de validacao deterministica.

`k-means` nao deve ser usado no caminho online de decisao. Se houver clusterizacao, ela fica restrita a ferramentas offline de inspecao, organizacao e auditoria do catalogo.

## Consequencias

- O SQL segue allowlisted e nunca e gerado pela LLM.
- O top K reduz tokens sem remover a validacao final.
- Fallback deterministico continua obrigatorio quando embeddings, LLM ou validacao falharem.
- O trace deve preservar candidatos recuperados, escolha final, confidence e motivo de rejeicao.
