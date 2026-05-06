# Redireccionamento

O ficheiro canónico dos mapas **ID → nome** passou a ser o embutido no pacote:

[`src/orion_mcp_v2/skill/reference_lookups.md`](../src/orion_mcp_v2/skill/reference_lookups.md)

O orquestrador **injerta automaticamente** esse conteúdo no system prompt (`reference_lookups_loader`). Não é necessário **@** no Cursor para o fluxo HTTP da API.
