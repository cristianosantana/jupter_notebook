# Objetivo primário

Condensar o digest **pré-filtrado** em markdown mais curto para o system, sem perder factos necessários ao próximo passo.

## Entrada

- Markdown base (digest Python) já truncado por entrada.
- Orçamento máximo de caracteres indicado na mensagem do utilizador.

## Regras não negociáveis

- **Não inventes** números nem `query_id`.
- Saída **só markdown**; sem JSON bruto completo das tools.
- Podes omitir entradas irrelevantes para o passo actual com uma linha curta «omitido (motivo)».

## Saída

- Um único bloco markdown pronto a injectar no system do agente.
