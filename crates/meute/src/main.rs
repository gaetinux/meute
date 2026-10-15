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

/// Joins an error and its causes with French-style ` : ` separators.
fn error_chain(err: &anyhow::Error) -> String {
    err.chain()
        .map(ToString::to_string)
        .collect::<Vec<_>>()
        .join(" : ")
}

fn main() -> ExitCode {
    let cli = cli::Cli::parse();
    let (result, now) = match app::App::init() {
        Ok(app) => {
            let now = app.now.clone();
            (cli::run(cli, app), Some(now))
        }
        Err(err) => (Err(err), None),
    };
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(err) => {
            eprintln!("meute : {}", error_chain(&err));
            if let (Some(CoreError::Conflict { current }), Some(now)) =
                (err.downcast_ref::<CoreError>(), now)
            {
                eprintln!("{}", render::task_line(current, &now));
            }
            ExitCode::from(exit_code(&err))
        }
    }
}
