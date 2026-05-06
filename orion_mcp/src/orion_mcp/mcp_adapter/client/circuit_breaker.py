from __future__ import annotations

import time
from dataclasses import dataclass, field


class CircuitOpenError(RuntimeError):
    """Circuito em estado OPEN — falhar rápido sem sobrecarregar o upstream."""


@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    open_seconds: float = 30.0
    _failures: int = 0
    _opened_at: float | None = None
    _state: str = field(default="closed", init=False)  # closed | open | half_open

    def before_call(self) -> None:
        now = time.monotonic()
        if self._state == "open":
            if self._opened_at is None or now - self._opened_at >= self.open_seconds:
                self._state = "half_open"
                self._failures = max(0, self.failure_threshold - 1)
                return
            raise CircuitOpenError("mcp_grpc_circuit_open")
        if self._state == "half_open":
            return

    def record_success(self) -> None:
        self._failures = 0
        self._state = "closed"
        self._opened_at = None

    def record_failure(self) -> None:
        if self._state == "half_open":
            self._state = "open"
            self._opened_at = time.monotonic()
            return
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._state = "open"
            self._opened_at = time.monotonic()
