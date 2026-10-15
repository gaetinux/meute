//! Error type shared by all of `meute-core`.

use std::path::PathBuf;

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
}

/// Result alias using [`CoreError`].
pub type Result<T> = std::result::Result<T, CoreError>;
