//! Core library of meute: all business logic lives here.
#![warn(missing_docs)]
#![deny(clippy::print_stdout, clippy::print_stderr)]

pub mod actor;
pub mod config;
pub mod db;
pub mod error;
pub mod paths;
pub mod project;
pub mod quick_add;
pub mod task;
pub mod views;

pub use error::{CoreError, Result};
