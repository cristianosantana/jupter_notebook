% rules_lib.pl — motor B genérico (agnóstico à dimensão).
% Dimensão e períodos aparecem só nos fatos do case gerado.
% Operações: period_growth, period_decline, ranking_desc, ranking_asc,
%            leader_change, cumulative, time_series.

:- dynamic
    operacao/1,
    dimensao_alvo/1,
    periodo/1,
    index_key/1,
    scope_filter/2,
    operand_label/1,
    observado/4,
    nao_disponivel/3,
    truncated/1,
    veredito_runtime/4.

:- discontiguous veredito_b/1.

% --- sanitize: filtro cuja dimensão = dimensão-alvo é contradição estrutural ---

filtro_valido(Dim, _Valor) :-
    dimensao_alvo(Alvo),
    Dim \== Alvo.

filtros_escopo_sanitizados(Filtros) :-
    findall(Dim-Valor,
            ( scope_filter(Dim, Valor),
              filtro_valido(Dim, Valor)
            ),
            Filtros).

% --- crescimento percentual entre dois períodos (interseção de labels) ---

crescimento_pct(IndexKey, Label, PeriodoIni, PeriodoFim, Pct) :-
    observado(IndexKey, Label, PeriodoIni, V1),
    observado(IndexKey, Label, PeriodoFim, V2),
    number(V1),
    number(V2),
    V1 =\= 0,
    Pct is ((V2 - V1) / V1) * 100.

labels_comparaveis(IndexKey, PeriodoIni, PeriodoFim, Labels) :-
    findall(L,
            ( observado(IndexKey, L, PeriodoIni, V1),
              number(V1),
              observado(IndexKey, L, PeriodoFim, V2),
              number(V2)
            ),
            Raw),
    sort(Raw, Labels).

periodos_ordenados(P1, P2) :-
    findall(P, periodo(P), Ps0),
    sort(Ps0, Ps),
    Ps = [P1 | _],
    last(Ps, P2),
    P1 \== P2.

% Ranking cross-entity exige 2+ labels. Query escopada (operand_label/1)
% aceita 1 label — ex.: "variação do Cartão entre jan e jun".
cobertura_suficiente(Labels) :-
    \+ truncated(true),
    length(Labels, N),
    ( N > 1
    ; N =:= 1,
      findall(OL, operand_label(OL), Ops),
      Ops \= []
    ).

% --- veredito B: period_growth (maior alta) / period_decline (maior queda) ---

veredito_b(vencedora(Label, Pct)) :-
    ( operacao(period_growth) ; operacao(period_decline) ),
    index_key(IK),
    periodos_ordenados(P1, P2),
    labels_comparaveis(IK, P1, P2, Labels),
    cobertura_suficiente(Labels),
    findall(Pct0-Label0,
            ( member(Label0, Labels),
              crescimento_pct(IK, Label0, P1, P2, Pct0)
            ),
            Pares),
    Pares \= [],
    ( operacao(period_growth)
    -> max_member(Pct-Label, Pares)
    ;  min_member(Pct-Label, Pares)
    ).

veredito_b(cobertura_incompleta(Labels)) :-
    ( operacao(period_growth) ; operacao(period_decline) ),
    index_key(IK),
    periodos_ordenados(P1, P2),
    labels_comparaveis(IK, P1, P2, Labels),
    \+ cobertura_suficiente(Labels).

% --- veredito B: ranking_desc / ranking_asc (um período) ---

veredito_b(vencedora(Label, Valor)) :-
    ( operacao(ranking_desc) ; operacao(ranking_asc) ),
    index_key(IK),
    periodo(Periodo),
    findall(V-L,
            ( observado(IK, L, Periodo, V),
              number(V)
            ),
            Pares),
    length(Pares, N),
    N > 1,
    \+ truncated(true),
    ( operacao(ranking_desc)
    -> max_member(Valor-Label, Pares)
    ;  min_member(Valor-Label, Pares)
    ).

veredito_b(cobertura_incompleta(Labels)) :-
    ( operacao(ranking_desc) ; operacao(ranking_asc) ),
    index_key(IK),
    periodo(Periodo),
    findall(L, (observado(IK, L, Periodo, V), number(V)), Labels0),
    sort(Labels0, Labels),
    ( length(Labels, N), N =< 1
    ; truncated(true)
    ).

% --- veredito B: leader_change (RANK top=1 por período, nunca growth) ---
%
% "Quem foi o líder no período X, e ele se manteve líder no período Y?"
% NÃO é period_growth: o vencedor é decidido por valor absoluto MÁXIMO em
% cada período, isoladamente — nunca pela variação percentual entre os dois
% valores de uma mesma entidade. Regra separada por design, para impedir que
% o motor caia de volta em crescimento_pct/3 quando há 2 períodos + ranking.
% Convenção: Label/Valor reportados = líder do período mais recente (P2);
% "mudou de líder" é auditável comparando o líder de P1 com o de P2.

lider_do_periodo(IndexKey, Periodo, Label, Valor) :-
    findall(V-L,
            ( observado(IndexKey, L, Periodo, V),
              number(V)
            ),
            Pares),
    Pares \= [],
    max_member(Valor-Label, Pares).

veredito_b(vencedora(Label, Valor)) :-
    operacao(leader_change),
    index_key(IK),
    periodos_ordenados(P1, P2),
    findall(L1, (observado(IK, L1, P1, V1), number(V1)), LabelsP1),
    findall(L2, (observado(IK, L2, P2, V2), number(V2)), LabelsP2),
    sort(LabelsP1, SortedP1),
    sort(LabelsP2, SortedP2),
    length(SortedP1, N1),
    length(SortedP2, N2),
    N1 > 1,
    N2 > 1,
    \+ truncated(true),
    lider_do_periodo(IK, P1, _LiderP1, _ValorP1),
    lider_do_periodo(IK, P2, Label, Valor).

veredito_b(cobertura_incompleta(Labels)) :-
    operacao(leader_change),
    index_key(IK),
    periodos_ordenados(P1, P2),
    findall(L1, (observado(IK, L1, P1, V1), number(V1)), LabelsP1),
    findall(L2, (observado(IK, L2, P2, V2), number(V2)), LabelsP2),
    sort(LabelsP1, SortedP1),
    sort(LabelsP2, SortedP2),
    append(SortedP1, SortedP2, Labels0),
    sort(Labels0, Labels),
    ( length(SortedP1, N1), N1 =< 1
    ; length(SortedP2, N2), N2 =< 1
    ; truncated(true)
    ).

% --- veredito B: cumulative (soma em todos os períodos) ---
%
% Acumula observados por label em TODOS os periodo/1. Cobertura exige que
% cada período tenha valor numérico para o label. Com 2+ labels no escopo
% do index, o Veredito B reporta a diferença (primeiro-segundo por ordem
% lexicográfica de label_norm) — alinhado a "diferença entre totais".

periodos_todos(Periodos) :-
    findall(P, periodo(P), Ps0),
    sort(Ps0, Periodos),
    Periodos \= [].

acumulado_label(IndexKey, Label, Total) :-
    periodos_todos(Periodos),
    findall(V,
            ( member(P, Periodos),
              observado(IndexKey, Label, P, V),
              number(V)
            ),
            Valores),
    length(Periodos, NPeriodos),
    length(Valores, NValores),
    NValores =:= NPeriodos,
    sum_list(Valores, Total).

labels_com_cobertura_completa(IndexKey, Labels) :-
    findall(L,
            ( observado(IndexKey, L, _P, V),
              number(V),
              acumulado_label(IndexKey, L, _T)
            ),
            Raw),
    sort(Raw, All),
    ( findall(OL, operand_label(OL), Ops0), Ops0 \= []
    -> findall(L, (member(L, Ops0), member(L, All)), Labels)
    ;  Labels = All
    ).

veredito_b(vencedora(Label, Valor)) :-
    operacao(cumulative),
    index_key(IK),
    \+ truncated(true),
    labels_com_cobertura_completa(IK, Labels),
    length(Labels, N),
    N >= 2,
    Labels = [L1, L2 | _],
    acumulado_label(IK, L1, T1),
    acumulado_label(IK, L2, T2),
    Diff is T1 - T2,
    format(atom(Label), 'diff:~w-~w', [L1, L2]),
    Valor = Diff.

veredito_b(vencedora(Label, Valor)) :-
    operacao(cumulative),
    index_key(IK),
    \+ truncated(true),
    labels_com_cobertura_completa(IK, Labels),
    Labels = [Label],
    acumulado_label(IK, Label, Valor).

veredito_b(cobertura_incompleta(Labels)) :-
    operacao(cumulative),
    index_key(IK),
    findall(L, (observado(IK, L, _P, V), number(V)), Raw),
    sort(Raw, Labels),
    ( truncated(true)
    ; labels_com_cobertura_completa(IK, Completos),
      Completos = []
    ).

% --- veredito B: time_series (meses em que label A > label B) ---
%
% Com dois labels (operand_label ou ordem lexicográfica), reporta a lista de
% períodos (átomo CSV) em que o primeiro ultrapassa o segundo.
% Valor = quantidade de meses de cruzamento.

series_labels(IndexKey, Labels) :-
    findall(L, (observado(IndexKey, L, _P, V), number(V)), Raw),
    sort(Raw, All),
    ( findall(OL, operand_label(OL), Ops0), Ops0 \= []
    -> findall(L, (member(L, Ops0), member(L, All)), Labels)
    ;  Labels = All
    ).

mes_ultrapassa(IndexKey, LabelA, LabelB, Periodo) :-
    observado(IndexKey, LabelA, Periodo, VA),
    observado(IndexKey, LabelB, Periodo, VB),
    number(VA),
    number(VB),
    VA > VB.

veredito_b(vencedora(Label, Valor)) :-
    operacao(time_series),
    index_key(IK),
    periodos_todos(Periodos),
    length(Periodos, NPeriodos),
    NPeriodos >= 2,
    \+ truncated(true),
    series_labels(IK, Labels),
    Labels = [LA, LB | _],
    findall(P,
            ( member(P, Periodos),
              mes_ultrapassa(IK, LA, LB, P)
            ),
            Meses),
    Meses \= [],
    atomic_list_concat(Meses, ',', Label),
    length(Meses, Valor).

veredito_b(cobertura_incompleta(Labels)) :-
    operacao(time_series),
    index_key(IK),
    series_labels(IK, Labels),
    ( truncated(true)
    ; \+ periodos_todos(_)
    ; periodos_todos(Periodos), length(Periodos, N), N < 2
    ; Labels = []
    ; length(Labels, NLab), NLab < 2
    ).

% --- normalização de label para comparação ---

label_norm(Raw, Norm) :-
    ( atom(Raw) -> atom_string(Raw, S0)
    ; string(Raw) -> S0 = Raw
    ; format(string(S0), '~w', [Raw])
    ),
    string_lower(S0, Norm).

valores_proximos(A, B) :-
    number(A),
    number(B),
    Diff is abs(A - B),
    Diff < 0.51.

% --- comparação A vs B; halt com exit code ---

comparar_veredictos :-
    veredito_runtime(LabelA, ValorA, ConfA, NotaA),
    format('~n=== VEREDITO A — runtime ===~n', []),
    format('Label: ~w | Valor: ~w | Confidence: ~w~n', [LabelA, ValorA, ConfA]),
    format('Nota: ~w~n', [NotaA]),
    format('~n=== VEREDITO B — Prolog (rules_lib) ===~n', []),
    ( veredito_b(Resultado)
    -> true
    ;  Resultado = sem_regra
    ),
    ( Resultado = vencedora(LabelB, ValorB)
    -> format('Vencedora: ~w | Valor: ~w~n', [LabelB, ValorB]),
       label_norm(LabelA, NA),
       label_norm(LabelB, NB),
       ( NA == NB,
         valores_proximos(ValorA, ValorB)
       -> format('~n=== COMPARAÇÃO: CONVERGE ===~n', []),
          halt(0)
       ;  format('~n=== COMPARAÇÃO: DIVERGE ===~n', []),
          format('A=~w/~w vs B=~w/~w~n', [LabelA, ValorA, LabelB, ValorB]),
          halt(1)
       )
    ; Resultado = cobertura_incompleta(Labels)
    -> format('Cobertura incompleta. Labels comparáveis: ~w~n', [Labels]),
       label_norm(LabelA, NA),
       ( member(NA, ["cobertura_incompleta", "nao_disponivel", "insufficient"])
       -> format('~n=== COMPARAÇÃO: CONVERGE (ambos insuficientes) ===~n', []),
          halt(0)
       ;  format('~n=== COMPARAÇÃO: DIVERGE ===~n', []),
          format('A afirma vencedor (~w); B recusa por cobertura incompleta.~n', [LabelA]),
          halt(1)
       )
    ;  format('Sem regra aplicável para operacao atual.~n', []),
       format('~n=== COMPARAÇÃO: B_INSUFFICIENT ===~n', []),
       halt(2)
    ).
