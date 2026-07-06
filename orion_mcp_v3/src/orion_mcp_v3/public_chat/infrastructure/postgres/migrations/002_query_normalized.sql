-- P2 — cache de intent por pergunta normalizada (lookup antes do LLM).

ALTER TABLE "public"."public_chat_questions"
    ADD COLUMN IF NOT EXISTS "query_normalized" TEXT NULL;

CREATE INDEX IF NOT EXISTS "idx_pcq_intent_cache"
    ON "public"."public_chat_questions" ("query_normalized", "parent_question_id", "created_at" DESC);
