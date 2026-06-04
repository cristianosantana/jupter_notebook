# Query Modules

Este diretório contém módulos de query SQL descobertos automaticamente pelo broker.
Cada arquivo Python com uma variável `SQL` vira um `QueryTemplate` registrado em
`ANALYTICS_TEMPLATES`.

O fluxo principal é:

1. `broker.queries.__init__` importa os módulos deste diretório.
2. `broker.query_templates._build_registry()` transforma cada módulo em `QueryTemplate`.
3. `broker.evidence_series_resolve.resolve_evidence_series_specs()` usa o template para decidir quais colunas das linhas SQL representam valor, tempo e label.
4. `broker.evidence_aggregator.EvidenceAggregator` passa as linhas e essas chaves para `EvidenceBuilder`.
5. `EvidenceBuilder` transforma `rows` em `EvidenceBlock` para o orquestrador/narrador.

## Contrato De Um Modulo

Um módulo de query expõe metadados simples em variáveis globais. Exemplo:

```python
VALUE_KEY = "total_comissao"
TIME_KEY = None
GRAIN = "month"
LABEL_KEY = "concessionaria"
DEFAULT_MEASURE = "total_comissao"
DEFAULT_DIMENSION = "concessionaria"
MEASURES = {
    "total_comissao": {
        "label": "total de comissao",
        "kind": "money",
        "synonyms": ("comissao", "comissao total", "total comissao", "comissoes"),
        "additive": True,
    },
}
```

Essas variáveis não são apenas documentação: elas orientam como o resultado SQL será
interpretado antes de virar evidência.

## Variaveis Principais

### `SQL`

String SQL parametrizada com placeholders `%s`.

As colunas selecionadas com alias (`AS ...`) são o contrato real entre a query e o
resto do pipeline. Variáveis como `VALUE_KEY`, `TIME_KEY`, `LABEL_KEY`, `MEASURES`
e `DIMENSIONS` devem apontar para aliases presentes no `SELECT`.

### `ANSWERS`

Tupla de frases que descrevem perguntas respondidas pela query.

O registry usa essas frases para pontuar qual template combina melhor com o
`CognitivePlan` e com a pergunta original. Quanto mais próximas do vocabulário do
usuário, maior a chance de o template correto ser escolhido.

### `VALUE_KEY`

Coluna numérica principal da query.

É o valor padrão usado pelo `EvidenceBuilder` para calcular baseline, variação,
tendência, ranking, concentração, anomalias, cobertura e confiança. No exemplo
`fechamento_faturamento_comissao_concessionaria_periodo.py`,
`VALUE_KEY = "total_comissao"` significa que a evidência principal será construída
sobre a coluna `total_comissao`.

Quando a pergunta seleciona outra métrica em `MEASURES`, o pipeline pode substituir
o `VALUE_KEY` pelo `column` da métrica selecionada.

### `TIME_KEY`

Coluna temporal da query, ou `None` quando o resultado não tem série temporal.

Quando preenchido, o `EvidenceBuilder` usa essa coluna para montar série temporal,
comparar períodos e inferir cobertura de período. Quando `None`, a evidência ainda
pode gerar ranking, baseline e anomalias, mas não terá tendência temporal derivada
das linhas.

### `GRAIN`

Granularidade temporal declarada para `TIME_KEY`.

Valores comuns:

- `"day"`: linhas agrupadas por dia.
- `"month"`: linhas agrupadas por mês ou usadas em fechamento mensal.
- `"total"`: resultado agregado sem período relevante.

Se `TIME_KEY` for `None`, o `GRAIN` fica como metadado do template, mas não gera
série temporal no `EvidenceBuilder`.

### `LABEL_KEY`

Coluna categórica principal da query.

É usada para rankings e agrupamentos legíveis. No exemplo
`fechamento_faturamento_comissao_concessionaria_periodo.py`,
`LABEL_KEY = "concessionaria"` faz o builder somar `VALUE_KEY` por concessionária
e produzir ranking/dominância.

Quando não há dimensão categórica, use `None`.

### `DEFAULT_MEASURE`

Métrica padrão para projeção de resposta direta.

Ela aponta para uma chave em `MEASURES`. Se o usuário pedir algo genérico como
"ranking" ou "liste por concessionária", essa métrica será usada quando nenhuma
outra métrica for identificada com mais precisão.

### `DEFAULT_DIMENSION`

Dimensão padrão para projeção de resposta direta.

Ela aponta para uma chave em `DIMENSIONS`. É a dimensão usada quando a pergunta não
declara outra dimensão. Normalmente é igual a `LABEL_KEY`.

### `MEASURES`

Dicionário de métricas que a query consegue responder.

Cada entrada representa uma medida numérica disponível nas linhas SQL. A chave da
entrada geralmente é o alias da coluna, mas pode apontar para outro alias via
`column`.

Campos aceitos:

- `column`: alias real da coluna no SQL. Opcional; se ausente, usa a própria chave.
- `label`: nome humano usado em respostas.
- `kind`: tipo de valor, por exemplo `"money"`, `"number"`, `"percent"` ou `"count"`.
- `synonyms`: termos que ajudam o seletor a mapear a pergunta do usuário para essa métrica.
- `additive`: indica se a métrica pode ser somada entre linhas.
- `sortable`: indica se a métrica pode ser usada em ranking/ordenação.

Exemplo: se a query retorna `total`, `total_comissao` e o usuário pergunta por
"comissão", os sinônimos de `total_comissao` ajudam o pipeline a escolher essa
métrica em vez de `total`.

### `DIMENSIONS`

Dicionário de dimensões que a query consegue usar para agrupar, filtrar ou listar.

Cada entrada representa uma coluna categórica ou temporal disponível nas linhas SQL.

Campos aceitos:

- `column`: alias real da coluna no SQL. Opcional; se ausente, usa a própria chave.
- `label`: nome humano da dimensão.
- `synonyms`: termos que ajudam o seletor a mapear a pergunta do usuário para essa dimensão.

### `SUPPORTED_OPERATIONS`

Operações de resposta direta permitidas para a query.

Valores comuns:

- `"ranking_desc"`: ranking do maior para o menor.
- `"ranking_asc"`: ranking do menor para o maior.
- `"top_and_bottom"`: maior e menor no mesmo resultado.
- `"list"`: listagem dos registros/projeções.

Essas operações são usadas pelo `answer_projector` antes da narração pelo LLM.

### `DEFAULT_PARAMS`

Parâmetros padrão extras para o SQL.

`date_from` e `date_to` são adicionados automaticamente pelo registry. Use
`DEFAULT_PARAMS` para outros filtros opcionais, como `business_unit_id` ou
`tipo_grupo_servico`.

### `PARAMETERS`

Ordem dos parâmetros que serão aplicados nos placeholders `%s` do `SQL`.

Essa tupla deve ter a mesma ordem e quantidade lógica dos placeholders. Quando o
mesmo valor aparece várias vezes no SQL, repita o nome na tupla.

Exemplo:

```python
PARAMETERS = (
    "date_from",
    "date_to",
    "business_unit_id",
    "business_unit_id",
)
```

## Contrato Geral Vs Dominio

O contrato de evidência é geral: todo módulo acaba produzindo um `EvidenceBlock`.
O que é específico por domínio é o mapeamento das colunas da query.

- `EvidenceBlock` define a forma final da evidência: `summary`, `insights`,
  `metrics`, `confidence`, `coverage`, `provenance`, `sample_refs` e
  `supporting_data`.
- `EvidenceSeriesSpec` define como interpretar as linhas de uma query específica:
  qual coluna é valor (`value_key`), tempo (`time_key`), label (`label_key`), id
  (`id_key`) e tipo (`value_kind`).
- Cada módulo deste diretório fornece os metadados que alimentam essa
  `EvidenceSeriesSpec`.

Na prática: o domínio mora nos módulos de query; a transformação em evidência é
genérica.

## Como Adicionar Constantes Novas

Antes de criar uma constante nova, separe dois casos:

1. A informação cabe em uma constante já suportada, como `MEASURES`,
   `DIMENSIONS`, `DEFAULT_PARAMS` ou `SUPPORTED_OPERATIONS`.
2. A informação precisa virar um novo campo do contrato usado pela evidência.

No primeiro caso, normalmente basta alterar o módulo em `broker/queries/`. No
segundo, também é preciso ensinar o pipeline a carregar, transportar e consumir a
nova constante.

### Caso 1: Nova Metrica Ou Dimensao

Para adicionar uma nova métrica, adicione um alias no `SELECT` e uma entrada em
`MEASURES`:

```python
SQL = """\
SELECT
    conc.nome AS concessionaria,
    ROUND(SUM(com.valor_dentro), 2) AS total_comissao_interna
...
"""

MEASURES = {
    "total_comissao_interna": {
        "label": "comissao interna",
        "kind": "money",
        "synonyms": ("comissao interna", "interno", "valor dentro"),
        "additive": True,
    },
}
```

Se a chave de `MEASURES` não for o alias real da coluna, informe `column`:

```python
MEASURES = {
    "comissao_interna": {
        "column": "total_comissao_interna",
        "label": "comissao interna",
        "kind": "money",
        "synonyms": ("comissao interna",),
        "additive": True,
    },
}
```

Para adicionar uma nova dimensão, adicione uma entrada em `DIMENSIONS` apontando
para uma coluna retornada pela query:

```python
DIMENSIONS = {
    "concessionaria": {
        "label": "concessionaria",
        "synonyms": ("concessionaria", "loja"),
    },
    "tipo_servico": {
        "label": "tipo de servico",
        "synonyms": ("tipo de servico", "grupo de servico"),
    },
}
```

Essas alterações já são usadas por `_build_capability()` em
`broker.query_templates`. Elas afetam a projeção de resposta direta e podem afetar
o `EvidenceSeriesSpec.value_key` quando o seletor escolhe uma métrica específica
via `selected_metric`.

### Caso 2: Nova Constante Que Deve Entrar No `EvidenceSeriesSpec`

Se a nova constante muda como o `EvidenceBuilder` interpreta as linhas, ela precisa
entrar no caminho do `EvidenceSeriesSpec`.

Exemplo: suponha que você queira adicionar `ID_KEY` por query para trocar o
identificador usado em exemplos de anomalias.

Passos necessários:

1. Declare a constante no módulo de query:

```python
ID_KEY = "caixa_tipo_id"
```

2. Adicione o campo ao `QueryTemplate` em `broker/query_templates.py`:

```python
@dataclass(frozen=True, slots=True)
class QueryTemplate:
    ...
    id_key: str | None = None
```

3. Carregue a constante em `_build_registry()`:

```python
reg.register(QueryTemplate(
    ...
    id_key=getattr(mod, "ID_KEY", None),
))
```

4. Adicione o campo em `contracts/evidence_series_spec.py` se ele ainda não
existir:

```python
@dataclass(frozen=True, slots=True)
class EvidenceSeriesSpec:
    ...
    id_key: str | None = "id"
```

5. Copie o valor do template em
`broker/evidence_series_resolve.resolve_evidence_series_specs()`:

```python
EvidenceSeriesSpec(
    ...
    id_key=tpl.id_key if tpl.id_key is not None else default_id_key,
)
```

6. Garanta que `EvidenceAggregator` passa o campo para `EvidenceBuilder.build()`.
Hoje ele já repassa `id_key`, `value_key`, `value_kind`, `label_key`, `time_key` e
`grain`.

7. Se a constante for uma informação nova que o `EvidenceBuilder` ainda não usa,
adicione um parâmetro em `EvidenceBuilder.build()` e implemente o consumo ali.
Sem essa etapa, o campo pode até viajar no contrato, mas não muda a evidência.

### Mapa De Uso Atual

As constantes atuais chegam ao `EvidenceSeriesSpec` assim:

- `VALUE_KEY` vira `QueryTemplate.value_key` e depois `EvidenceSeriesSpec.value_key`.
- `TIME_KEY` vira `QueryTemplate.time_key` e depois `EvidenceSeriesSpec.time_key`.
- `GRAIN` vira `QueryTemplate.grain` e depois `EvidenceSeriesSpec.grain`.
- `LABEL_KEY` vira `QueryTemplate.label_key` e depois `EvidenceSeriesSpec.label_key`.
- `MEASURES[*].kind` pode virar `EvidenceSeriesSpec.value_kind` quando a métrica é selecionada.
- `MEASURES[*].column` pode substituir `VALUE_KEY` quando a métrica selecionada aponta para outro alias.
- `DEFAULT_MEASURE`, `DEFAULT_DIMENSION`, `DIMENSIONS` e `SUPPORTED_OPERATIONS`
  alimentam `AnswerCapability`; eles impactam a resposta direta, mas não viram
  campos próprios do `EvidenceSeriesSpec`.
- `DEFAULT_PARAMS` e `PARAMETERS` afetam a execução SQL; eles não entram na
  evidência diretamente.

Regra prática: se a constante muda apenas seleção, filtros, operação ou texto da
resposta direta, ela provavelmente pertence a `AnswerCapability`. Se ela muda o
modo como as linhas viram baseline, ranking, tendência, anomalia ou cobertura, ela
precisa passar pelo `EvidenceSeriesSpec` e pelo `EvidenceBuilder`.

## Checklist Para Nova Query

Ao adicionar uma nova query:

1. Garanta que todos os aliases usados em `VALUE_KEY`, `TIME_KEY`, `LABEL_KEY`,
   `MEASURES` e `DIMENSIONS` existem no `SELECT`.
2. Defina `ANSWERS` com frases reais que usuários usariam.
3. Escolha `VALUE_KEY` como a métrica principal mais segura para narrar.
4. Use `TIME_KEY = None` se a query não retorna período por linha.
5. Declare `MEASURES` para todas as métricas que o usuário pode pedir.
6. Declare `DIMENSIONS` para todas as dimensões que podem aparecer em filtros,
   rankings ou listagens.
7. Revise `PARAMETERS` sempre que adicionar/remover placeholders `%s`.
