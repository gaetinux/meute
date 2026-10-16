use super::*;
use crate::CoreError;

#[test]
fn ensure_config_writes_default_once_and_never_overwrites() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("config.toml");
    assert!(ensure_config(&path).unwrap());
    std::fs::write(&path, "# mine\n[ui]\nboard_width = 80\n").unwrap();
    assert!(!ensure_config(&path).unwrap());
    assert_eq!(
        std::fs::read_to_string(&path).unwrap(),
        "# mine\n[ui]\nboard_width = 80\n"
    );
}

#[test]
fn default_config_parses_to_default_values() {
    let cfg: Config = toml::from_str(DEFAULT_CONFIG).unwrap();
    assert_eq!(cfg.repos.roots, vec!["~/git".to_string()]);
    assert_eq!(cfg.claude.permission_mode, "manual");
    assert_eq!((cfg.ui.board_width, cfg.ui.narrow_threshold), (60, 120));
    assert_eq!(cfg.quotas.peak_timezone, "America/New_York");
    assert_eq!(
        (cfg.quotas.peak_start_hour, cfg.quotas.peak_end_hour),
        (8, 14)
    );
}

#[test]
fn missing_keys_fall_back_to_defaults() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("config.toml");
    std::fs::write(&path, "[ui]\nboard_width = 80\n").unwrap();
    let cfg = load_config(&path).unwrap();
    assert_eq!(cfg.ui.board_width, 80);
    assert_eq!(cfg.ui.narrow_threshold, 120);
}

#[test]
fn config_set_preserves_comments_and_unknown_keys() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("config.toml");
    std::fs::write(
        &path,
        "# garde-moi\n[ui]\nboard_width = 60 # largeur\n[perso]\nx = 1\n",
    )
    .unwrap();
    config_set(&path, "ui.board_width", "72").unwrap();
    let text = std::fs::read_to_string(&path).unwrap();
    assert!(text.contains("# garde-moi") && text.contains("# largeur") && text.contains("[perso]"));
    assert_eq!(config_get(&path, "ui.board_width").unwrap(), "72");
}

#[test]
fn config_set_rejects_unknown_key_and_wrong_type() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("config.toml");
    ensure_config(&path).unwrap();
    let before = std::fs::read_to_string(&path).unwrap();
    assert!(matches!(
        config_set(&path, "ui.nope", "1"),
        Err(CoreError::Invalid(_))
    ));
    assert!(matches!(
        config_set(&path, "ui.board_width", "large"),
        Err(CoreError::Invalid(_))
    ));
    assert_eq!(std::fs::read_to_string(&path).unwrap(), before);
}

#[test]
fn invalid_toml_reports_path_and_line_without_touching_file() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("config.toml");
    std::fs::write(&path, "[ui]\nboard_width = = 3\n").unwrap();
    let err = load_config(&path).unwrap_err();
    let msg = err.to_string();
    assert!(
        msg.contains("config.toml") && msg.contains("line 2"),
        "{msg}"
    );
    assert_eq!(
        std::fs::read_to_string(&path).unwrap(),
        "[ui]\nboard_width = = 3\n"
    );
}

#[test]
fn config_get_returns_default_for_absent_key() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("config.toml");
    std::fs::write(&path, "").unwrap();
    assert_eq!(
        config_get(&path, "claude.permission_mode").unwrap(),
        "manual"
    );
}

#[test]
fn load_config_tolerates_unknown_keys_in_known_sections() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("config.toml");
    std::fs::write(&path, "[ui]\nboad_width = 1\nboard_width = 70\n").unwrap();
    let cfg = load_config(&path).unwrap();
    assert_eq!(cfg.ui.board_width, 70);
    assert_eq!(cfg.ui.narrow_threshold, 120);
}
