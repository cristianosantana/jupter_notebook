"""Hash determinístico do contrato normalizado — chave de cache exato."""

from __future__ import annotations

import hashlib
import json

from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract
from orion_mcp_v3.public_chat.domain.intent_parser import normalize_contract_for_hash


def build_semantic_hash(contract: IntentContract) -> str:
    """sha256 de JSON canônico do contrato normalizado."""
    canonical = normalize_contract_for_hash(contract)
    payload = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
