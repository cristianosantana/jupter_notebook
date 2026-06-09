-- V2: campos de auditoria largos para payloads reais do destilador.

ALTER TABLE "public"."memory_compression_log"
  ALTER COLUMN "batch_key" TYPE VARCHAR(255),
  ALTER COLUMN "from_state" TYPE VARCHAR(255),
  ALTER COLUMN "to_state" TYPE VARCHAR(255);
