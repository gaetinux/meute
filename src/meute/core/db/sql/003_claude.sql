ALTER TABLE sessions ADD COLUMN native_id TEXT;
ALTER TABLE sessions ADD COLUMN transcript_path TEXT;
ALTER TABLE sessions ADD COLUMN model TEXT;
ALTER TABLE sessions ADD COLUMN permission_mode TEXT;
ALTER TABLE sessions ADD COLUMN last_tool TEXT;
ALTER TABLE sessions ADD COLUMN pending_permission TEXT;
ALTER TABLE sessions ADD COLUMN last_message TEXT;
CREATE TABLE session_events (
  id INTEGER PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  event TEXT NOT NULL,
  detail TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE INDEX session_events_session ON session_events(session_id, created_at);
CREATE TABLE metric_samples (
  id INTEGER PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  model TEXT, effort TEXT,
  context_pct REAL, cost_usd REAL, duration_ms INTEGER,
  lines_added INTEGER, lines_removed INTEGER,
  worktree_name TEXT, worktree_branch TEXT, worktree_path TEXT,
  repo_host TEXT, repo_owner TEXT, repo_name TEXT
);
CREATE INDEX metric_samples_session ON metric_samples(session_id, created_at);
CREATE TABLE quota_samples (
  id INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  five_hour_pct REAL, five_hour_resets_at TEXT,
  seven_day_pct REAL, seven_day_resets_at TEXT
);
CREATE INDEX quota_samples_created ON quota_samples(created_at);
