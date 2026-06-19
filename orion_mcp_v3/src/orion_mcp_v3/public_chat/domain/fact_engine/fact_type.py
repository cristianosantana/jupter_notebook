"""Proof binding — tipo de fact no workspace."""

from __future__ import annotations

from enum import Enum


class FactType(str, Enum):
    RAW = "raw"
    DERIVED = "derived"
    ESTIMATED = "estimated"
