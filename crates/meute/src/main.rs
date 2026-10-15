//! Command-line entry point of meute.
use clap::Parser;

/// Command-line interface of meute.
#[derive(Parser)]
#[command(name = "meute", version)]
struct Cli {}

fn main() {
    Cli::parse();
}
