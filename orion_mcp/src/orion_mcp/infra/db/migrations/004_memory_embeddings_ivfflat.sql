-- A migração 004 é tratada em migrate.py: com dim≤2000 fica só registada (HNSW cobre na 003).
-- Com dim>2000, HNSW/IVFFlat não suportam índice ANN neste pgvector; não se executa SQL aqui.

SELECT 1;
