# Objetivo primário

Obter o glossário dinâmico `id → nome` para concessionárias, pessoas e serviços.

## Papel e âmbito

- Pode ser carregado pelo orquestrador ou por pedido explícito do modelo; o digest pode já conter uma execução recente.

## Regras não negociáveis

- **Não inventes** nomes: usa o markdown devolvido.
- Mesmos argumentos (`max_chars`, `include_demais_registos`, …) → reutilização via cache de sessão.

## Fluxo de trabalho

1. Verifica o digest.
2. Se necessário, chama com parâmetros alinhados ao Settings do projecto.

## Barra de qualidade / verificação

- Na resposta ao utilizador, prefere **nome** ao id nu quando o mapeamento existir.

## Saída

- Integra nomes do glossário na narrativa final.
