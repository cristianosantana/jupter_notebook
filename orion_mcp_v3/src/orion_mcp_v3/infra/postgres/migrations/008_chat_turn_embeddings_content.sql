-- Texto do turno para retrieval vectorial sem re-parse de conversation_state.

ALTER TABLE chat_turn_embeddings
    ADD COLUMN IF NOT EXISTS content TEXT NOT NULL DEFAULT '';

COMMENT ON COLUMN chat_turn_embeddings.content IS
    'Texto indexado (cópia do turno) usado na montagem de ContextBlock após busca vetorial.';
