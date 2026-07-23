"""Roda um case ou a suíte; mapeia exit code × status → pass/fail CI."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .case_loader import CaseSpec, load_case
from .memory_parser import parse_memory_json
from .pl_emitter import emit_pl

EXIT_CONVERGE = 0
EXIT_DIVERGE = 1
EXIT_INSUFFICIENT = 2


@dataclass(frozen=True, slots=True)
class CaseRunResult:
    case: CaseSpec
    raw_exit: int
    ci_ok: bool
    generated_pl: Path
    stdout: str
    stderr: str
    reason: str


def interpret_ci(status: str, raw_exit: int) -> tuple[bool, str]:
    """Contrato CI: known_bug espera 1; regression_guard espera 0; 2 sempre falha."""
    if raw_exit == EXIT_INSUFFICIENT:
        return False, "exit 2 (insumos incompletos / B insuficiente / swipl)"
    if status == "regression_guard":
        if raw_exit == EXIT_CONVERGE:
            return True, "regression_guard + converge"
        if raw_exit == EXIT_DIVERGE:
            return False, "regressão: regression_guard + diverge"
        return False, f"regression_guard + exit inesperado {raw_exit}"
    if status == "known_bug":
        if raw_exit == EXIT_DIVERGE:
            return True, "known_bug + diverge (esperado)"
        if raw_exit == EXIT_CONVERGE:
            return False, "known_bug convergiu — promova a regression_guard"
        return False, f"known_bug + exit inesperado {raw_exit}"
    return False, f"status desconhecido: {status}"


def run_swipl(pl_path: Path) -> tuple[int, str, str]:
    swipl = shutil.which("swipl")
    if not swipl:
        return EXIT_INSUFFICIENT, "", "swipl não encontrado no PATH"
    proc = subprocess.run(
        [swipl, "-q", "-s", str(pl_path), "-g", "comparar_veredictos"],
        capture_output=True,
        text=True,
        check=False,
    )
    # SWI pode retornar 0 se halt não for alcançado; normaliza
    code = proc.returncode
    if code not in (EXIT_CONVERGE, EXIT_DIVERGE, EXIT_INSUFFICIENT):
        # falha de consult / exception
        code = EXIT_INSUFFICIENT
    return code, proc.stdout or "", proc.stderr or ""


def run_case(
    case_dir: Path | str,
    *,
    emit_only: bool = False,
) -> CaseRunResult:
    case = load_case(case_dir)
    scope = tuple((sf.dimension, sf.value) for sf in case.intent.scope_filters)
    memory = parse_memory_json(
        case.memory_path,
        index_key=case.intent.index_key,
        periods=case.intent.periods,
        scope_filters=scope,
        operand_labels=case.intent.operand_labels,
    )
    pl_path = emit_pl(case, memory)

    if emit_only:
        return CaseRunResult(
            case=case,
            raw_exit=EXIT_INSUFFICIENT,
            ci_ok=False,
            generated_pl=pl_path,
            stdout="",
            stderr="emit-only",
            reason="emit-only (não executou swipl)",
        )

    raw_exit, stdout, stderr = run_swipl(pl_path)
    ci_ok, reason = interpret_ci(case.status, raw_exit)
    return CaseRunResult(
        case=case,
        raw_exit=raw_exit,
        ci_ok=ci_ok,
        generated_pl=pl_path,
        stdout=stdout,
        stderr=stderr,
        reason=reason,
    )


def discover_cases(cases_root: Path | str) -> list[Path]:
    root = Path(cases_root)
    if not root.is_dir():
        raise FileNotFoundError(f"Diretório de cases não encontrado: {root}")
    found: set[Path] = set()
    for pattern in ("*/case.yaml", "*/case.json"):
        for p in root.glob(pattern):
            if p.parent.is_dir():
                found.add(p.parent.resolve())
    return sorted(found)


def run_suite(cases_root: Path | str) -> tuple[list[CaseRunResult], int]:
    """Retorna (resultados, exit_code_suite). Suite exit 0 só se todos ci_ok."""
    results: list[CaseRunResult] = []
    for case_dir in discover_cases(cases_root):
        results.append(run_case(case_dir))
    suite_ok = all(r.ci_ok for r in results) and bool(results)
    return results, (0 if suite_ok else 1)
