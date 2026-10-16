//! File-system behaviour of the configuration, added after a cargo-mutants run.

use meute_core::CoreError;
use meute_core::config::{Config, config_get, config_set, load_config};

#[test]
fn absent_file_yields_defaults_everywhere() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("absent.toml");
    assert_eq!(load_config(&path).unwrap(), Config::default());
    assert_eq!(config_get(&path, "ui.board_width").unwrap(), "60");
    config_set(&path, "ui.board_width", "80").unwrap();
    assert_eq!(config_get(&path, "ui.board_width").unwrap(), "80");
}

#[test]
fn unreadable_path_is_an_io_error_not_defaults() {
    let dir = tempfile::tempdir().unwrap();
    // A directory exists but cannot be read as a file.
    let err = load_config(dir.path()).unwrap_err();
    assert!(matches!(err, CoreError::Io(_)), "{err:?}");
    assert!(config_get(dir.path(), "ui.board_width").is_err());
}
