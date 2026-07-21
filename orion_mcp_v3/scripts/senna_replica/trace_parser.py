"""Extrai metadados / Veredito A de um JSONL public_chat_pipeline."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ExtractedFact:
    label: str
    value: str
    unit: str | None = None
    confidence: float | None = None
    fact_key: str | None = None


@dataclass(frozen=True, slots=True)
class TraceExtract:
    trace_id: str
    question: str | None = None
    contract: dict[str, Any] | None = None
    facts: tuple[ExtractedFact, ...] = ()
    gaps: tuple[dict[str, Any], ...] = ()
    workspace_confidence: float | None = None
    answer_preview: str | None = None
    context_keys: tuple[str, ...] = ()
    origin_ids: tuple[int, ...] = ()
    events_by_etapa: dict[str, list[dict[str, Any]]] = field(default_factory=dict, compare=False)


def _parse_value_number(raw: str | float | int | None) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip().replace("%", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def load_jsonl_events(path: Path | str, *, trace_id: str | None = None) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if not isinstance(obj, dict):
                continue
            if trace_id and str(obj.get("trace_id")) != trace_id:
                continue
            events.append(obj)
    return events


def parse_trace(path: Path | str, *, trace_id: str) -> TraceExtract:
    events = load_jsonl_events(path, trace_id=trace_id)
    if not events:
        raise ValueError(f"Nenhum evento para trace_id={trace_id} em {path}")

    by_etapa: dict[str, list[dict[str, Any]]] = {}
    for ev in events:
        etapa = str(ev.get("etapa") or "")
        by_etapa.setdefault(etapa, []).append(ev)

    question: str | None = None
    for etapa in ("api.ask", "runner.turn", "runner.intent_persisted"):
        for ev in by_etapa.get(etapa, []):
            dados = ev.get("dados") or {}
            preview = dados.get("message_preview")
            if preview:
                question = str(preview)
                break
        if question:
            break

    contract: dict[str, Any] | None = None
    for etapa in ("intent.cache_hit", "intent.interpret", "runner.intent_persisted"):
        for ev in by_etapa.get(etapa, []):
            if ev.get("fase") != "post":
                continue
            dados = ev.get("dados") or {}
            if isinstance(dados.get("contract"), dict):
                contract = dados["contract"]
                break
        if contract:
            break

    facts: list[ExtractedFact] = []
    gaps: list[dict[str, Any]] = []
    workspace_confidence: float | None = None
    for etapa in ("workspace.build", "fact.extract"):
        for ev in by_etapa.get(etapa, []):
            if ev.get("fase") != "post":
                continue
            dados = ev.get("dados") or {}
            if workspace_confidence is None and dados.get("workspace_confidence") is not None:
                workspace_confidence = float(dados["workspace_confidence"])
            for fact in dados.get("facts") or []:
                if not isinstance(fact, dict):
                    continue
                facts.append(
                    ExtractedFact(
                        label=str(fact.get("label") or ""),
                        value=str(fact.get("value") or ""),
                        unit=(str(fact["unit"]) if fact.get("unit") is not None else None),
                        confidence=(
                            float(fact["confidence"])
                            if fact.get("confidence") is not None
                            else None
                        ),
                        fact_key=(str(fact["fact_key"]) if fact.get("fact_key") else None),
                    )
                )
            for gap in dados.get("gaps") or []:
                if isinstance(gap, dict):
                    gaps.append(gap)
            if facts:
                break
        if facts:
            break

    answer_preview: str | None = None
    for etapa in ("qa.turn_summary", "api.ask"):
        for ev in by_etapa.get(etapa, []):
            if ev.get("fase") != "post":
                continue
            dados = ev.get("dados") or {}
            if etapa == "qa.turn_summary":
                resp = dados.get("resposta") or {}
                if isinstance(resp, dict) and resp.get("answer_preview"):
                    answer_preview = str(resp["answer_preview"])
                    break
            if dados.get("answer_preview"):
                answer_preview = str(dados["answer_preview"])
                break
        if answer_preview:
            break

    context_keys: list[str] = []
    origin_ids: list[int] = []
    for ev in by_etapa.get("memory.accessed", []) + by_etapa.get("qa.turn_summary", []):
        dados = ev.get("dados") or {}
        mem = dados.get("memory") if isinstance(dados.get("memory"), dict) else dados
        for key in mem.get("context_keys") or []:
            context_keys.append(str(key))
        for kid in mem.get("knowledge_ids") or []:
            try:
                origin_ids.append(int(kid))
            except (TypeError, ValueError):
                continue

    return TraceExtract(
        trace_id=trace_id,
        question=question,
        contract=contract,
        facts=tuple(facts),
        gaps=tuple(gaps),
        workspace_confidence=workspace_confidence,
        answer_preview=answer_preview,
        context_keys=tuple(dict.fromkeys(context_keys)),
        origin_ids=tuple(dict.fromkeys(origin_ids)),
        events_by_etapa=by_etapa,
    )


def fact_to_runtime_numbers(fact: ExtractedFact) -> tuple[str, float] | None:
    if not fact.label:
        return None
    num = _parse_value_number(fact.value)
    if num is None:
        return None
    return fact.label, num
