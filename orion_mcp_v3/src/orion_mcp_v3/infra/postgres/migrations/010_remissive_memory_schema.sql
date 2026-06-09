-- V2: memória remissiva materializada por rotina externa de destilação.

DROP TABLE IF EXISTS "public"."memory_embeddings" CASCADE;
DROP TABLE IF EXISTS "public"."memory_curta" CASCADE;
DROP TABLE IF EXISTS "public"."memory_essence" CASCADE;
DROP TABLE IF EXISTS "public"."memory_compression_log" CASCADE;

CREATE TABLE "public"."memory_curta" (
  "id" SERIAL,
  "user_id" VARCHAR(20) NOT NULL,
  "category" VARCHAR(50) NOT NULL,
  "context_key" VARCHAR(100) NOT NULL,
  "validated_answer" TEXT NOT NULL,
  "recent_questions" JSONB NOT NULL DEFAULT '[]'::jsonb,
  "key_metrics" JSONB NOT NULL DEFAULT '{}'::jsonb,
  "consolidated_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  "last_seen_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  "ttl_expires_at" TIMESTAMP WITH TIME ZONE NULL,
  CONSTRAINT "memory_curta_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "unq_memory_curta_context" UNIQUE ("context_key")
);

CREATE INDEX "idx_memory_curta_ttl" ON "public"."memory_curta" ("ttl_expires_at" ASC);
CREATE INDEX "idx_memory_curta_context" ON "public"."memory_curta" ("context_key");
CREATE INDEX "idx_memory_curta_last_seen" ON "public"."memory_curta" ("last_seen_at" ASC);

CREATE TABLE "public"."memory_embeddings" (
  "id" SERIAL,
  "user_id" VARCHAR(20) NOT NULL,
  "origin_id" INTEGER NOT NULL,
  "origin_type" VARCHAR(50) NOT NULL,
  "text" TEXT NOT NULL,
  "embedding" vector(1536) NOT NULL,
  "category" VARCHAR(50) NULL,
  "created_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  "ttl_expires_at" TIMESTAMP WITH TIME ZONE NULL,
  CONSTRAINT "memory_embeddings_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "fk_memory_embeddings_curta"
    FOREIGN KEY ("origin_id")
    REFERENCES "public"."memory_curta" ("id")
    ON DELETE CASCADE
);

CREATE INDEX "idx_memory_embeddings_ttl" ON "public"."memory_embeddings" ("ttl_expires_at" ASC);
CREATE INDEX "idx_memory_embeddings_user_id" ON "public"."memory_embeddings" ("user_id" ASC);
CREATE INDEX "idx_memory_embeddings_origin" ON "public"."memory_embeddings" ("origin_id", "origin_type");
CREATE INDEX "idx_memory_embeddings_ivfflat"
ON "public"."memory_embeddings" USING ivfflat ("embedding" vector_cosine_ops)
WITH (lists = 100);

CREATE TABLE "public"."memory_essence" (
  "id" SERIAL,
  "user_id" VARCHAR(20) NOT NULL,
  "theme" VARCHAR(255) NOT NULL,
  "observation" TEXT NULL,
  "key_finding" TEXT NULL,
  "recommendation" TEXT NULL,
  "stable_metrics" JSONB NOT NULL DEFAULT '{}'::jsonb,
  "last_updated" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  "confidence" VARCHAR(20) NULL,
  CONSTRAINT "memory_essence_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "unq_user_theme" UNIQUE ("user_id", "theme")
);

CREATE INDEX "idx_memory_essence_confidence" ON "public"."memory_essence" ("confidence" ASC);

CREATE TABLE "public"."memory_compression_log" (
  "id" SERIAL,
  "batch_key" VARCHAR(255) NOT NULL,
  "user_id" VARCHAR(20) NOT NULL,
  "from_state" VARCHAR(255) NOT NULL,
  "to_state" VARCHAR(255) NOT NULL,
  "messages_compressed" INTEGER NOT NULL DEFAULT 0,
  "compression_ratio" DOUBLE PRECISION NULL,
  "what_was_kept" TEXT NULL,
  "what_was_dropped" TEXT NULL,
  "compressed_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  CONSTRAINT "memory_compression_log_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "unq_memory_compression_batch" UNIQUE ("batch_key")
);

CREATE INDEX "idx_memory_compression_log_at" ON "public"."memory_compression_log" ("compressed_at" ASC);
CREATE INDEX "idx_memory_compression_log_user" ON "public"."memory_compression_log" ("user_id" ASC);
