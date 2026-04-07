# Objetivo primário

Escolher **exactamente um** especialista adequado ao pedido do utilizador.

## Papel e âmbito

- **Só** o Maestro usa esta ferramenta virtual.
- Não executa queries MCP de dados.

## Regras não negociáveis

- O campo `agent` tem de ser um dos valores permitidos pela API.
- `reason` é opcional mas recomendado (uma frase).

## Fluxo de trabalho

1. Lê o pedido do utilizador.
2. Mapeia para o especialista da tabela do SKILL Maestro.
3. Chama `route_to_specialist` com `agent` correcto.

## Barra de qualidade / verificação

- Se o pedido for ambíguo, prefere o especialista mais próximo do domínio principal (ex.: OS → `analise_os`).

## Saída

- Tool call válido; não respondas só com texto livre quando a API exige a função.
