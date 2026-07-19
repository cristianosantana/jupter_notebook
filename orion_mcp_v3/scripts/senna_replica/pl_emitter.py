"""Emite .pl nas 7 seções do trilho; regras via include de rules_lib.pl."""

from __future__ import annotations

from pathlib import Path

from .case_loader import CaseSpec
from .memory_parser import MemoryParseResult, Observado


def _prolog_atom(text: str) -> str:
    """Escapa string como átomo Prolog entre aspas simples."""
    escaped = text.replace("\\", "\\\\").replace("'", "''")
    return f"'{escaped}'"


def _prolog_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _observado_clause(obs: Observado) -> str:
    return (
        f"observado({obs.index_key}, {_prolog_atom(obs.label)}, "
        f"{_prolog_atom(obs.period)}, {_prolog_number(obs.value)})."
    )


def rules_lib_path() -> Path:
    return Path(__file__).resolve().parent / "prolog" / "rules_lib.pl"


def emit_pl(
    case: CaseSpec,
    memory: MemoryParseResult,
    *,
    output_path: Path | None = None,
) -> Path:
    out = output_path or (case.root / "generated.pl")
    lib = rules_lib_path().resolve()

    verdict = case.runtime_verdict
    note = verdict.note or case.bug_summary or "sem nota"
    conf = verdict.confidence if verdict.confidence is not None else 0.0

    lines: list[str] = []

    # --- 1. Cabeçalho ---
    lines.extend(
        [
            "% =============================================================================",
            "% generated.pl — réplica Senna (NÃO EDITAR; regenerado pelo harness)",
            "%",
            f"% Pergunta: {case.question.replace(chr(10), ' ')}",
            f"% trace_id: {case.trace_id}",
            f"% Veredito runtime (A): {verdict.label} / {verdict.value} {verdict.unit}",
            "% Declaração: resolve do zero via rules_lib.pl; não audita decisão alheia.",
            f"% status: {case.status} | secao: {case.secao}",
            "% =============================================================================",
            "",
        ]
    )

    # --- 2. Estrutura da pergunta ---
    lines.append("% --- 2. Fatos de estrutura da pergunta ---")
    lines.append(f"operacao({case.intent.operation}).")
    lines.append(f"dimensao_alvo({case.intent.dimension}).")
    for period in case.intent.periods:
        lines.append(f"periodo({_prolog_atom(period)}).")
    lines.append(f"index_key({case.intent.index_key}).")
    for sf in case.intent.scope_filters:
        if sf.dimension == case.intent.dimension:
            continue  # não emitir filtro na dimensão-alvo
        lines.append(
            f"scope_filter({_prolog_atom(sf.dimension)}, {_prolog_atom(sf.value)})."
        )
    lines.append("")

    # --- 3. Observados ---
    lines.append("% --- 3. Fatos de dado observado ---")
    if not memory.observados:
        lines.append(
            f"nao_disponivel({case.intent.index_key}, {_prolog_atom('ranked_list')}, "
            f"{_prolog_atom('memory.json sem rows utilizáveis')})."
        )
    else:
        for obs in memory.observados:
            lines.append(_observado_clause(obs))
    for missing in memory.missing_periods:
        lines.append(
            f"nao_disponivel({case.intent.index_key}, {_prolog_atom(missing)}, "
            f"{_prolog_atom('periodo ausente no memory.json')})."
        )
    if memory.truncated:
        lines.append("truncated(true).")
    else:
        lines.append("truncated(false).")
    lines.append("")

    # --- 4. Veredito runtime ---
    lines.append("% --- 4. Veredito real do runtime (fato histórico) ---")
    lines.append(
        f"veredito_runtime({_prolog_atom(verdict.label)}, {_prolog_number(verdict.value)}, "
        f"{_prolog_number(conf)}, {_prolog_atom(note)})."
    )
    lines.append("")

    # --- 5. Regras (include) ---
    lines.append("% --- 5. Regras determinísticas (rules_lib.pl) ---")
    lines.append(f":- include({_prolog_atom(str(lib))}).")
    lines.append("")

    # --- 6. comparar_veredictos está na lib ---
    lines.append("% --- 6. Comparação: consultar comparar_veredictos/0 (em rules_lib.pl) ---")
    lines.append("")

    # --- 7. Instruções ---
    lines.extend(
        [
            "% =============================================================================",
            "% 7. USO",
            "%   swipl -q -s generated.pl -g comparar_veredictos",
            "% Exit: 0 converge | 1 diverge | 2 insuficiente/sem regra",
            "% =============================================================================",
            "",
        ]
    )

    out.write_text("\n".join(lines), encoding="utf-8")
    return out
