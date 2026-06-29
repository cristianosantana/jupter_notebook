-- 016_memory_curta_metric_dimension.sql
-- Adiciona campos metric_kind e dimension para melhor granularidade analítica

ALTER TABLE public.memory_curta
    ADD COLUMN IF NOT EXISTS metric_kind TEXT,
    ADD COLUMN IF NOT EXISTS dimension   TEXT;

CREATE INDEX IF NOT EXISTS idx_memory_curta_metric_kind
    ON public.memory_curta (metric_kind)
    WHERE metric_kind IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_memory_curta_dimension
    ON public.memory_curta (dimension)
    WHERE dimension IS NOT NULL;

-- Comentários para documentação
COMMENT ON COLUMN public.memory_curta.metric_kind IS 'Tipo da métrica: faturamento, comissao, producao, parcelamento, taxa_cartao, ticket_medio, etc.';
COMMENT ON COLUMN public.memory_curta.dimension IS 'Dimensão de agrupamento: total, por_concessionaria, por_servico, por_vendedor, por_forma_pagamento, etc.';