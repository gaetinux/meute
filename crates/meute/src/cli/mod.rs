//! `clap` definitions and dispatch.
mod project;
mod task;

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
    /// Gérer les projets.
    #[command(subcommand)]
    Project(project::ProjectCommand),
}

/// Runs the parsed command.
pub fn run(cli: Cli, mut app: App) -> anyhow::Result<()> {
    match cli.command {
        Some(Command::Task(cmd)) => task::run(cmd, &mut app),
        Some(Command::Project(cmd)) => project::run(cmd, &mut app),
        None => Ok(()),
    }
}
