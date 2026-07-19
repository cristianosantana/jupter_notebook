% rules_lib.pl — motor B genérico (agnóstico à dimensão).
% Dimensão e períodos aparecem só nos fatos do case gerado.
% Operações: period_growth, period_decline, ranking_desc, ranking_asc.

:- dynamic
    operacao/1,
    dimensao_alvo/1,
    periodo/1,
    index_key/1,
    scope_filter/2,
    observado/4,
    nao_disponivel/3,
    truncated/1,
    veredito_runtime/4.

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

cobertura_suficiente(Labels) :-
    length(Labels, N),
    N > 1,
    \+ truncated(true).

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
