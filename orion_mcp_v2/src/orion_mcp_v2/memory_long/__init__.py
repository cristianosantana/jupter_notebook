"""
Memória longa (embeddings / pgvector) — reservado para paridade opcional com `orion_mcp`.

O MVP HTTP usa Redis + Postgres para estado; este pacote existe como âncora para futura
integração de RAG sem bloquear o hot path (filas Celery).
"""

__all__: list[str] = []
