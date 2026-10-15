//! `meute config …`
use clap::Subcommand;
use meute_core::config::{config_get, config_set, ensure_config};
use meute_core::paths::Paths;

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

/// Runs a config command; it needs only the paths, so it works on an invalid file.
pub fn run(cmd: ConfigCommand) -> anyhow::Result<()> {
    let file = Paths::from_env()?.config_file;
    match cmd {
        ConfigCommand::Path => println!("{}", file.display()),
        ConfigCommand::Get { key } => {
            ensure_config(&file)?;
            println!("{}", config_get(&file, &key)?);
        }
        ConfigCommand::Set { key, value } => {
            ensure_config(&file)?;
            config_set(&file, &key, &value)?;
        }
    }
    Ok(())
}
