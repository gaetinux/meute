CREATE TABLE projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE COLLATE NOCASE,
  description TEXT NOT NULL DEFAULT '',
  instructions TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE TABLE repos (
  id INTEGER PRIMARY KEY,
  path TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  kind TEXT,
  discovered_at TEXT NOT NULL
);
CREATE TABLE project_repos (
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
  PRIMARY KEY (project_id, repo_id)
);
CREATE TABLE tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL CHECK (length(trim(title)) > 0),
  description TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL CHECK (status IN ('todo','in_progress','blocked','review','done')),
  blocked_reason TEXT,
  priority TEXT NOT NULL CHECK (priority IN ('urgent','high','normal','low')),
  due_date TEXT,
  due_at TEXT,
  project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  repo_id INTEGER REFERENCES repos(id) ON DELETE SET NULL,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  completed_at TEXT,
  CHECK (due_date IS NULL OR due_at IS NULL),
  CHECK ((status = 'blocked') = (blocked_reason IS NOT NULL))
);
CREATE TABLE task_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  body TEXT NOT NULL,
  author TEXT NOT NULL, channel TEXT NOT NULL, session_id TEXT,
  created_at TEXT NOT NULL
);
-- Pas de clé étrangère : l'historique survit à la suppression de la tâche.
CREATE TABLE task_events (
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL,
  field TEXT NOT NULL, old_value TEXT, new_value TEXT,
  author TEXT NOT NULL, channel TEXT NOT NULL, session_id TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX task_events_task ON task_events(task_id);
