//! TOML configuration of meute.

use crate::{CoreError, Result};
use serde::{Deserialize, Serialize};
use std::path::Path;

/// Configuration written on first run.
pub const DEFAULT_CONFIG: &str = r#"# Configuration de meute — modifiable à la main ou avec `meute config set`.

[repos]
# Dossiers où meute cherche les dépôts Git (profondeur 3).
roots = ["~/git"]

[claude]
# Mode de permission des sessions Claude lancées par meute :
# manual, acceptEdits, plan, auto, dontAsk, bypassPermissions.
permission_mode = "manual"

[ui]
# Largeur du tableau de bord, en colonnes.
board_width = 60
# En dessous de cette largeur, le tableau de bord passe en plein écran.
narrow_threshold = 120

[quotas]
# Heures pleines : jours ouvrés, de peak_start_hour à peak_end_hour, dans ce fuseau.
peak_timezone = "America/New_York"
peak_start_hour = 8
peak_end_hour = 14
"#;

/// Whole configuration. Unknown top-level sections are ignored.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct Config {
    /// Git repository discovery.
    pub repos: ReposConfig,
    /// Claude sessions.
    pub claude: ClaudeConfig,
    /// User interface.
    pub ui: UiConfig,
    /// Quota windows.
    pub quotas: QuotasConfig,
}

/// `[repos]` section.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct ReposConfig {
    /// Folders scanned for Git repositories.
    pub roots: Vec<String>,
}

impl Default for ReposConfig {
    fn default() -> Self {
        Self {
            roots: vec!["~/git".to_string()],
        }
    }
}

/// `[claude]` section.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct ClaudeConfig {
    /// Permission mode of launched sessions.
    pub permission_mode: String,
}

impl Default for ClaudeConfig {
    fn default() -> Self {
        Self {
            permission_mode: "manual".to_string(),
        }
    }
}

/// `[ui]` section.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct UiConfig {
    /// Dashboard width in columns.
    pub board_width: u16,
    /// Below this terminal width the dashboard goes full screen.
    pub narrow_threshold: u16,
}

impl Default for UiConfig {
    fn default() -> Self {
        Self {
            board_width: 60,
            narrow_threshold: 120,
        }
    }
}

/// `[quotas]` section.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct QuotasConfig {
    /// IANA time zone of the peak window.
    pub peak_timezone: String,
    /// First peak hour (inclusive).
    pub peak_start_hour: u8,
    /// Last peak hour (exclusive).
    pub peak_end_hour: u8,
}

impl Default for QuotasConfig {
    fn default() -> Self {
        Self {
            peak_timezone: "America/New_York".to_string(),
            peak_start_hour: 8,
            peak_end_hour: 14,
        }
    }
}

fn write_atomic(path: &Path, text: &str) -> Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let mut tmp = path.as_os_str().to_owned();
    tmp.push(".tmp");
    std::fs::write(&tmp, text)?;
    std::fs::rename(&tmp, path)?;
    Ok(())
}

fn config_error(path: &Path, message: impl ToString) -> CoreError {
    CoreError::Config {
        path: path.to_path_buf(),
        message: message.to_string(),
    }
}

/// Reads the file text, or an empty string when the file is absent.
fn read_or_empty(path: &Path) -> Result<String> {
    match std::fs::read_to_string(path) {
        Ok(text) => Ok(text),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(String::new()),
        Err(e) => Err(e.into()),
    }
}

/// Writes [`DEFAULT_CONFIG`] if `path` does not exist. Returns `true` if created.
///
/// # Errors
/// Returns [`CoreError::Io`] when the file cannot be written.
pub fn ensure_config(path: &Path) -> Result<bool> {
    if path.exists() {
        return Ok(false);
    }
    write_atomic(path, DEFAULT_CONFIG)?;
    Ok(true)
}

/// Loads the configuration; an absent file yields the defaults.
///
/// # Errors
/// Returns [`CoreError::Config`] (with path and line) on invalid TOML.
pub fn load_config(path: &Path) -> Result<Config> {
    toml::from_str(&read_or_empty(path)?).map_err(|e| config_error(path, e))
}

/// Splits `section.key` and checks it exists in the default configuration.
fn split_known_key<'a>(key: &'a str, defaults: &toml::Table) -> Result<(&'a str, &'a str)> {
    let known = key.split_once('.').filter(|(s, k)| {
        defaults
            .get(*s)
            .and_then(toml::Value::as_table)
            .is_some_and(|t| t.contains_key(*k))
    });
    known.ok_or_else(|| CoreError::Invalid(format!("clé inconnue : {key}")))
}

fn default_table() -> Result<toml::Table> {
    toml::Table::try_from(Config::default()).map_err(|e| CoreError::Invalid(e.to_string()))
}

fn display_value(value: &toml::Value) -> String {
    value
        .as_str()
        .map_or_else(|| value.to_string(), str::to_string)
}

/// Returns the value of the dotted key `section.key` (the default when absent).
///
/// # Errors
/// [`CoreError::Invalid`] for an unknown key, [`CoreError::Config`] for invalid TOML.
pub fn config_get(path: &Path, key: &str) -> Result<String> {
    let defaults = default_table()?;
    let (section, name) = split_known_key(key, &defaults)?;
    let current: toml::Table = read_or_empty(path)?
        .parse()
        .map_err(|e| config_error(path, e))?;
    let value = current
        .get(section)
        .and_then(toml::Value::as_table)
        .and_then(|t| t.get(name))
        .or_else(|| {
            defaults
                .get(section)
                .and_then(toml::Value::as_table)
                .and_then(|t| t.get(name))
        });
    value
        .map(display_value)
        .ok_or_else(|| CoreError::Invalid(format!("clé inconnue : {key}")))
}

/// Sets `section.key`, preserving comments and unknown keys. The value is read as
/// TOML when valid, as a string otherwise. The result is validated before writing.
///
/// # Errors
/// [`CoreError::Invalid`] for an unknown key or a value of the wrong type (file untouched).
pub fn config_set(path: &Path, key: &str, value: &str) -> Result<()> {
    let defaults = default_table()?;
    let (section, name) = split_known_key(key, &defaults)?;
    let mut doc: toml_edit::DocumentMut = read_or_empty(path)?
        .parse()
        .map_err(|e| config_error(path, e))?;
    let new: toml_edit::Value = value
        .parse()
        .unwrap_or_else(|_| toml_edit::Value::from(value));
    let table = doc
        .entry(section)
        .or_insert_with(toml_edit::table)
        .as_table_mut()
        .ok_or_else(|| CoreError::Invalid(format!("« {section} » n'est pas une section")))?;
    match table.get_mut(name).and_then(toml_edit::Item::as_value_mut) {
        Some(slot) => {
            let decor = slot.decor().clone();
            *slot = new;
            *slot.decor_mut() = decor;
        }
        None => {
            table.insert(name, toml_edit::Item::Value(new));
        }
    }
    let text = doc.to_string();
    toml::from_str::<Config>(&text).map_err(|e| CoreError::Invalid(format!("{key} : {e}")))?;
    write_atomic(path, &text)
}

#[cfg(test)]
mod tests;
