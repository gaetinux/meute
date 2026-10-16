//! Thin client for a dedicated tmux server.
#![warn(missing_docs)]
#![deny(clippy::print_stdout, clippy::print_stderr)]

mod client;
mod conf;
mod error;
mod layout;
mod pane;
mod version;

pub use client::Tmux;
pub use conf::{Keys, LayoutSpec, render_config};
pub use error::TmuxError;
pub use layout::{
    BG_SESSION, ID_OPTION, Layout, MAIN_SESSION, MAIN_WINDOW, ROLE_BOARD, ROLE_OPTION,
    ROLE_WELCOME, STATUS_OPTION, ensure_layout, find_layout, is_narrow,
};
pub use pane::{PaneId, PaneInfo, Spawn, parse_pane_line};
pub use version::{MIN_VERSION, TmuxVersion, parse_version};
