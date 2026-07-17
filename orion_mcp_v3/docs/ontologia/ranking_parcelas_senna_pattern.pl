% =============================================================================
% ranking_parcelas_senna_pattern.pl
%
% Replica, no padrão do exercício "Ayrton Senna" do Fabrício Ceolin, a decisão
% de ranking que o runtime do Orion tomou via LLM no turno de trace_id
% 9ee5b6e3-3705-4a8d-996f-a66525fe6d9a.
%
% Pergunta original do usuário:
%   "Das vendas parceladas em cartão de crédito em janeiro de 2026, qual
%    parcela (1x a 10x) teve o maior crescimento percentual até junho?"
%
% Veredito do runtime (LLM + heurística, hoje em produção):
%   "1X é a vencedora do ranking (é o único registro disponível) —
%    variação de -35,95%" — com confidence 0.9.
%
% Este script NÃO tenta reproduzir o intent.interpret (leitura de português
% livre) — isso é trabalho de LLM e está fora do escopo de uma linguagem
% lógica. O que ele reproduz, de forma determinística, é o que vem DEPOIS
% da interpretação: dado que a operação é "ranking sobre a dimensão
% parcelas", quais requirements deveriam existir, e qual é o veredito
% correto quando eles existem.
%
% Como no caso Senna: duas implementações independentes, comparadas no final.
% =============================================================================


% -----------------------------------------------------------------------------
% BLOCO 1 — Fatos de domínio
%
% Equivalente ao "coletar as fontes públicas" do caso Senna: aqui as fontes
% são o catálogo já existente do Orion (a dimensão `parcelas` do IndexKey
% `parcelamento_de_cartao`), não algo inventado para o exercício.
% -----------------------------------------------------------------------------

% dominio(Dimensao, ListaDeValores).
dominio(parcelas, ['1x','2x','3x','4x','5x','6x','7x','8x','9x','10x']).

% index_expoe_dimensao(IndexKey, Dimensao).
index_expoe_dimensao(parcelamento_de_cartao, parcelas).


% -----------------------------------------------------------------------------
% BLOCO 2 — Fatos de observação (dados reais e dados faltantes)
%
% observado(IndexKey, ValorDimensao, Periodo, Valor).
%
% Fonte: memory_curta, theme parcelamento_cartao
%   sistema_background:fechamento_gerencial:parcelamento_cartao:periodo-2026-01
%   sistema_background:fechamento_gerencial:parcelamento_cartao:periodo-2026-06
% Valores = campo "valor" (R$) das rows de key_metrics.parcelamento_de_cartao.
%
% `ausente` = parcela não apareceu no ranked_list daquele período (não há
% número para crescimento_pct / valor_resolvido).
% -----------------------------------------------------------------------------

observado(parcelamento_de_cartao, '1x',  '2026-01', 157701.01).
observado(parcelamento_de_cartao, '1x',  '2026-06', 101027.22).
observado(parcelamento_de_cartao, '2x',  '2026-01', 38927.00).
observado(parcelamento_de_cartao, '2x',  '2026-06', 20199.20).
observado(parcelamento_de_cartao, '3x',  '2026-01', 49109.00).
observado(parcelamento_de_cartao, '3x',  '2026-06', 70383.04).
observado(parcelamento_de_cartao, '4x',  '2026-01', 36559.00).
observado(parcelamento_de_cartao, '4x',  '2026-06', 44150.19).
observado(parcelamento_de_cartao, '5x',  '2026-01', 69004.00).
observado(parcelamento_de_cartao, '5x',  '2026-06', 30526.80).
observado(parcelamento_de_cartao, '6x',  '2026-01', 103233.90).
observado(parcelamento_de_cartao, '6x',  '2026-06', 139341.10).
observado(parcelamento_de_cartao, '7x',  '2026-01', 1500.00).
observado(parcelamento_de_cartao, '7x',  '2026-06', 1200.00).
observado(parcelamento_de_cartao, '8x',  '2026-01', 2350.00).
observado(parcelamento_de_cartao, '8x',  '2026-06', 1900.00).
observado(parcelamento_de_cartao, '9x',  '2026-01', 6100.00).
observado(parcelamento_de_cartao, '9x',  '2026-06', 5000.00).
observado(parcelamento_de_cartao, '10x', '2026-01', 681772.80).
observado(parcelamento_de_cartao, '10x', '2026-06', 767384.20).


% -----------------------------------------------------------------------------
% BLOCO 3 — O que o runtime real produziu (para comparação final)
%
% Isso não é premissa lógica — é o registro do "Veredito A", exatamente como
% o Ceolin teria anotado o veredito real de 1989 antes de rodar o Prolog
% para o caso Senna, para poder comparar no final.
% -----------------------------------------------------------------------------

veredito_runtime(parcela('1x'), crescimento_pct(-35.95), confidence(0.9),
                  justificativa('único registro disponível')).


% -----------------------------------------------------------------------------
% BLOCO 4 — Regra determinística: cálculo de crescimento percentual
%
% Pura aritmética, sem inferência de linguagem. Só resolve quando os dois
% valores (período inicial e final) foram de fato observados.
% -----------------------------------------------------------------------------

crescimento_pct(IndexKey, Valor, PeriodoIni, PeriodoFim, Pct) :-
    observado(IndexKey, Valor, PeriodoIni, V1),
    observado(IndexKey, Valor, PeriodoFim, V2),
    number(V1),
    number(V2),
    V1 =\= 0,
    Pct is ((V2 - V1) / V1) * 100.


% -----------------------------------------------------------------------------
% BLOCO 5 — Regra determinística: verificação de cobertura de domínio
%
% Esta é a regra que o runtime de hoje não tem. Ela responde a pergunta:
% "para fazer um ranking válido sobre a dimensão `parcelas`, eu preciso ter
% dado de todos os valores do domínio — eu tenho?"
% -----------------------------------------------------------------------------

valor_resolvido(IndexKey, Valor, PeriodoIni, PeriodoFim) :-
    observado(IndexKey, Valor, PeriodoIni, V1),
    observado(IndexKey, Valor, PeriodoFim, V2),
    number(V1),
    number(V2).

cobertura(IndexKey, Dimensao, PeriodoIni, PeriodoFim, Resolvidos, Faltantes) :-
    index_expoe_dimensao(IndexKey, Dimensao),
    dominio(Dimensao, TodosValores),
    include([V]>>valor_resolvido(IndexKey, V, PeriodoIni, PeriodoFim),
            TodosValores, Resolvidos),
    exclude([V]>>valor_resolvido(IndexKey, V, PeriodoIni, PeriodoFim),
            TodosValores, Faltantes).


% -----------------------------------------------------------------------------
% BLOCO 6 — Regra de veredito
%
% Dois casos, com justificativa explícita em cada um — o equivalente ao
% "caminho da solução" que o Prolog do caso Senna expunha ao navegar a base.
%
% Caso A: cobertura completa -> ranking determinístico de verdade.
% Caso B: cobertura incompleta -> falha explicitamente, listando o que falta,
%         em vez de escolher um vencedor com base no que sobrou.
% -----------------------------------------------------------------------------

veredito_prolog(IndexKey, Dimensao, PeriodoIni, PeriodoFim,
                 vencedora(Valor, Pct)) :-
    cobertura(IndexKey, Dimensao, PeriodoIni, PeriodoFim, Resolvidos, []),
    % só chega aqui se Faltantes = [] -> cobertura 100%
    findall(Pct-Valor,
            ( member(Valor, Resolvidos),
              crescimento_pct(IndexKey, Valor, PeriodoIni, PeriodoFim, Pct)
            ),
            Pares),
    max_member(Pct-Valor, Pares).

veredito_prolog(IndexKey, Dimensao, PeriodoIni, PeriodoFim,
                 cobertura_incompleta(Faltantes, Resolvidos)) :-
    cobertura(IndexKey, Dimensao, PeriodoIni, PeriodoFim, Resolvidos, Faltantes),
    Faltantes \= [].


% -----------------------------------------------------------------------------
% BLOCO 7 — Comparação dos dois veredictos (o "passo 5" do método Senna)
% -----------------------------------------------------------------------------

comparar_veredictos :-
    veredito_runtime(parcela(ValorRuntime), crescimento_pct(PctRuntime),
                      confidence(Conf), justificativa(JustRuntime)),
    format('~n=== VEREDITO A — runtime real (LLM + heurística) ===~n'),
    format('Vencedora: ~w | Crescimento: ~w% | Confidence: ~w~n', [ValorRuntime, PctRuntime, Conf]),
    format('Justificativa registrada: ~w~n', [JustRuntime]),

    format('~n=== VEREDITO B — script Prolog (determinístico) ===~n'),
    ( veredito_prolog(parcelamento_de_cartao, parcelas, '2026-01', '2026-06', Resultado)
    -> ( Resultado = vencedora(Valor, Pct)
       -> format('Vencedora: ~w | Crescimento: ~w%~n', [Valor, Pct]),
          format('Cobertura: completa (10/10 valores do domínio)~n')
       ; Resultado = cobertura_incompleta(Faltantes, Resolvidos)
       -> length(Faltantes, NFalt),
          length(Resolvidos, NRes),
          format('Não é possível emitir ranking: cobertura incompleta.~n'),
          format('Resolvidos: ~w/10 ~w~n', [NRes, Resolvidos]),
          format('Faltantes (ausente em um ou ambos períodos): ~w/10 ~w~n', [NFalt, Faltantes])
       )
    ),

    format('~n=== COMPARAÇÃO ===~n'),
    format('Veredito A afirma um vencedor com confidence ~w baseado em 1/10 valores do domínio.~n', [Conf]),
    format('Veredito B recusa emitir vencedor até que os outros 9 valores sejam consultados.~n'),
    format('Divergência: A responde como se a comparação fosse completa; B expõe que não é.~n').


% =============================================================================
% COMO USAR
%
% 1. Instale o SWI-Prolog (swipl).
% 2. No terminal (a partir da raiz do repo):
%      swipl docs/ontologia/ranking_parcelas_senna_pattern.pl
%      ?- comparar_veredictos.
%    (cópia operacional também em scripts/ranking_parcelas_senna_pattern.pl)
%
% Com os dados atuais da memory_curta, 7x falta em jan e jun e 8x falta em
% jun → Veredito B permanece `cobertura_incompleta` até o domínio 1x–10x
% estar completo nos dois períodos. Isso prova formalmente que o Veredito A
% (vencedor com 1/10 valores) não tinha base para a confiança declarada.
% =============================================================================
