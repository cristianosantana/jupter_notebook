"""CLI: case único, --suite ou --from-db."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .live_packer import pack_and_run, parse_operand_labels
from .suite_runner import run_case, run_suite


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Réplica Senna (Prolog-first): empacota case → generated.pl → "
            "swipl comparar_veredictos. Exit codes: 0 converge, 1 diverge, 2 insuficiente."
        )
    )
    parser.add_argument(
        "case_dir",
        nargs="?",
        help="Diretório do case (com case.yaml)",
    )
    parser.add_argument(
        "--suite",
        metavar="CASES_DIR",
        help="Roda todos os cases sob o diretório (modo CI)",
    )
    parser.add_argument(
        "--emit-only",
        action="store_true",
        help="Só gera generated.pl (não chama swipl)",
    )
    parser.add_argument(
        "--from-db",
        action="store_true",
        help="Empacota memory.json a partir de memory_curta (DATABASE_URL)",
    )
    parser.add_argument("--question", help="Pergunta (obrigatório com --from-db)")
    parser.add_argument("--operation", help="Operação Senna (ex.: cumulative, time_series)")
    parser.add_argument("--dimension", help="Dimensão-alvo")
    parser.add_argument("--index-key", help="Chave de índice em key_metrics / context_key")
    parser.add_argument(
        "--operand-labels",
        help="Labels operandos separados por | (ex.: 'Pix|Cartão de Crédito')",
    )
    parser.add_argument(
        "--status",
        default="known_bug",
        choices=("known_bug", "regression_guard"),
        help="Status do case ao empacotar (default: known_bug)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.suite:
        results, code = run_suite(args.suite)
        for r in results:
            mark = "PASS" if r.ci_ok else "FAIL"
            print(
                f"[{mark}] {r.case.root.name} status={r.case.status} "
                f"raw_exit={r.raw_exit} — {r.reason}"
            )
            if r.stdout.strip():
                print(r.stdout.rstrip())
            if r.stderr.strip() and not r.ci_ok:
                print(r.stderr.rstrip(), file=sys.stderr)
        if not results:
            print("Nenhum case encontrado.", file=sys.stderr)
            return 2
        return code

    if args.from_db:
        missing = [
            name
            for name, value in (
                ("--question", args.question),
                ("--operation", args.operation),
                ("--dimension", args.dimension),
                ("--index-key", args.index_key),
                ("case_dir", args.case_dir),
            )
            if not value
        ]
        if missing:
            print(
                f"--from-db exige: case_dir, --question, --operation, "
                f"--dimension, --index-key (faltando: {', '.join(missing)})",
                file=sys.stderr,
            )
            return 2
        return pack_and_run(
            question=args.question,
            case_dir=args.case_dir,
            operation=args.operation,
            dimension=args.dimension,
            index_key=args.index_key,
            operand_labels=parse_operand_labels(args.operand_labels),
            status=args.status,
            emit_only=args.emit_only,
        )

    if not args.case_dir:
        build_parser().print_help()
        return 2

    result = run_case(args.case_dir, emit_only=args.emit_only)
    print(f"generated: {result.generated_pl}")
    print(f"status={result.case.status} raw_exit={result.raw_exit} ci_ok={result.ci_ok}")
    print(f"reason: {result.reason}")
    if result.stdout.strip():
        print(result.stdout.rstrip())
    if result.stderr.strip():
        print(result.stderr.rstrip(), file=sys.stderr)

    if args.emit_only:
        return 0
    return result.raw_exit


if __name__ == "__main__":
    sys.exit(main())
