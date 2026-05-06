CREATE TABLE IF NOT EXISTS memory_curta_analytics (
  id SERIAL PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  category VARCHAR(50) NOT NULL,
  summary JSONB NOT NULL,
  consolidated_at TIMESTAMPTZ,
  ttl_expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(user_id, category)
);

CREATE INDEX IF NOT EXISTS memory_curta_user_cat_idx ON memory_curta_analytics (user_id, category);
