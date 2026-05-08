"""
DriftGuard — comparação leve entre digestos consecutivos (ORDEM_IMPLEMENTAÇÃO §7).

Usa confiança e volume como sinais grosseiros; extensível com mais métricas.
"""

from __future__ import annotations

from dataclasses import dataclass

from orion_mcp_v3.contracts.digest import AnalyticalDigest


@dataclass(frozen=True, slots=True)
class DriftSignal:
    code: str
    message: str
    severity: float


@dataclass(frozen=True, slots=True)
class DriftReport:
    signals: tuple[DriftSignal, ...]
    refresh_recommended: bool


class DriftGuard:
    """
    Emite :class:`DriftReport` quando a digest nova diverge da anterior além dos limiares.
    """

    def __init__(
        self,
        *,
        confidence_drop_threshold: float = 0.12,
        volume_change_ratio: float = 4.0,
    ) -> None:
        self._conf_drop = confidence_drop_threshold
        self._vol_ratio = volume_change_ratio

    def evaluate(self, previous: AnalyticalDigest | None, current: AnalyticalDigest) -> DriftReport:
        if previous is None:
            return DriftReport((), False)

        signals: list[DriftSignal] = []
        pc, cc = previous.confidence, current.confidence
        if pc is not None and cc is not None and pc - cc >= self._conf_drop:
            delta = pc - cc
            sev = min(1.0, delta / max(self._conf_drop, 1e-9))
            signals.append(
                DriftSignal(
                    "confidence_drop",
                    f"conf {pc:.3f} → {cc:.3f} (Δ={delta:.3f})",
                    sev,
                )
            )

        pv, cv = max(0, int(previous.volume)), max(0, int(current.volume))
        if pv > 0 and cv > 0:
            ratio = max(pv, cv) / min(pv, cv)
            if ratio >= self._vol_ratio:
                sev = min(1.0, ratio / max(self._vol_ratio, 1e-9))
                signals.append(
                    DriftSignal(
                        "volume_shift",
                        f"volume {pv} vs {cv} (ratio≈{ratio:.2f})",
                        sev,
                    )
                )

        return DriftReport(tuple(signals), bool(signals))
