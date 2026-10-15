//! Core library of meute: all business logic lives here.
#![warn(missing_docs)]
#![deny(clippy::print_stdout, clippy::print_stderr)]

pub mod actor;
pub mod config;
pub mod error;
pub mod paths;
pub mod project;
pub mod task;

pub use error::{CoreError, Result};
