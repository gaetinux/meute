//! Thin client for a dedicated tmux server.
#![warn(missing_docs)]
#![deny(clippy::print_stdout, clippy::print_stderr)]

mod client;
mod error;
mod version;

pub use client::Tmux;
pub use error::TmuxError;
pub use version::{MIN_VERSION, TmuxVersion, parse_version};
