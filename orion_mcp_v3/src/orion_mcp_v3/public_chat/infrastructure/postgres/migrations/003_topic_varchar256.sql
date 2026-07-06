-- Amplia topic para contratos com período composto (ex.: 2026-01..2026-06).

ALTER TABLE "public"."public_chat_questions"
    ALTER COLUMN "topic" TYPE VARCHAR(256);

ALTER TABLE "public"."public_chat_responses"
    ALTER COLUMN "topic" TYPE VARCHAR(256);
