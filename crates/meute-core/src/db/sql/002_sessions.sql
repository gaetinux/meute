CREATE TABLE sessions (
  id TEXT PRIMARY KEY CHECK (length(id) = 36),
  agent TEXT NOT NULL CHECK (agent IN ('claude','bash')),
  title TEXT NOT NULL CHECK (length(trim(title)) > 0),
  project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  repo_id INTEGER REFERENCES repos(id) ON DELETE SET NULL,
  task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
  cwd TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('running','subagent_running','compacting',
    'permission_requested','waiting_input','idle','exited','unreachable','maybe_stuck','unknown')),
  exit_code INTEGER CHECK (exit_code IS NULL OR state = 'exited'),
  last_activity_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  ended_at TEXT
);
CREATE INDEX sessions_state ON sessions(state);
