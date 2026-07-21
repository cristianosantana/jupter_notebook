"""Carrega e valida case.yaml / case.json (+ paths relativos)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

VALID_STATUSES = frozenset({"known_bug", "regression_guard"})


@dataclass(frozen=True, slots=True)
class ScopeFilter:
    dimension: str
    value: str


@dataclass(frozen=True, slots=True)
class IntentSpec:
    operation: str
    dimension: str
    periods: tuple[str, ...]
    index_key: str
    scope_filters: tuple[ScopeFilter, ...] = ()


@dataclass(frozen=True, slots=True)
class RuntimeVerdict:
    label: str
    value: float
    unit: str = "pct"
    confidence: float | None = None
    note: str = ""


@dataclass(frozen=True, slots=True)
class CaseSpec:
    root: Path
    status: str
    secao: int
    bug_summary: str
    trace_id: str
    question: str
    intent: IntentSpec
    runtime_verdict: RuntimeVerdict
    memory_path: Path
    trace_path: Path | None = None
    raw: dict[str, Any] = field(default_factory=dict, compare=False)


def _load_mapping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError(f"case inválido (esperado mapping): {path}")
        return data

    try:
        import yaml
    except ImportError:
        json_sibling = path.with_suffix(".json")
        if json_sibling.is_file():
            return _load_mapping(json_sibling)
        raise RuntimeError(
            "PyYAML é obrigatório para case.yaml (pip install PyYAML), "
            f"ou forneça {path.with_suffix('.json').name}."
        ) from None

    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"case.yaml inválido (esperado mapping): {path}")
    return data


def _require(data: dict[str, Any], key: str) -> Any:
    if key not in data or data[key] is None:
        raise ValueError(f"case: campo obrigatório ausente: {key}")
    return data[key]


def load_case(case_dir: Path | str) -> CaseSpec:
    root = Path(case_dir).resolve()
    yaml_path = root / "case.yaml"
    json_path = root / "case.json"

    if yaml_path.is_file():
        try:
            data = _load_mapping(yaml_path)
        except RuntimeError:
            if json_path.is_file():
                data = _load_mapping(json_path)
            else:
                raise
    elif json_path.is_file():
        data = _load_mapping(json_path)
    else:
        raise FileNotFoundError(f"case.yaml/case.json não encontrado em {root}")

    status = str(_require(data, "status")).strip()
    if status not in VALID_STATUSES:
        raise ValueError(
            f"case: status inválido {status!r}; use {sorted(VALID_STATUSES)}"
        )

    intent_raw = _require(data, "intent")
    if not isinstance(intent_raw, dict):
        raise ValueError("case: intent deve ser um mapping")

    periods = intent_raw.get("periods") or []
    if not isinstance(periods, list) or not periods:
        raise ValueError("case: intent.periods deve ser lista não vazia")

    scope_filters: list[ScopeFilter] = []
    for item in intent_raw.get("scope_filters") or []:
        if not isinstance(item, dict):
            continue
        scope_filters.append(
            ScopeFilter(
                dimension=str(item["dimension"]),
                value=str(item["value"]),
            )
        )

    intent = IntentSpec(
        operation=str(_require(intent_raw, "operation")),
        dimension=str(_require(intent_raw, "dimension")),
        periods=tuple(str(p) for p in periods),
        index_key=str(_require(intent_raw, "index_key")),
        scope_filters=tuple(scope_filters),
    )

    verdict_raw = _require(data, "runtime_verdict")
    if not isinstance(verdict_raw, dict):
        raise ValueError("case: runtime_verdict deve ser um mapping")

    verdict = RuntimeVerdict(
        label=str(_require(verdict_raw, "label")),
        value=float(_require(verdict_raw, "value")),
        unit=str(verdict_raw.get("unit") or "pct"),
        confidence=(
            float(verdict_raw["confidence"])
            if verdict_raw.get("confidence") is not None
            else None
        ),
        note=str(verdict_raw.get("note") or ""),
    )

    memory_rel = str(data.get("memory_json") or "./memory.json")
    memory_path = (root / memory_rel).resolve()
    if not memory_path.is_file():
        raise FileNotFoundError(f"memory.json não encontrado: {memory_path}")

    trace_path: Path | None = None
    if data.get("trace_jsonl"):
        candidate = (root / str(data["trace_jsonl"])).resolve()
        if candidate.is_file():
            trace_path = candidate

    return CaseSpec(
        root=root,
        status=status,
        secao=int(_require(data, "secao")),
        bug_summary=str(data.get("bug_summary") or "").strip(),
        trace_id=str(_require(data, "trace_id")),
        question=str(_require(data, "question")).strip(),
        intent=intent,
        runtime_verdict=verdict,
        memory_path=memory_path,
        trace_path=trace_path,
        raw=data,
    )
