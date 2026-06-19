-- Chat Público — consulta sobre conhecimento remissivo validado.
-- Cache exato por (topic, semantic_hash); sem colunas vetoriais em public_chat_*.

CREATE TABLE IF NOT EXISTS "public"."public_chat_questions" (
    "id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "thread_id" UUID NOT NULL,
    "parent_question_id" UUID NULL REFERENCES "public"."public_chat_questions" ("id"),
    "topic" VARCHAR(128) NOT NULL,
    "intent_contract" JSONB NOT NULL DEFAULT '{}'::jsonb,
    "semantic_hash" VARCHAR(64) NOT NULL,
    "query_original" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS "idx_pcq_thread"
    ON "public"."public_chat_questions" ("thread_id", "created_at");
CREATE INDEX IF NOT EXISTS "idx_pcq_parent"
    ON "public"."public_chat_questions" ("parent_question_id");
CREATE INDEX IF NOT EXISTS "idx_pcq_semantic"
    ON "public"."public_chat_questions" ("topic", "semantic_hash");

CREATE TABLE IF NOT EXISTS "public"."public_chat_responses" (
    "id" UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    "topic" VARCHAR(128) NOT NULL,
    "semantic_hash" VARCHAR(64) NOT NULL,
    "answer_payload" JSONB NOT NULL,
    "knowledge_fingerprint" VARCHAR(64) NOT NULL,
    "presentation_snapshot" TEXT NULL,
    "expires_at" TIMESTAMPTZ NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT "unq_pc_responses_topic_semantic" UNIQUE ("topic", "semantic_hash")
);

CREATE TABLE IF NOT EXISTS "public"."public_chat_question_responses" (
    "question_id" UUID NOT NULL REFERENCES "public"."public_chat_questions" ("id"),
    "response_id" UUID NOT NULL REFERENCES "public"."public_chat_responses" ("id"),
    "is_repeat" BOOLEAN NOT NULL DEFAULT false,
    "presentation_delivered" TEXT NOT NULL,
    "linked_at" TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT "public_chat_question_responses_pkey" PRIMARY KEY ("question_id", "response_id")
);

COMMENT ON TABLE "public"."public_chat_questions" IS
    'Histórico imutável de perguntas do Chat Público; encadeamento via parent_question_id.';
COMMENT ON TABLE "public"."public_chat_responses" IS
    'Resolução cacheada por (topic, semantic_hash); ponteiro para conhecimento remissivo.';
COMMENT ON TABLE "public"."public_chat_question_responses" IS
    'Pivô de auditoria entre perguntas e resoluções cacheadas.';
