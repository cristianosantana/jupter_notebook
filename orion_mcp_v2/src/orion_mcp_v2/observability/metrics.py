from __future__ import annotations

from prometheus_client import Counter, Histogram

ORCHESTRATOR_TURN_SECONDS = Histogram(
    "orion_v2_orchestrator_turn_duration_seconds",
    "Duração do turno (orquestrador)",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

CONSOLIDATION_SECONDS = Histogram(
    "orion_v2_consolidation_job_duration_seconds",
    "Duração da consolidação por utilizador",
    buckets=(0.5, 1.0, 2.5, 5.0, 15.0, 60.0, 120.0),
)

CHAT_REQUESTS = Counter(
    "orion_v2_chat_requests_total",
    "Pedidos HTTP chat",
    ["outcome"],
)

CHAT_LATENCY = Histogram(
    "orion_v2_chat_latency_seconds",
    "Latência end-to-end chat (inclui stream)",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)

RATE_LIMIT_HITS = Counter(
    "orion_v2_rate_limit_exceeded_total",
    "Bloqueios por rate limit",
)
