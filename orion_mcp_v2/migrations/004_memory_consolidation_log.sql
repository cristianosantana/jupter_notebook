CREATE TABLE IF NOT EXISTS memory_consolidation_log (
  id SERIAL PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL,
  job_id TEXT,
  status VARCHAR(32) NOT NULL,
  error_message TEXT,
  sessions_processed INT,
  consolidated_at TIMESTAMPTZ,
  next_retry_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS memory_consolidation_log_user_idx ON memory_consolidation_log (user_id);
CREATE INDEX IF NOT EXISTS memory_consolidation_log_status_idx ON memory_consolidation_log (status);
