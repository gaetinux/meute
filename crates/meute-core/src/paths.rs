//! XDG locations of meute files.

use crate::{CoreError, Result};
use directories::BaseDirs;
use std::path::{Path, PathBuf};

/// Resolved locations of meute files.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Paths {
    /// `<config>/meute/config.toml`.
    pub config_file: PathBuf,
    /// `<data>/meute/meute.db`.
    pub db_file: PathBuf,
    /// `<state>/meute/`.
    pub state_dir: PathBuf,
}

impl Paths {
    /// Builds paths from explicit XDG base directories (pure, no environment access).
    #[must_use]
    pub fn from_roots(config_home: &Path, data_home: &Path, state_home: &Path) -> Paths {
        Paths {
            config_file: config_home.join("meute").join("config.toml"),
            db_file: data_home.join("meute").join("meute.db"),
            state_dir: state_home.join("meute"),
        }
    }

    /// Resolves paths from the environment (`XDG_*_HOME` honored on Linux).
    ///
    /// # Errors
    /// Returns [`CoreError::Invalid`] when no home directory can be determined.
    pub fn from_env() -> Result<Paths> {
        let base = BaseDirs::new()
            .ok_or_else(|| CoreError::Invalid("dossier personnel introuvable".to_string()))?;
        let state = base.state_dir().unwrap_or_else(|| base.data_dir());
        Ok(Paths::from_roots(base.config_dir(), base.data_dir(), state))
    }

    /// Creates the directories that hold the config file, the database and the state.
    ///
    /// # Errors
    /// Returns [`CoreError::Io`] when a directory cannot be created.
    pub fn ensure_dirs(&self) -> Result<()> {
        for dir in [
            self.config_file.parent(),
            self.db_file.parent(),
            Some(self.state_dir.as_path()),
        ]
        .into_iter()
        .flatten()
        {
            std::fs::create_dir_all(dir)?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;

    #[test]
    fn from_roots_appends_meute_segments() {
        let p = Paths::from_roots(Path::new("/t/c"), Path::new("/t/d"), Path::new("/t/s"));
        assert_eq!(p.config_file, Path::new("/t/c/meute/config.toml"));
        assert_eq!(p.db_file, Path::new("/t/d/meute/meute.db"));
        assert_eq!(p.state_dir, Path::new("/t/s/meute"));
    }

    #[test]
    fn ensure_dirs_creates_parent_directories() {
        let dir = tempfile::tempdir().unwrap();
        let p = Paths::from_roots(
            &dir.path().join("c"),
            &dir.path().join("d"),
            &dir.path().join("s"),
        );
        p.ensure_dirs().unwrap();
        assert!(dir.path().join("c/meute").is_dir());
        assert!(dir.path().join("d/meute").is_dir());
        assert!(dir.path().join("s/meute").is_dir());
    }
}
