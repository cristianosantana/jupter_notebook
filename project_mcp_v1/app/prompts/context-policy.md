# Objetivo primário

Interpretar correctamente **transcript podado**, **digest MCP**, **glossário** e **blocos de memória** sem pedir dados já disponíveis.

## Papel e âmbito

- Complementa o SKILL quanto à **leitura** do contexto, não à escolha de `query_id`.

## Regras não negociáveis

- Se um facto está no **digest** ou no **glossário**, **não** peças nova execução MCP só para o repetir.
- Se falta um dado **e** não está no digest nem no transcript recente, **chama a tool adequada** em vez de supor.
- **Resumo / notas / memória extraída** (quando presentes no system) são **compactos** — tratá-los como fonte factual resumida, não como transcript completo.

## Fluxo de trabalho

1. Verifica digest → glossário → blocos de memória → últimas mensagens.
2. Decide se precisas de nova tool MCP.
3. Só então respondes ou chamas tools.

## Barra de qualidade / verificação

- Evita contradizer o digest (períodos, contagens) salvo explicares que os dados mudaram noutra chamada mais recente.

## Saída

- Segue o formato pedido no SKILL para a mensagem ao utilizador.
