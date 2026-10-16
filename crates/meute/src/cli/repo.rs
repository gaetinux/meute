//! `meute repo …`
use crate::app::App;
use crate::repos;
use clap::Subcommand;
use meute_core::repo::Repo;
use std::path::Path;

#[derive(Subcommand)]
pub enum RepoCommand {
    /// Lister les dépôts découverts.
    List {
        /// Sortie JSON.
        #[arg(long)]
        json: bool,
    },
}

/// Replaces a leading `$HOME` with `~` for display.
fn display_path(path: &Path, home: Option<&Path>) -> String {
    match home.and_then(|h| path.strip_prefix(h).ok()) {
        Some(rest) if rest.as_os_str().is_empty() => "~".to_owned(),
        Some(rest) => format!("~/{}", rest.display()),
        None => path.display().to_string(),
    }
}

fn line(repo: &Repo, home: Option<&Path>) -> String {
    format!(
        "{}  {}  {}",
        repo.name,
        repo.kind.as_deref().unwrap_or("-"),
        display_path(&repo.path, home)
    )
}

pub fn run(cmd: RepoCommand, app: &mut App) -> anyhow::Result<()> {
    match cmd {
        RepoCommand::List { json } => {
            let found = repos::scan(app)?;
            if json {
                println!("{}", serde_json::to_string(&found)?);
            } else {
                let home = std::env::var_os("HOME").map(std::path::PathBuf::from);
                for repo in &found {
                    println!("{}", line(repo, home.as_deref()));
                }
            }
        }
    }
    Ok(())
}
