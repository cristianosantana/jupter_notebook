O único check que falhou foi cosmético — o texto `"field_parsers"` aparece no docstring do entrypoint (não como import). Vou verificar e corrigir:Confirmado — é só a docstring de documentação do módulo, não um import real. O check estava errado. Corrijo o check e apresento os arquivos:O problema é espaçamento — os checks procuravam `": "` sem espaços extras. Corrijo os checks:26/26 checks. Todos os arquivos compilam.O script saiu de 853 linhas para 268, e o total do módulo ficou em 1.169 linhas distribuídas em 7 arquivos com responsabilidades únicas. Aqui está o mapa:

---

**Onde cada coisa fica agora**

| Arquivo | Responsabilidade | Linhas |
|---|---|---|
| `distill_supervised_memory.py` | CLI, wiring de dependências, orquestração | 268 |
| `distillery/__init__.py` | API pública do módulo | 33 |
| `distillery/result.py` | Dataclass `DistillationResult` | 14 |
| `distillery/field_parsers.py` | Extração tipada de campos do payload LLM | 227 |
| `distillery/catalog.py` | Catálogos + `resolve_dimension` + `resolve_metric_kind` | 187 |
| `distillery/payload_parser.py` | `parse_distillation_payload` + `enrich_knowledge_from_windows` | 298 |
| `distillery/prompt_builder.py` | `build_distillation_prompt` | 142 |

**Regra de manutenção por caso de uso:**

- Novo alias de dimension ou theme → só `catalog.py`
- Nova regra de extração de campo → só `field_parsers.py`
- Mudança no prompt → só `prompt_builder.py`
- Novo campo no payload do LLM → `payload_parser.py` + eventualmente `field_parsers.py`
- Lógica de orquestração ou CLI → só `distill_supervised_memory.py`

Nenhum desses casos exige tocar mais de um arquivo.

**Migrations**

 - python3 scripts/apply_migrations.py
 - python3 src/orion_mcp_v3/public_chat/scripts/apply_migrations.py
 - ||
 - python3 -m orion_mcp_v3.scripts.apply_migrations
 - python3 -m orion_mcp_v3.public_chat.scripts.apply_migrations