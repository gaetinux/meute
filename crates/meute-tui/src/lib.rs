//! Terminal user interface of meute: a minimal dashboard of sessions and repositories.
#![warn(missing_docs)]

mod board;
mod render;
mod run;

pub use board::{Board, BoardAction, BoardBackend, BoardData, SessionRow};
pub use run::run_board;
