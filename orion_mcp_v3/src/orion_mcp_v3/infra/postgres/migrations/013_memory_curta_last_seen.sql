-- V2: marcador de rotação para expirar conhecimento remissivo não renovado.

ALTER TABLE "public"."memory_curta"
  ADD COLUMN IF NOT EXISTS "last_seen_at" TIMESTAMP WITH TIME ZONE;

UPDATE "public"."memory_curta"
SET "last_seen_at" = COALESCE("last_seen_at", "consolidated_at", now())
WHERE "last_seen_at" IS NULL;

ALTER TABLE "public"."memory_curta"
  ALTER COLUMN "last_seen_at" SET DEFAULT now(),
  ALTER COLUMN "last_seen_at" SET NOT NULL;

CREATE INDEX IF NOT EXISTS "idx_memory_curta_last_seen"
  ON "public"."memory_curta" ("last_seen_at" ASC);
