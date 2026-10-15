//! Project repository.

use jiff::Timestamp;
use rusqlite::{ErrorCode, OptionalExtension, Row, params};

use super::Db;
use crate::error::{CoreError, Result};
use crate::project::{Project, ProjectId};

const COLUMNS: &str = "id, name, description, instructions, created_at";

fn row_to_project(row: &Row) -> rusqlite::Result<Project> {
    let created_at: String = row.get(4)?;
    Ok(Project {
        id: ProjectId(row.get(0)?),
        name: row.get(1)?,
        description: row.get(2)?,
        instructions: row.get(3)?,
        created_at: created_at.parse::<Timestamp>().map_err(|e| {
            rusqlite::Error::FromSqlConversionFailure(4, rusqlite::types::Type::Text, Box::new(e))
        })?,
    })
}

impl Db {
    /// Create a project; the name is trimmed and unique ignoring case.
    ///
    /// # Errors
    /// [`CoreError::Invalid`] on an empty or already used name.
    pub fn create_project(&mut self, name: &str, description: &str) -> Result<Project> {
        let name = name.trim();
        if name.is_empty() {
            return Err(CoreError::Invalid(
                "le nom du projet ne peut pas être vide".into(),
            ));
        }
        let now = self.now().to_string();
        let tx = self.conn.transaction()?;
        let inserted = tx.execute(
            "INSERT INTO projects (name, description, created_at) VALUES (?1, ?2, ?3)",
            params![name, description, now],
        );
        match inserted {
            Ok(_) => {}
            Err(rusqlite::Error::SqliteFailure(e, _))
                if e.code == ErrorCode::ConstraintViolation =>
            {
                return Err(CoreError::Invalid(format!("projet déjà existant : {name}")));
            }
            Err(other) => return Err(other.into()),
        }
        let id = tx.last_insert_rowid();
        let project = tx.query_row(
            &format!("SELECT {COLUMNS} FROM projects WHERE id = ?1"),
            [id],
            row_to_project,
        )?;
        tx.commit()?;
        Ok(project)
    }

    /// Find a project by name, ignoring case.
    pub fn project_by_name(&self, name: &str) -> Result<Option<Project>> {
        Ok(self
            .conn
            .query_row(
                &format!("SELECT {COLUMNS} FROM projects WHERE name = ?1"),
                [name.trim()],
                row_to_project,
            )
            .optional()?)
    }

    /// All projects, sorted by name.
    pub fn list_projects(&self) -> Result<Vec<Project>> {
        let mut stmt = self.conn.prepare(&format!(
            "SELECT {COLUMNS} FROM projects ORDER BY name COLLATE NOCASE, id"
        ))?;
        let rows = stmt.query_map([], row_to_project)?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }
}
