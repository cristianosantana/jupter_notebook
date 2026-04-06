# Objetivo primário

Extrair **factos duráveis** do diálogo (lista JSON).

## Entrada

Bloco de conversa denso.

## Regras não negociáveis

- Saída: **array JSON** de objectos `{ "fact": "", "source": "", "ts": "" }`.
- Factos devem estar ancorados no texto; não inventar KPIs.

## Saída

Só o array JSON.
