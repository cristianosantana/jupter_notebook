"""
Extracção de metadados YAML do cabeçalho ``/* @mcp_query_meta ... @mcp_query_meta */`` em ficheiros .sql.

Evitar ``*/`` nos textos do meta: em comentário SQL ``/* ... */`` isso encerra o comentário. Aspas YAML/JSON podem incluir outros caracteres; use ``|`` para blocos longos.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final

import yaml

_META_START: Final[str] = "/* @mcp_query_meta"
_META_END: Final[str] = "@mcp_query_meta */"

_VALID_SHAPES: Final[frozenset[str]] = frozenset({"tabular_multiline", "json_aggregate"})

_META_BLOCK_RE = re.compile(
    re.escape(_META_START) + r"\s*(.*?)\s*" + re.escape(_META_END),
    re.DOTALL,
)


def parse_sql_file(path: Path) -> tuple[dict[str, Any], str]:
    """
    Lê ``path``, extrai meta YAML e devolve ``(meta, sql_body)``.

    ``meta`` inclui sempre ``query_id``, ``resource_description``, ``when_to_use``, ``output_shape``.
    ``not_confused_with`` é opcional (lista de ``query_id`` ou string única).
    """
    raw = path.read_text(encoding="utf-8")
    if _META_START not in raw:
        raise ValueError(f"{path.name}: falta cabeçalho {_META_START!r}")

    m = _META_BLOCK_RE.search(raw)
    if not m:
        raise ValueError(f"{path.name}: cabeçalho MCP mal formado (esperado {_META_END!r})")

    yaml_blob = m.group(1).strip()

    try:
        loaded = yaml.safe_load(yaml_blob)
    except yaml.YAMLError as e:
        raise ValueError(f"{path.name}: YAML inválido no meta: {e}") from e

    if not isinstance(loaded, dict):
        raise ValueError(f"{path.name}: meta YAML tem de ser um objecto/mapa no topo")

    stem = path.stem
    qid = loaded.get("query_id")
    if qid is None or str(qid).strip() == "":
        qid = stem
    qid = str(qid).strip()
    if qid != stem:
        raise ValueError(
            f"{path.name}: query_id {qid!r} tem de coincidir com o nome do ficheiro ({stem!r})"
        )

    for key in ("resource_description", "when_to_use", "output_shape"):
        if key not in loaded or loaded[key] is None or str(loaded[key]).strip() == "":
            raise ValueError(f"{path.name}: meta obrigatório em falta ou vazio: {key}")

    shape = str(loaded["output_shape"]).strip()
    if shape not in _VALID_SHAPES:
        raise ValueError(
            f"{path.name}: output_shape {shape!r} inválido; use {sorted(_VALID_SHAPES)}"
        )

    ncf = loaded.get("not_confused_with")
    ncf_list: list[str] | None = None
    if ncf is not None:
        if isinstance(ncf, str):
            ncf_list = [ncf.strip()] if ncf.strip() else None
        elif isinstance(ncf, list):
            ncf_list = [str(x).strip() for x in ncf if str(x).strip()]
            ncf_list = ncf_list or None
        else:
            raise ValueError(f"{path.name}: not_confused_with tem de ser string ou lista")

    meta: dict[str, Any] = {
        "query_id": qid,
        "resource_description": str(loaded["resource_description"]).strip(),
        "when_to_use": str(loaded["when_to_use"]).strip(),
        "output_shape": shape,
    }
    if ncf_list:
        meta["not_confused_with"] = ncf_list

    sql_body = raw[m.end() :].strip()
    if not sql_body:
        raise ValueError(f"{path.name}: SQL vazio após o meta")

    core = sql_body.rstrip(";").strip()
    if ";" in core:
        raise ValueError(f"{path.name}: SQL com múltiplas statements não é permitido")

    return meta, core


def validate_query_sql_dir(query_dir: Path) -> list[str]:
    """
    Valida todos os ``*.sql`` em ``query_dir``. Devolve lista de ``query_id`` ordenados.
    Levanta ``ValueError`` no primeiro erro.
    """
    paths = sorted(query_dir.glob("*.sql"), key=lambda p: p.name)
    if not paths:
        raise ValueError(f"nenhum .sql em {query_dir}")
    seen: set[str] = set()
    ids: list[str] = []
    for path in paths:
        meta, _ = parse_sql_file(path)
        qid = meta["query_id"]
        if qid in seen:
            raise ValueError(f"query_id duplicado: {qid}")
        seen.add(qid)
        ids.append(qid)
    return ids
