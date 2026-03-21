# Maestro: processos (código) e pergunta via API

Este documento descreve as **formas de montar o contexto de dados** e como **`MaestroService.run`** / **`POST /pergunta`** se relacionam com [`executar_fluxo_maestro`](../app/services/maestro_fluxo.py).

---

## Visão geral do fluxo

1. O Maestro analisa a pergunta (LLM com skill `maestro`).
2. Invoca cada `agente` listado:
   - **Modo conhecimento:** sem `df_contexto` ou agente fora de `agentes_dataframe`.
   - **Modo DataFrame (2 fases):** agente em `agentes_dataframe` **e** `df_contexto` montado — FASE 1 (`perguntas_dados`) → executor agrega → FASE 2 interpreta.
3. Envia respostas ao avaliador e devolve a entrega final.

Para um agente entrar em **modo DataFrame**, é obrigatório: `skill_id in agentes_dataframe` **e** `df_contexto` não nulo (ver abaixo).

---

## Origem do `df_contexto` (prioridade)

| Ordem | Condição | Efeito |
|-------|----------|--------|

| 1 | `mysql_tabelas` ou `mysql_tabela` definidos | Carrega do MySQL, injeta no `mysql_injetar_namespace` (se informado), monta `df_contexto`. **Ignora** o ramo `dataframe_preexistente` para montagem do contexto. |
| 2 | Sem MySQL no request, mas `dataframe_preexistente` é uma string não vazia | Monta `df_contexto` a partir do objeto referenciado em `mysql_injetar_namespace[nome]`. |
| 3 | Nenhum dos dois | `df_contexto` permanece `None`; agentes em `agentes_dataframe` **não** rodam em 2 fases com dados tabulares. |

**Executor:** as métricas leem o DataFrame em `mysql_injetar_namespace[df_variavel]` (ou `globals()` se namespace for `None`). O nome da variável vem de `df_contexto["df_variavel"]` (igual ao `dataframe_preexistente` ou ao nome retornado pelo load MySQL).

---

## Processo em Python — `MaestroService.run`

Chamada típica:

```python
from app.services.maestro_service import MaestroService

maestro = MaestroService(client=client, settings=settings)
resultado = maestro.run(
    pergunta="…",
    agentes=["agente_analise_os"],
    agentes_dataframe=["agente_analise_os"],
    # dados — escolha UM caminho coerente (MySQL OU DF em memória), vide prioridade acima
    mysql_tabelas=[…],           # opcional
    mysql_tabela=None,
    mysql_injetar_namespace=…,   # dict onde está o DataFrame (obrigatório para DF em memória)
    dataframe_preexistente="df_os",  # opcional — nome da chave no namespace
    verbose=True,
)
```

### Parâmetros relevantes (resumo)

| Parâmetro | Função |
|-----------|--------|

| `pergunta` | Texto enviado ao Maestro e aos agentes. |
| `agentes` | Lista de skill IDs a invocar. |
| `agentes_dataframe` | Quais desses IDs usam modo 2 fases quando há `df_contexto`. |
| `model` | Modelo OpenAI (default nas settings). |
| `mysql_*` | Credenciais e carga (`mysql_tabela` ou `mysql_tabelas`, `mysql_limite`, `mysql_filtro_where`). |
| `mysql_injetar_namespace` | Dict Python onde o load MySQL **ou** o código coloca o `DataFrame`. |
| `dataframe_preexistente` | Nome (string) da variável no `mysql_injetar_namespace`; usado só se **não** houver `mysql_tabelas`/`mysql_tabela`. |
| `skills_dir` | Pasta das skills (default nas settings). |
| `**kwargs` | Repassados a `executar_fluxo_maestro` (ex.: `skills_list` pré-carregada). |

### Cenários em processo

1. **Só MySQL**  
   `mysql_tabelas` (ou `mysql_tabela`) + `mysql_injetar_namespace=globals()` (ou outro dict).  
   Opcional: `dataframe_preexistente` **omitido** — o contexto usa o nome gerado pelo agente MySQL (ex.: `df_os`).

2. **Só DataFrame já carregado (sem nova query)**  
   Sem `mysql_tabelas`/`mysql_tabela`.  
   `mysql_injetar_namespace` apontando para o dict que contém o `DataFrame`, e `dataframe_preexistente="nome_da_chave"`.

3. **MySQL e `dataframe_preexistente` no mesmo `run`**  
   Válido apenas na prática se quiser injetar o resultado do MySQL no mesmo dict; **a montagem do contexto segue o caminho MySQL** (prioridade 1). O nome em `df_contexto` será o definido pelo carregamento, não necessariamente `dataframe_preexistente`.

4. **Sem dados**  
   Agentes só em modo conhecimento; a lista `agentes_dataframe` não ativa modo tabular sem `df_contexto`.

---

## Pergunta via API — `POST /pergunta`

Rota: conforme registro do router (ex.: `/pergunta`).

### Corpo (`PerguntaRequest`)

| Campo | Tipo | Descrição |
|-------|------|-----------|

| `pergunta` | string (obrigatório) | Pergunta ao Maestro. |
| `agentes` | lista de strings | Skill IDs. |
| `agentes_dataframe` | lista de strings | IDs que devem operar em 2 fases quando há `df_contexto`. |
| `mysql_tabela` | string opcional | Uma tabela (fluxo MySQL simples). |
| `mysql_tabelas` | lista de dicts opcional | Definição multi-tabela (joins). |
| `mysql_limite` | int | Limite de linhas no load. |
| `mysql_filtro_where` | string | Cláusula SQL adicional. |
| `dataframe_preexistente` | string opcional | Nome registrado em [`maestro_df_registry`](../app/services/maestro_df_registry.py). |
| `verbose` | bool | Logs do fluxo. |

### DataFrame em memória na API

O JSON **não** transporta `DataFrame`. Fluxo:

1. No **mesmo processo** do servidor, registre antes da chamada:

   ```python
   from app.services.maestro_df_registry import register

   register("df_os", dataframe_pandas)
   ```

2. Chame `POST /pergunta` com `dataframe_preexistente: "df_os"` e `agentes_dataframe` preenchido.

3. A rota obtém `get_namespace()`, valida que `"df_os"` existe; caso contrário responde **400** com mensagem explicando o `register`.

4. `mysql_injetar_namespace` enviado ao `maestro.run` é esse namespace compartilhado **somente quando** `dataframe_preexistente` veio no body.

### Exemplos de corpo JSON

#### Agregação: soma de serviços com pagamento confirmado — concessionária Osaka (Fev/2026)

Pergunta direcionada a `agente_dados` e `agente_financeiro`, com join em `os`, `os_servicos`, `concessionarias` e filtro por nome da concessionária + `EXISTS` em `caixas` (pagamentos no período indicado).

```json
{
  "agentes": [
    "agente_dados",
    "agente_financeiro"
  ],
  "pergunta": "Soma única do valor de serviços de OS que possuem pagamentos confirmados na Osaka em Fev/2026.",
  "mysql_tabelas": [
    {
      "tabela": "os",
      "alias": "os"
    },
    {
      "tabela": "os_servicos",
      "alias": "oss",
      "fk": "os.id = oss.os_id",
      "colunas": [
        "SUM(oss.valor_venda_real) AS faturamento_correto"
      ]
    },
    {
      "tabela": "concessionarias",
      "alias": "con",
      "fk": "os.concessionaria_id = con.id"
    }
  ],
  "mysql_filtro_where": "con.nome LIKE '%Osaka%' AND os.deleted_at IS NULL AND EXISTS (SELECT 1 FROM caixas cx WHERE cx.os_id = os.id AND cx.created_at BETWEEN '2025-12-01' AND '2026-02-28' AND cx.cancelado = 0 AND cx.deleted_at IS NULL)",
  "mysql_limite": 10000
}
```

*(Ajuste o intervalo em `mysql_filtro_where` conforme o mês/ano desejado; valide se o agente MySQL do projeto aceita `SUM` nas `colunas` do join — o contrato SQL interno pode exigir variantes.)*

#### Mix de serviços: mais lucrativo vs mais popular

`agente_dados` + `agente_negocios`, com `servico_nome` e `concessionaria_nome` no resultado.

```json
{
  "agentes": [
    "agente_dados",
    "agente_negocios"
  ],
  "pergunta": "qual o servico mais lucrativo e qual o mais popular?",
  "mysql_limite": 10000,
  "mysql_filtro_where": "os.deleted_at IS NULL",
  "verbose": true,
  "mysql_tabelas": [
    {
      "tabela": "os",
      "alias": "os"
    },
    {
      "tabela": "os_servicos",
      "alias": "oss",
      "fk": "os.id = oss.os_id"
    },
    {
      "tabela": "servicos",
      "alias": "ser",
      "fk": "oss.servico_id = ser.id",
      "colunas": [
        "ser.nome AS servico_nome"
      ]
    },
    {
      "tabela": "concessionarias",
      "alias": "con",
      "fk": "os.concessionaria_id = con.id",
      "colunas": [
        "con.nome AS concessionaria_nome"
      ]
    }
  ]
}
```

**Com MySQL genérico (agente_analise_os, modo DataFrame):**

```json
{
  "pergunta": "Análise semanal de Ordens de Serviço",
  "agentes": ["agente_analise_os"],
  "agentes_dataframe": ["agente_analise_os"],
  "mysql_tabelas": [],
  "mysql_limite": 50000,
  "mysql_filtro_where": "os.deleted_at IS NULL",
  "verbose": true
}
```

*(Preencha `mysql_tabelas` com a mesma estrutura usada [nos exemplos acima](#exemplos-de-corpo-json) ou no notebook.)*

**Com DataFrame já registrado no processo:**

```json
{
  "pergunta": "Resumo executivo e top concessionárias",
  "agentes": ["agente_analise_os"],
  "agentes_dataframe": ["agente_analise_os"],
  "dataframe_preexistente": "df_os",
  "verbose": true
}
```

**Somente agentes em modo conhecimento (sem tabelas e sem `dataframe_preexistente`):**

```json
{
  "pergunta": "Explique o conceito de ticket médio em oficinas",
  "agentes": ["agente_negocios"],
  "verbose": false
}
```

### Resposta (`PerguntaResponse`)

Inclui `analise`, `respostas_agentes`, `avaliacao`, `entrega_final` — mesmo formato retornado pelo fluxo interno (campos podem ser expandidos no schema conforme necessidade).

---

## Referências no repositório

| Artefato | Caminho |
|----------|---------|

| Serviço | [`app/services/maestro_service.py`](../app/services/maestro_service.py) |
| Fluxo + executor | [`app/services/maestro_fluxo.py`](../app/services/maestro_fluxo.py) |
| Registry HTTP / multi-request | [`app/services/maestro_df_registry.py`](../app/services/maestro_df_registry.py) |
| Schema API | [`app/api/schemas/pergunta.py`](../app/api/schemas/pergunta.py) |
| Rota | [`app/api/routes/pergunta.py`](../app/api/routes/pergunta.py) |

---

## Notas

- **Worker / jobs:** jobs que repassam `kwargs` para `maestro.run` podem incluir `dataframe_preexistente` desde que o processo tenha o DataFrame no **mesmo** dict usado como `mysql_injetar_namespace` (registry ou outro).
- **Segurança:** `maestro_df_registry` é compartilhado no processo; restrinja quem pode chamar `register` e valide nomes em ambientes multi-tenant.
