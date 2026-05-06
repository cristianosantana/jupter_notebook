from __future__ import annotations

from prometheus_client import Counter, Histogram

CHAT_REQUESTS = Counter(
    "orion_chat_requests_total",
    "Chat requests",
    labelnames=("outcome",),
)
CHAT_LATENCY = Histogram(
    "orion_chat_latency_seconds",
    "Chat end-to-end latency",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)
DRL_BUNDLES_BUILT = Counter(
    "orion_drl_bundles_built_total",
    "Consultas catalogadas para as quais foi construído um bundle DRL no MCP",
)
