from __future__ import annotations

from enum import Enum


class Strategy(str, Enum):
    fast = "fast"
    deep = "deep"
