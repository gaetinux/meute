//! Command-line entry point of meute.
mod app;
mod cli;
mod render;

use clap::Parser;
use meute_core::CoreError;
use std::process::ExitCode;

/// Exit code for a general error.
const EXIT_GENERAL: u8 = 1;
/// Exit code for a version conflict.
const EXIT_CONFLICT: u8 = 3;
/// Exit code for a missing entity.
const EXIT_NOT_FOUND: u8 = 4;

fn exit_code(err: &anyhow::Error) -> u8 {
    match err.downcast_ref::<CoreError>() {
        Some(CoreError::Conflict { .. }) => EXIT_CONFLICT,
        Some(CoreError::NotFound { .. }) => EXIT_NOT_FOUND,
        Some(
            CoreError::Config { .. }
            | CoreError::Io(_)
            | CoreError::Invalid(_)
            | CoreError::Db(_)
            | CoreError::Migration(_),
        )
        | None => EXIT_GENERAL,
    }
}

fn main() -> ExitCode {
    let cli = cli::Cli::parse();
    match app::App::init().and_then(|app| cli::run(cli, app)) {
        Ok(()) => ExitCode::SUCCESS,
        Err(err) => {
            eprintln!("meute : {err:#}");
            ExitCode::from(exit_code(&err))
        }
    }
}
