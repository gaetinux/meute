//! Error type shared by all of `meute-core`.

use std::path::PathBuf;

use crate::task::Task;

/// Errors returned by `meute-core`.
#[derive(Debug, thiserror::Error)]
pub enum CoreError {
    /// A configuration file could not be parsed.
    #[error("configuration invalide ({}) : {message}", path.display())]
    Config {
        /// File that failed to parse.
        path: PathBuf,
        /// Parser message, including the line number.
        message: String,
    },
    /// Filesystem error.
    #[error("erreur d'entrée/sortie : {0}")]
    Io(#[from] std::io::Error),
    /// Invalid user input (unknown key, wrong type, ...).
    #[error("valeur invalide : {0}")]
    Invalid(String),
    /// An entity looked up by identifier does not exist.
    #[error("{entity} introuvable : {id}")]
    NotFound {
        /// Kind of entity (e.g. `tâche`).
        entity: &'static str,
        /// Identifier as displayed to the user.
        id: String,
    },
    /// The task was modified since the caller read it.
    #[error("modifiée entre-temps (version actuelle : {})", current.version)]
    Conflict {
        /// Current stored state of the task.
        current: Box<Task>,
    },
    /// SQLite error.
    #[error("erreur de base de données : {0}")]
    Db(#[from] rusqlite::Error),
    /// Schema migration failure.
    #[error("échec de la migration : {0}")]
    Migration(String),
}

/// Result alias using [`CoreError`].
pub type Result<T> = std::result::Result<T, CoreError>;
