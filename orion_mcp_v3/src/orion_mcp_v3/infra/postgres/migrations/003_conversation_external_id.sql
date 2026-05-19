-- Liga conversation_id arbitrário da API ao UUID interno (session_id PK).

ALTER TABLE conversation_state
    ADD COLUMN IF NOT EXISTS external_id VARCHAR(512);

CREATE UNIQUE INDEX IF NOT EXISTS uq_conversation_state_external_id
    ON conversation_state (external_id)
    WHERE external_id IS NOT NULL;

COMMENT ON COLUMN conversation_state.external_id IS
    'ID de sessão da API quando não é UUID; UUID canónico permanece em session_id.';
