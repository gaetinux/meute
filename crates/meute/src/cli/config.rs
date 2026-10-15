//! `meute config …`
use crate::app::App;
use clap::Subcommand;
use meute_core::config::{config_get, config_set};

#[derive(Subcommand)]
pub enum ConfigCommand {
    /// Afficher le chemin du fichier de configuration.
    Path,
    /// Lire une clé (`section.clé`).
    Get {
        /// Clé, par exemple `ui.board_width`.
        key: String,
    },
    /// Écrire une clé (`section.clé`).
    Set {
        /// Clé, par exemple `ui.board_width`.
        key: String,
        /// Valeur (TOML si valide, texte sinon).
        value: String,
    },
}

pub fn run(cmd: ConfigCommand, app: &App) -> anyhow::Result<()> {
    match cmd {
        ConfigCommand::Path => println!("{}", app.config_file.display()),
        ConfigCommand::Get { key } => println!("{}", config_get(&app.config_file, &key)?),
        ConfigCommand::Set { key, value } => config_set(&app.config_file, &key, &value)?,
    }
    Ok(())
}
