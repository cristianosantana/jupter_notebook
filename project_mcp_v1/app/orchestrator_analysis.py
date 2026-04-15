"""
Instrumentação de análise (stdout): prefixo fixo para grep e leitura em logs.

Não substitui o trace JSONL; serve para depuração rápida no terminal.
"""

from __future__ import annotations

import json
import sys
from typing import Any

_PREFIX = "[instrumentação-análise-orquestrador]"


def _trunc(val: Any, max_len: int = 400) -> str:
    if val is None:
        return "None"
    if isinstance(val, (dict, list)):
        try:
            t = json.dumps(val, ensure_ascii=False, default=str)
        except Exception:
            t = repr(val)
    else:
        t = str(val)
    if len(t) > max_len:
        return t[: max_len - 3] + "..."
    return t


def analise(msg: str, **kwargs: Any) -> None:
    """Um print por evento; ``kwargs`` aparecem como pares ``chave=valor`` truncados."""
    if kwargs:
        tail = " ".join(f"{k}={_trunc(v)}" for k, v in kwargs.items())
        line = f"{_PREFIX} {msg} | {tail}"
    else:
        line = f"{_PREFIX} {msg}"
    print(line, flush=True, file=sys.stdout)
