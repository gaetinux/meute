//! Core library of meute: all business logic lives here.
#![warn(missing_docs)]
#![deny(clippy::print_stdout, clippy::print_stderr)]

pub mod config;
pub mod error;
pub mod paths;

pub use error::{CoreError, Result};
