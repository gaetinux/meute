//! Session repository.

use std::path::PathBuf;

use jiff::Timestamp;
use rusqlite::types::Type;
use rusqlite::{Connection, ErrorCode, Row, params};

use super::Db;
use super::time::{from_db, to_db};
use crate::error::{CoreError, Result};
use crate::project::ProjectId;
use crate::repo::RepoId;
use crate::session::{AgentKind, NewSession, Session, SessionFilter, SessionId, SessionState};
use crate::task::TaskId;

const SESSION_SELECT: &str = "SELECT id, agent, title, project_id, repo_id, task_id, cwd, state, \
     exit_code, last_activity_at, created_at, ended_at FROM sessions";

/// Minimum length of an identifier prefix accepted by [`Db::find_session`].
const MIN_PREFIX: usize = 4;

fn conversion<E>(idx: usize, err: E) -> rusqlite::Error
where
    E: std::error::Error + Send + Sync + 'static,
{
    rusqlite::Error::FromSqlConversionFailure(idx, Type::Text, Box::new(err))
}

fn parse_ts(idx: usize, text: &str) -> rusqlite::Result<Timestamp> {
    from_db(text).map_err(|e| conversion(idx, e))
}

fn row_to_session(row: &Row) -> rusqlite::Result<Session> {
    let id: String = row.get(0)?;
    let agent: String = row.get(1)?;
    let cwd: String = row.get(6)?;
    let state: String = row.get(7)?;
    let last_activity_at: String = row.get(9)?;
    let created_at: String = row.get(10)?;
    let ended_at: Option<String> = row.get(11)?;
    Ok(Session {
        id: SessionId::parse(&id).map_err(|e| conversion(0, e))?,
        agent: AgentKind::from_id(&agent).map_err(|e| conversion(1, e))?,
        title: row.get(2)?,
        project_id: row.get::<_, Option<i64>>(3)?.map(ProjectId),
        repo_id: row.get::<_, Option<i64>>(4)?.map(RepoId),
        task_id: row.get::<_, Option<i64>>(5)?.map(TaskId),
        cwd: PathBuf::from(cwd),
        state: SessionState::from_parts(&state, row.get(8)?).map_err(|e| conversion(7, e))?,
        last_activity_at: parse_ts(9, &last_activity_at)?,
        created_at: parse_ts(10, &created_at)?,
        ended_at: ended_at.map(|s| parse_ts(11, &s)).transpose()?,
    })
}

fn fetch_session(conn: &Connection, id: SessionId) -> Result<Session> {
    match conn.query_row(
        &format!("{SESSION_SELECT} WHERE id = ?1"),
        [id.to_string()],
        row_to_session,
    ) {
        Ok(session) => Ok(session),
        Err(rusqlite::Error::QueryReturnedNoRows) => Err(not_found(&id.to_string())),
        Err(other) => Err(other.into()),
    }
}

fn not_found(id: &str) -> CoreError {
    CoreError::NotFound {
        entity: "session",
        id: id.to_string(),
    }
}

/// Map a foreign-key violation to the entity that does not exist.
fn unknown_reference(err: rusqlite::Error, new: &NewSession) -> CoreError {
    let is_foreign_key = matches!(
        &err,
        rusqlite::Error::SqliteFailure(e, _)
            if e.code == ErrorCode::ConstraintViolation
                && e.extended_code == rusqlite::ffi::SQLITE_CONSTRAINT_FOREIGNKEY
    );
    if is_foreign_key {
        CoreError::Invalid(format!(
            "référence inconnue (projet {:?}, dépôt {:?}, tâche {:?})",
            new.project_id.map(|p| p.0),
            new.repo_id.map(|r| r.0),
            new.task_id.map(|t| t.0)
        ))
    } else {
        CoreError::Db(err)
    }
}

fn exit_code(state: SessionState) -> Option<i32> {
    match state {
        SessionState::Exited { code } => code,
        SessionState::Running
        | SessionState::SubagentRunning
        | SessionState::Compacting
        | SessionState::PermissionRequested
        | SessionState::WaitingInput
        | SessionState::Idle
        | SessionState::Unreachable
        | SessionState::MaybeStuck
        | SessionState::Unknown => None,
    }
}

impl Db {
    /// Create a session; `created_at` and `last_activity_at` are the current time.
    ///
    /// # Errors
    /// [`CoreError::Invalid`] on a blank title, a non UTF-8 `cwd` or an unknown reference.
    pub fn create_session(&mut self, new: NewSession) -> Result<Session> {
        let title = new.title.trim();
        if title.is_empty() {
            return Err(CoreError::Invalid("le titre ne peut pas être vide".into()));
        }
        let Some(cwd) = new.cwd.to_str() else {
            return Err(CoreError::Invalid(format!(
                "chemin non UTF-8 : {}",
                new.cwd.display()
            )));
        };
        let now = to_db(self.now());
        self.conn
            .execute(
                "INSERT INTO sessions (id, agent, title, project_id, repo_id, task_id, cwd, \
                 state, exit_code, last_activity_at, created_at) \
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?10)",
                params![
                    new.id.to_string(),
                    new.agent.id(),
                    title,
                    new.project_id.map(|p| p.0),
                    new.repo_id.map(|r| r.0),
                    new.task_id.map(|t| t.0),
                    cwd,
                    new.state.id(),
                    exit_code(new.state),
                    now
                ],
            )
            .map_err(|e| unknown_reference(e, &new))?;
        fetch_session(&self.conn, new.id)
    }

    /// Read one session.
    ///
    /// # Errors
    /// [`CoreError::NotFound`] when it does not exist.
    pub fn get_session(&self, id: SessionId) -> Result<Session> {
        fetch_session(&self.conn, id)
    }

    /// Find a session by full identifier or by a unique prefix of at least 4 characters.
    ///
    /// # Errors
    /// [`CoreError::NotFound`] when nothing matches or the prefix is too short;
    /// [`CoreError::Invalid`] when several sessions match.
    pub fn find_session(&self, prefix: &str) -> Result<Session> {
        let prefix = prefix.to_lowercase();
        if prefix.chars().count() < MIN_PREFIX {
            return Err(not_found(&prefix));
        }
        let mut stmt = self.conn.prepare(&format!(
            "{SESSION_SELECT} WHERE substr(id, 1, length(?1)) = ?1 ORDER BY id LIMIT 2"
        ))?;
        let mut found = stmt
            .query_map([&prefix], row_to_session)?
            .collect::<rusqlite::Result<Vec<_>>>()?;
        match (found.pop(), found.pop()) {
            (None, _) => Err(not_found(&prefix)),
            (Some(only), None) => Ok(only),
            (Some(_), Some(_)) => Err(CoreError::Invalid(format!(
                "identifiant de session ambigu : {prefix}"
            ))),
        }
    }

    /// List sessions by creation time then identifier; live ones only unless asked.
    ///
    /// # Errors
    /// Database errors.
    pub fn list_sessions(&self, filter: SessionFilter) -> Result<Vec<Session>> {
        let where_clause = if filter.include_ended {
            ""
        } else {
            " WHERE state NOT IN ('exited', 'unreachable')"
        };
        let mut stmt = self.conn.prepare(&format!(
            "{SESSION_SELECT}{where_clause} ORDER BY created_at, id"
        ))?;
        let rows = stmt.query_map([], row_to_session)?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }

    /// Change the state; stamps `last_activity_at`, and `ended_at` when leaving the live states.
    ///
    /// # Errors
    /// [`CoreError::NotFound`] when the session does not exist.
    pub fn set_session_state(&mut self, id: SessionId, state: SessionState) -> Result<Session> {
        let now = to_db(self.now());
        let tx = self.conn.transaction()?;
        let current = fetch_session(&tx, id)?;
        let ended_now = current.state.is_live() && !state.is_live();
        tx.execute(
            "UPDATE sessions SET state = ?2, exit_code = ?3, last_activity_at = ?4, \
             ended_at = CASE WHEN ?5 THEN ?4 ELSE ended_at END WHERE id = ?1",
            params![id.to_string(), state.id(), exit_code(state), now, ended_now],
        )?;
        let updated = fetch_session(&tx, id)?;
        tx.commit()?;
        Ok(updated)
    }

    /// `PRAGMA data_version`: changes when another connection wrote to the database.
    ///
    /// # Errors
    /// Database errors.
    pub fn data_version(&self) -> Result<i64> {
        Ok(self
            .conn
            .query_row("PRAGMA data_version", [], |row| row.get(0))?)
    }
}
