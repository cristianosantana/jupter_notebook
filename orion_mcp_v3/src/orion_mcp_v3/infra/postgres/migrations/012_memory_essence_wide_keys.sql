-- V2: campos de essência largos para temas gerados pelo destilador.

ALTER TABLE "public"."memory_essence"
  ALTER COLUMN "theme" TYPE VARCHAR(255),
  ALTER COLUMN "confidence" TYPE VARCHAR(255);
