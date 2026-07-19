"""CLI: case único ou --suite."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

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
    # case único: devolve exit bruto do swipl (útil em desenvolvimento)
    return result.raw_exit


if __name__ == "__main__":
    sys.exit(main())
