//! Repository table access.

use std::path::PathBuf;

use rusqlite::{Row, params};

use super::Db;
use super::time::{from_db, to_db};
use crate::error::{CoreError, Result};
use crate::repo::{NewRepo, Repo, RepoId};

fn row_to_repo(row: &Row) -> rusqlite::Result<Repo> {
    let path: String = row.get(1)?;
    let discovered_at: String = row.get(4)?;
    Ok(Repo {
        id: RepoId(row.get(0)?),
        path: PathBuf::from(path),
        name: row.get(2)?,
        kind: row.get(3)?,
        discovered_at: from_db(&discovered_at).map_err(|e| {
            rusqlite::Error::FromSqlConversionFailure(4, rusqlite::types::Type::Text, Box::new(e))
        })?,
    })
}

impl Db {
    /// Register scan results in one transaction: new paths are inserted,
    /// known paths get their name and kind refreshed. Repositories absent from
    /// `found` are never deleted. Returns the full list.
    ///
    /// # Errors
    /// [`CoreError::Invalid`] on a non-UTF-8 path.
    pub fn sync_repos(&mut self, found: &[NewRepo]) -> Result<Vec<Repo>> {
        let now = to_db(self.now());
        let tx = self.conn.transaction()?;
        for repo in found {
            let path = repo.path.to_str().ok_or_else(|| {
                CoreError::Invalid(format!("chemin non UTF-8 : {}", repo.path.display()))
            })?;
            tx.execute(
                "INSERT INTO repos (path, name, kind, discovered_at) VALUES (?1, ?2, ?3, ?4)
                 ON CONFLICT(path) DO UPDATE SET name = excluded.name, kind = excluded.kind",
                params![path, repo.name, repo.kind, now],
            )?;
        }
        tx.commit()?;
        self.list_repos()
    }

    /// All repositories, sorted by name (ignoring case) then path.
    pub fn list_repos(&self) -> Result<Vec<Repo>> {
        let mut stmt = self.conn.prepare(
            "SELECT id, path, name, kind, discovered_at FROM repos
             ORDER BY name COLLATE NOCASE, path",
        )?;
        let rows = stmt.query_map([], row_to_repo)?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }
}
