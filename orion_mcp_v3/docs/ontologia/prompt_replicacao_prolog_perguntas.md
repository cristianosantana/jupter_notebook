# Prompt: Replicação Independente em Prolog de uma Decisão do Runtime (Padrão Senna)

> Como usar: cole este prompt em uma sessão com acesso ao trace completo de um
> turno do `public_chat_pipeline` (os JSONL de log) e, se disponível, às
> linhas relevantes de `memory_curta`. Use uma pergunta por execução — o
> objetivo é produzir um script Prolog autocontido (`.pl`) que resolve a
> mesma pergunta **do zero, de forma independente**, sem chamar LLM, e que
> ao final compara o próprio veredito com o que o runtime realmente
> respondeu. Não é um auditor plugado no pipeline — é uma segunda
> implementação paralela, no espírito exato do exercício que o Fabrício
> Ceolin descreveu no caso Ayrton Senna.

---

## PROMPT

Você é um engenheiro de conhecimento construindo uma **segunda
implementação independente**, em Prolog, para resolver uma pergunta que o
Orion (sistema de analytics cognitivo do consumidor `chat_public`) já
respondeu via LLM. O objetivo não é auditar ou corrigir o pipeline em
produção — é reproduzir a cadeia de decisão inteira, ponto a ponto, com
fatos e regras explícitas, e comparar o veredito resultante com o veredito
real do runtime. Duas implementações autônomas, cada uma chegando à sua
própria resposta; a comparação só acontece no final.

### Insumos que você deve pedir, se não vierem anexados

1. O **trace completo do turno** (todas as etapas do JSONL: `intent.interpret`,
   `fact.plan`, `fact.resolve`, `fact.extract`, `workspace.build`,
   `narrator`) para o `trace_id` em questão.
2. As **linhas de `memory_curta`** relevantes para a pergunta — especialmente
   quando o dado já vem consolidado em formato `ranked_list` (nesse caso,
   prefira sempre essas linhas a reconstruir dado via `fact_keys`
   fragmentadas).
3. O **veredito real do runtime**: a resposta final dada ao usuário, a
   confiança relatada, e qualquer `fact_key` usada no caminho.

Se qualquer um desses insumos estiver ausente, pare e peça — não invente
dado de produção para preencher a base de fatos.

### O que você NÃO deve fazer

- **Não** tente reproduzir o `intent.interpret` como regra lógica. Ler texto
  livre em português é trabalho de linguagem, não de lógica de primeira
  ordem. A estruturação inicial da pergunta em fatos (qual é a operação,
  qual é a dimensão-alvo, quais períodos) é trabalho manual seu, feito uma
  vez, da mesma forma que o Ceolin estruturou manualmente as premissas
  jurídicas do caso Senna antes de escrever qualquer cláusula Prolog.
- **Não** crie um catálogo estático de domínio de valores por dimensão (do
  tipo `dominio(dimensao, [lista, fixa, de, valores])`) a menos que você
  tenha confirmado, nos dados reais, que aquela dimensão específica não tem
  variação de período a período. Uma auditoria anterior já mostrou que até
  dimensões aparentemente fechadas (como número de parcelas) variam de mês
  para mês — um domínio estático errado produz falso positivo de
  "cobertura incompleta" pior do que não ter a checagem.
- **Não** escreva uma regra específica para a dimensão da pergunta atual se
  a mesma regra puder ser escrita de forma agnóstica à dimensão. Prefira
  sempre a formulação genérica ("se a operação é de comparação sobre uma
  dimensão e o dado já existe consolidado em lista, use a lista") à
  formulação específica ("se a dimensão é X, faça Y").

### Estrutura do script Prolog a ser produzido

O arquivo `.pl` resultante deve ter estas seções, nesta ordem:

**1. Cabeçalho** — comentário explicando: qual pergunta está sendo
replicada, qual `trace_id` originou o exercício, qual foi o veredito real
do runtime (resumo de uma linha), e a declaração explícita de que este
script resolve o problema do zero, não audita decisão alheia.

**2. Fatos de estrutura da pergunta** — a tradução manual do
`IntentContract` real do turno em fatos Prolog: operação pedida (lookup,
ranking, comparação entre períodos, etc.), dimensão-alvo, períodos
envolvidos, e qualquer filtro de escopo que **não** seja da dimensão-alvo
(esses são legítimos e devem ser preservados; só o filtro que colide com a
própria dimensão-alvo é uma contradição a descartar — ver seção de regras).

**3. Fatos de dado observado** — os valores reais, extraídos das linhas de
`memory_curta` fornecidas. Priorize sempre dado já consolidado (`ranked_list`
com todas as entidades de um período) sobre dado fragmentado por entidade.
Se o dado necessário para resolver a pergunta do zero não estiver disponível
nos insumos fornecidos, declare os fatos faltantes explicitamente como
`nao_disponivel` (nunca invente valores) e siga em frente — o script deve
ser capaz de reportar "não posso responder com o dado que tenho", que é em
si um resultado válido e comparável.

**4. Fato do veredito real do runtime** — uma única cláusula de fato
(não uma regra) registrando o que o runtime respondeu de fato: valor(es),
confiança relatada, e qualquer ressalva que o runtime tenha incluído no
texto da resposta. Isso é o equivalente ao "veredito real de 1989" do caso
Senna — um dado histórico fixo, não recalculado.

**5. Regras determinísticas de resolução** — a cadeia de regras que
resolve a pergunta a partir dos fatos das seções 2 e 3, sem qualquer
inferência de linguagem. Isso tipicamente inclui:
   - Uma regra que descarta, por contradição estrutural, qualquer filtro de
     escopo cuja dimensão coincida com a dimensão-alvo de uma operação de
     comparação (independente de qual dimensão for).
   - Uma regra que calcula o que precisa ser calculado (variação
     percentual, soma, comparação, ranking) puramente a partir dos fatos de
     dado observado.
   - Uma regra de cobertura/suficiência: o veredito só é considerado
     completo se a base de comparação for suficiente (mais de um item
     comparável, sem indicação de truncamento no dado de origem); caso
     contrário, a regra deve falhar de forma explícita, retornando o motivo
     (não apenas `false`), listando o que está faltando.

**6. Regra de comparação dos dois veredictos** — uma cláusula final que
imprime, lado a lado: o veredito do runtime (fato da seção 4) e o veredito
Prolog (resultado das regras da seção 5), destacando se convergem ou
divergem, e — quando divergirem — por que, em linguagem derivada
diretamente da cadeia de regras que falhou ou teve resultado diferente
(o "caminho de justificativa" que é o ponto central do método
neurosimbólico).

**7. Bloco final de instruções de uso** — como rodar (`swipl arquivo.pl`,
qual consulta disparar), e quais fatos, se houver algum marcado
`nao_disponivel`, precisariam ser preenchidos manualmente (com a origem
exata de onde buscar: qual `context_key` de `memory_curta`, ou qual outra
fonte) para o script produzir um veredito completo.

### Critério de qualidade do resultado

Antes de entregar o script, verifique:

- Nenhuma regra ou fato menciona a dimensão específica da pergunta atual de
  forma hardcoded dentro de uma regra que poderia ser genérica — a
  dimensão deve aparecer só nos *fatos* (seção 2/3), nunca no corpo das
  *regras* (seção 5), a menos que exista uma razão de negócio genuína e
  documentada para tratar aquela dimensão como caso especial.
- Toda vez que um fato de dado observado não estiver disponível, ele está
  marcado como tal, não omitido silenciosamente — omissão silenciosa
  produz um veredito Prolog artificialmente "limpo" que não é comparável
  de verdade ao veredito do runtime.
- A regra de cobertura/suficiência (item 5, terceiro ponto) está presente
  mesmo que, para a pergunta específica em questão, a cobertura pareça
  óbvia — o valor do exercício está em generalizar para a próxima
  pergunta, não só resolver a atual.

---

## Notas de uso

- Rode este prompt uma vez por pergunta/turno que você quiser auditar dessa
  forma — cada execução produz um script isolado, específico daquele
  turno, mas escrito com regras reaproveitáveis.
- Depois de acumular alguns desses scripts, vale revisar as seções 5 (regras
  determinísticas) de cada um lado a lado — regras que se repetem
  idênticas entre scripts de perguntas diferentes são candidatas fortes a
  virar parte permanente do pipeline (nesse ponto, e só nesse ponto, faz
  sentido considerar mover a lógica para dentro do `fact.plan` ou do
  `FallbackPolicy` em produção).
- Este exercício continua sendo, por desenho, um script manual e isolado —
  não o integre ao runtime como parte deste prompt. Integração é uma
  decisão separada, a ser tomada depois de o padrão se repetir em múltiplas
  perguntas, não a partir de uma única replicação.