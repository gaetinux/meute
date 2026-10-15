//! Application context shared by all commands.
use anyhow::{Context, anyhow};
use jiff::Zoned;
use meute_core::actor::{Actor, Author, Channel};
use meute_core::config::{ensure_config, load_config};
use meute_core::db::Db;
use meute_core::paths::Paths;
use meute_core::project::Project;
use std::path::PathBuf;
use std::time::Duration;

/// Busy timeout of the CLI connection.
const BUSY_TIMEOUT: Duration = Duration::from_millis(5000);

/// Everything a command needs: database, clock and acting identity.
pub struct App {
    pub db: Db,
    pub now: Zoned,
    pub actor: Actor,
    pub config_file: PathBuf,
}

impl App {
    /// Prepares directories and configuration, then opens the database.
    pub fn init() -> anyhow::Result<App> {
        let paths = Paths::from_env()?;
        paths.ensure_dirs()?;
        ensure_config(&paths.config_file)?;
        load_config(&paths.config_file)?;
        let now = current_time()?;
        let timestamp = now.timestamp();
        let db = Db::open(&paths.db_file, BUSY_TIMEOUT)?;
        // `MEUTE_NOW` also drives stored timestamps so end-to-end tests are deterministic.
        let db = if std::env::var_os("MEUTE_NOW").is_some() {
            db.with_clock(move || timestamp)
        } else {
            db
        };
        let actor = Actor {
            author: Author::User,
            channel: Channel::Cli,
            session_id: std::env::var("MEUTE_SESSION").ok(),
        };
        Ok(App {
            db,
            now,
            actor,
            config_file: paths.config_file,
        })
    }

    /// Finds a project by name or fails with the list of known projects.
    pub fn require_project(&self, name: &str) -> anyhow::Result<Project> {
        if let Some(project) = self.db.project_by_name(name)? {
            return Ok(project);
        }
        let known: Vec<String> = self
            .db
            .list_projects()?
            .into_iter()
            .map(|p| p.name)
            .collect();
        Err(anyhow!(
            "projet inconnu : {name} (projets : {})",
            known.join(", ")
        ))
    }
}

fn current_time() -> anyhow::Result<Zoned> {
    match std::env::var("MEUTE_NOW") {
        Ok(raw) => raw
            .parse::<Zoned>()
            .with_context(|| format!("variable MEUTE_NOW invalide : {raw}")),
        Err(std::env::VarError::NotPresent) => Ok(Zoned::now()),
        Err(std::env::VarError::NotUnicode(_)) => Err(anyhow!("variable MEUTE_NOW invalide")),
    }
}
