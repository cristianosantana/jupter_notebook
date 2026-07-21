"""Testes do harness senna_replica (parsers, emitter, contrato CI, smoke swipl)."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from senna_replica.case_loader import load_case  # noqa: E402
from senna_replica.memory_parser import parse_memory_json  # noqa: E402
from senna_replica.pl_emitter import emit_pl  # noqa: E402
from senna_replica.suite_runner import (  # noqa: E402
    EXIT_CONVERGE,
    EXIT_DIVERGE,
    EXIT_INSUFFICIENT,
    interpret_ci,
    run_case,
)
from senna_replica.trace_parser import parse_trace  # noqa: E402

CASE_DIR = (
    Path(__file__).resolve().parent.parent
    / "cases"
    / "secao1_ranking_periodo_parcelas_9ee5b6e3"
)


def test_memory_parser_observados_from_ranked_list() -> None:
    result = parse_memory_json(
        CASE_DIR / "memory.json",
        index_key="parcelamento_de_cartao",
        periods=("2026-01", "2026-06"),
    )
    assert not result.truncated
    assert result.missing_periods == ()
    labels_jan = {o.label for o in result.observados if o.period == "2026-01"}
    labels_jun = {o.label for o in result.observados if o.period == "2026-06"}
    assert "3X" in labels_jan and "3X" in labels_jun
    assert len(result.observados) == 20


def test_pl_emitter_has_seven_sections_and_include() -> None:
    case = load_case(CASE_DIR)
    memory = parse_memory_json(
        case.memory_path,
        index_key=case.intent.index_key,
        periods=case.intent.periods,
    )
    out = emit_pl(case, memory, output_path=CASE_DIR / "_test_generated.pl")
    text = out.read_text(encoding="utf-8")
    out.unlink(missing_ok=True)
    assert "operacao(period_growth)." in text
    assert "observado(parcelamento_de_cartao," in text
    assert "veredito_runtime(" in text
    assert "rules_lib.pl" in text
    assert ":- include(" in text
    assert "comparar_veredictos" in text
    # sem regras de domínio no gerado
    assert "dominio(" not in text
    assert "crescimento_pct(" not in text
    assert "veredito_b(" not in text


def test_ci_contract_matrix() -> None:
    assert interpret_ci("regression_guard", EXIT_CONVERGE)[0] is True
    assert interpret_ci("regression_guard", EXIT_DIVERGE)[0] is False
    assert interpret_ci("known_bug", EXIT_DIVERGE)[0] is True
    assert interpret_ci("known_bug", EXIT_CONVERGE)[0] is False
    assert interpret_ci("regression_guard", EXIT_INSUFFICIENT)[0] is False
    assert interpret_ci("known_bug", EXIT_INSUFFICIENT)[0] is False


def test_trace_parser_extracts_fact() -> None:
    extract = parse_trace(CASE_DIR / "trace.jsonl", trace_id="9ee5b6e3-3705-4a8d-996f-a66525fe6d9a")
    assert extract.question
    assert extract.facts
    assert extract.facts[0].label == "3X"


def test_cobertura_insuficiente_emits_nao_vencedor(tmp_path: Path) -> None:
    """Um único label comparável → B insufficient (exit 2)."""
    case_dir = tmp_path / "thin"
    case_dir.mkdir()
    (case_dir / "case.json").write_text(
        """
{
  "status": "known_bug",
  "secao": 1,
  "bug_summary": "thin coverage",
  "trace_id": "00000000-0000-0000-0000-000000000001",
  "question": "thin",
  "memory_json": "./memory.json",
  "intent": {
    "operation": "period_growth",
    "dimension": "parcelas",
    "periods": ["2026-01", "2026-06"],
    "index_key": "parcelamento_de_cartao"
  },
  "runtime_verdict": {"label": "1X", "value": -10.0, "unit": "pct", "confidence": 0.9}
}
""".strip(),
        encoding="utf-8",
    )
    (case_dir / "memory.json").write_text(
        """
[
  {
    "context_key": "x:periodo-2026-01",
    "key_metrics": {
      "parcelamento_de_cartao": {
        "rows": [{"parcelas": "1X", "valor": 100}],
        "_meta": {"entity_field": "parcelas", "value_field": "valor", "truncated_head_tail": false}
      }
    }
  },
  {
    "context_key": "x:periodo-2026-06",
    "key_metrics": {
      "parcelamento_de_cartao": {
        "rows": [{"parcelas": "1X", "valor": 90}],
        "_meta": {"entity_field": "parcelas", "value_field": "valor", "truncated_head_tail": false}
      }
    }
  }
]
""".strip(),
        encoding="utf-8",
    )
    if not shutil.which("swipl"):
        pytest.skip("swipl não instalado")
    result = run_case(case_dir)
    assert result.raw_exit == EXIT_DIVERGE
    assert "DIVERGE" in result.stdout or "incompleta" in result.stdout.lower()


@pytest.mark.skipif(not shutil.which("swipl"), reason="swipl não instalado")
def test_smoke_secao1_converge() -> None:
    result = run_case(CASE_DIR)
    assert result.raw_exit == EXIT_CONVERGE, (result.stdout, result.stderr)
    assert result.ci_ok is True
    assert "CONVERGE" in result.stdout
