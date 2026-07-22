"""Empacota case Senna a partir do BD (memory_curta) — isolado do public_chat."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from pathlib import Path
from typing import Any

from .infra.pool import close_postgres_pool, create_postgres_pool
from .infra.remissive_reader import SennaRemissiveReader
from .period_range import periods_from_question
from .suite_runner import EXIT_INSUFFICIENT, run_case


def _slug_index_key(index_key: str) -> str:
    return index_key.strip().lower().replace(" ", "_")


def _patterns_for_index_periods(index_key: str, periods: tuple[str, ...]) -> list[str]:
    key = _slug_index_key(index_key)
    # Aliases comuns: CLI vs context_key vs key_metrics
    aliases = {
        key,
        key.replace("tipo_os", "tipo_de_os"),
        key.replace("tipo_de_os", "tipo_os"),
        "comissao_por_concessionaria_tipo_os",
        "comissao_por_tipo_de_os_por_concessionaria",
        "comissao_por_tipo_os",
    }
    patterns: list[str] = []
    for alias in dict.fromkeys(a for a in aliases if a):
        for period in periods:
            patterns.append(f"%{alias}%periodo-{period}%")
            patterns.append(f"%{alias}%periodo_{period.replace('-', '_')}%")
            patterns.append(f"%periodo-{period}%{alias}%")
        patterns.append(f"%{alias}%")
    return patterns


def _prefer_key_metrics_key(hits: list[Any], requested: str) -> str:
    """Escolhe a chave real de key_metrics presente nos hits."""
    from collections import Counter

    counter: Counter[str] = Counter()
    for hit in hits:
        km = getattr(hit, "key_metrics", None) or {}
        if isinstance(km, dict):
            for key in km:
                counter[str(key)] += 1
    if not counter:
        return requested
    needle = _slug_index_key(requested)
    # Preferir chaves que casam com o pedido e têm matriz tipo_os
    ranked = sorted(
        counter.items(),
        key=lambda item: (
            -int(needle in _slug_index_key(item[0]) or _slug_index_key(item[0]) in needle),
            -int("tipo" in _slug_index_key(item[0])),
            -item[1],
            len(item[0]),
        ),
    )
    return ranked[0][0]


def _infer_concessionaria(question: str) -> str | None:
    match = re.search(
        r"concession[aá]ria\s+([A-Za-z0-9][A-Za-z0-9 \-/]+?)(?:\s*,|\s+somando|\s+de\s+janeiro|\s*$)",
        question or "",
        flags=re.IGNORECASE,
    )
    if not match:
        match = re.search(
            r"\b(GWM\s+BAMAQ(?:\s+\w+)?|SAITAMA\s*-\s*HONDA|PORSCHE|CARBEL(?:\s+\w+)?)\b",
            question or "",
            flags=re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()
        return None
    return match.group(1).strip()


def _hit_to_memory_row(hit: Any) -> dict[str, Any]:
    return {
        "origin_id": hit.origin_id,
        "context_key": hit.context_key,
        "category": hit.category,
        "validated_answer": hit.validated_answer,
        "key_metrics": dict(hit.key_metrics),
        "score": hit.score,
        "source": "memory_curta",
    }


def _filter_hits_for_periods(hits: list[Any], periods: tuple[str, ...]) -> list[Any]:
    if not periods:
        return hits
    period_tokens = {p.lower() for p in periods}
    period_tokens |= {p.replace("-", "_").lower() for p in periods}
    kept: list[Any] = []
    for hit in hits:
        ck = (hit.context_key or "").lower()
        if any(token in ck for token in period_tokens):
            kept.append(hit)
    return kept or hits


def _write_case_yaml(
    path: Path,
    *,
    status: str,
    secao: int,
    bug_summary: str,
    trace_id: str,
    question: str,
    operation: str,
    dimension: str,
    periods: tuple[str, ...],
    index_key: str,
    scope_filters: list[dict[str, str]],
    operand_labels: list[str],
    runtime_verdict: dict[str, Any],
) -> None:
    try:
        import yaml
    except ImportError:
        yaml = None

    payload = {
        "status": status,
        "secao": secao,
        "bug_summary": bug_summary,
        "trace_id": trace_id,
        "question": question,
        "memory_json": "./memory.json",
        "intent": {
            "operation": operation,
            "dimension": dimension,
            "periods": list(periods),
            "index_key": index_key,
            "scope_filters": scope_filters,
            "operand_labels": operand_labels,
        },
        "runtime_verdict": runtime_verdict,
    }
    if yaml is not None:
        path.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    path.with_suffix(".json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


async def pack_case_from_db(
    *,
    question: str,
    case_dir: Path,
    operation: str,
    dimension: str,
    index_key: str,
    periods: tuple[str, ...] | None = None,
    scope_filters: list[dict[str, str]] | None = None,
    operand_labels: list[str] | None = None,
    status: str = "known_bug",
    secao: int = 1,
    bug_summary: str = "",
    runtime_verdict: dict[str, Any] | None = None,
    database_url: str | None = None,
) -> Path:
    resolved_periods = periods or periods_from_question(question)
    if len(resolved_periods) < 1:
        raise ValueError("não foi possível extrair períodos da pergunta")

    pool = await create_postgres_pool(database_url, required=True)
    assert pool is not None
    try:
        reader = SennaRemissiveReader(pool, limit=50)
        patterns = _patterns_for_index_periods(index_key, resolved_periods)
        hits = await reader.load_hits_by_context_key_patterns(patterns, limit=50)
        if not hits:
            hits = await reader.load_hits_by_theme_patterns(
                [_slug_index_key(index_key)],
                limit=50,
            )
        hits = _filter_hits_for_periods(hits, resolved_periods)
        if not hits:
            raise RuntimeError(
                f"nenhum hit em memory_curta para index_key={index_key!r} "
                f"periods={resolved_periods}"
            )

        # Preferir a chave real de key_metrics quando o CLI passou um alias
        resolved_index_key = _prefer_key_metrics_key(hits, index_key)

        case_dir.mkdir(parents=True, exist_ok=True)
        memory_path = case_dir / "memory.json"
        memory_payload = {
            "hits": [_hit_to_memory_row(hit) for hit in hits],
            "source": "senna_live_packer",
            "index_key": resolved_index_key,
            "periods": list(resolved_periods),
            "question": question,
        }
        memory_path.write_text(
            json.dumps(memory_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        trace_id = str(uuid.uuid4())
        verdict = runtime_verdict or {
            "label": "pending_manual_verdict",
            "value": 0.0,
            "unit": "BRL",
            "confidence": 0.0,
            "note": "preencha runtime_verdict após inspecionar Veredito B / pipeline",
        }
        scopes = list(scope_filters or [])
        # Heurística: "concessionária X" / "para a concessionária X"
        if not any(s.get("dimension") == "concessionaria" for s in scopes):
            inferred = _infer_concessionaria(question)
            if inferred:
                scopes.append(
                    {"dimension": "concessionaria", "value": inferred, "match": "exact"}
                )
        _write_case_yaml(
            case_dir / "case.yaml",
            status=status,
            secao=secao,
            bug_summary=bug_summary
            or f"Case empacotado via --from-db ({operation})",
            trace_id=trace_id,
            question=question.strip(),
            operation=operation,
            dimension=dimension,
            periods=resolved_periods,
            index_key=resolved_index_key,
            scope_filters=scopes,
            operand_labels=operand_labels or [],
            runtime_verdict=verdict,
        )
        return case_dir
    finally:
        await close_postgres_pool(pool)


def pack_and_run(
    *,
    question: str,
    case_dir: Path | str,
    operation: str,
    dimension: str,
    index_key: str,
    periods: tuple[str, ...] | None = None,
    scope_filters: list[dict[str, str]] | None = None,
    operand_labels: list[str] | None = None,
    status: str = "known_bug",
    emit_only: bool = False,
    database_url: str | None = None,
) -> int:
    case_path = Path(case_dir)
    try:
        asyncio.run(
            pack_case_from_db(
                question=question,
                case_dir=case_path,
                operation=operation,
                dimension=dimension,
                index_key=index_key,
                periods=periods,
                scope_filters=scope_filters,
                operand_labels=operand_labels,
                status=status,
                database_url=database_url,
            )
        )
    except Exception as exc:  # noqa: BLE001 — CLI surface
        print(f"pack --from-db falhou: {exc}")
        return EXIT_INSUFFICIENT

    if emit_only:
        from .suite_runner import run_case as _run

        result = _run(case_path, emit_only=True)
        print(f"generated: {result.generated_pl}")
        return 0

    result = run_case(case_path, emit_only=False)
    print(f"generated: {result.generated_pl}")
    print(f"status={result.case.status} raw_exit={result.raw_exit} ci_ok={result.ci_ok}")
    print(f"reason: {result.reason}")
    if result.stdout.strip():
        print(result.stdout.rstrip())
    if result.stderr.strip():
        print(result.stderr.rstrip())
    return result.raw_exit


def parse_operand_labels(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in re.split(r"\s*\|\s*", raw) if part.strip()]
