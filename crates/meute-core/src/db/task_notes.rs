//! Task notes.

use rusqlite::{Row, TransactionBehavior, params};

use super::Db;
use super::tasks::fetch_task;
use super::time::{from_db, to_db};
use crate::actor::{Actor, Author, Channel};
use crate::error::{CoreError, Result};
use crate::task::{Note, TaskId};

fn row_to_note(row: &Row) -> rusqlite::Result<Note> {
    let conv = |idx: usize, e: crate::CoreError| {
        rusqlite::Error::FromSqlConversionFailure(idx, rusqlite::types::Type::Text, Box::new(e))
    };
    let author: String = row.get(3)?;
    let channel: String = row.get(4)?;
    let created_at: String = row.get(6)?;
    Ok(Note {
        id: row.get(0)?,
        task_id: TaskId(row.get(1)?),
        body: row.get(2)?,
        author: Author::from_id(&author).map_err(|e| conv(3, e))?,
        channel: Channel::from_id(&channel).map_err(|e| conv(4, e))?,
        session_id: row.get(5)?,
        created_at: from_db(&created_at).map_err(|e| {
            rusqlite::Error::FromSqlConversionFailure(6, rusqlite::types::Type::Text, Box::new(e))
        })?,
    })
}

impl Db {
    /// Add a note to a task; the task version is not changed.
    ///
    /// # Errors
    /// [`CoreError::Invalid`] on a blank body; [`CoreError::NotFound`] when
    /// the task does not exist.
    pub fn add_note(&mut self, id: TaskId, body: &str, actor: &Actor) -> Result<Note> {
        let body = body.trim();
        if body.is_empty() {
            return Err(CoreError::Invalid("la note ne peut pas être vide".into()));
        }
        let now = to_db(self.now());
        let tx = self
            .conn
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        fetch_task(&tx, id)?;
        tx.execute(
            "INSERT INTO task_notes (task_id, body, author, channel, session_id, created_at) \
             VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            params![
                id.0,
                body,
                actor.author.id(),
                actor.channel.id(),
                actor.session_id,
                now
            ],
        )?;
        let note_id = tx.last_insert_rowid();
        let note = tx.query_row(
            "SELECT id, task_id, body, author, channel, session_id, created_at \
             FROM task_notes WHERE id = ?1",
            [note_id],
            row_to_note,
        )?;
        tx.commit()?;
        Ok(note)
    }

    /// Notes of a task, oldest first.
    pub fn notes(&self, id: TaskId) -> Result<Vec<Note>> {
        let mut stmt = self.conn.prepare(
            "SELECT id, task_id, body, author, channel, session_id, created_at \
             FROM task_notes WHERE task_id = ?1 ORDER BY id",
        )?;
        let rows = stmt.query_map([id.0], row_to_note)?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }
}
