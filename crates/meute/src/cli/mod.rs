//! `clap` definitions and dispatch.
mod config;
mod project;
mod task;
mod task_edit;

use crate::app::App;
use clap::{Parser, Subcommand};

/// Command-line interface of meute.
#[derive(Parser)]
#[command(name = "meute", version)]
pub struct Cli {
    #[command(subcommand)]
    command: Option<Command>,
}

#[derive(Subcommand)]
enum Command {
    /// Gérer les tâches.
    #[command(subcommand)]
    Task(task::TaskCommand),
    /// Gérer la configuration.
    #[command(subcommand)]
    Config(config::ConfigCommand),
    /// Gérer les projets.
    #[command(subcommand)]
    Project(project::ProjectCommand),
}

/// Runs the command when it needs no [`App`] (configuration commands); otherwise
/// hands the command back.
pub fn run_without_app(cli: Cli) -> Result<anyhow::Result<()>, Box<Cli>> {
    match cli.command {
        Some(Command::Config(cmd)) => Ok(config::run(cmd)),
        Some(Command::Task(_) | Command::Project(_)) | None => Err(Box::new(cli)),
    }
}

/// Runs the parsed command.
pub fn run(cli: Cli, mut app: App) -> anyhow::Result<()> {
    match cli.command {
        Some(Command::Task(cmd)) => task::run(cmd, &mut app),
        Some(Command::Config(cmd)) => config::run(cmd),
        Some(Command::Project(cmd)) => project::run(cmd, &mut app),
        None => Ok(()),
    }
}
