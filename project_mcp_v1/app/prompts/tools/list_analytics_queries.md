# Objetivo primário

Listar análises disponíveis e respectivos `query_id` antes de executar queries.

## Papel e âmbito

- Primeiro passo típico quando não sabes qual `query_id` usar.

## Regras não negociáveis

- Usa o texto devolvido pelo MCP como fonte oficial de IDs.
- Consulta o digest: uma listagem idêntica pode já estar em cache.

## Fluxo de trabalho

1. Chama com `{}` ou filtros suportados pelo servidor.
2. Escolhe o `query_id` alinhado ao pedido.
3. Segue para `run_analytics_query`.

## Barra de qualidade / verificação

- Não assumes nomes de queries que não apareçam na lista.

## Saída

- Decisão informada de `query_id` + justificação curta.
