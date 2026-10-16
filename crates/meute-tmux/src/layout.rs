//! The `meute:main` window: dashboard on the right, main area on the left.

use crate::{LayoutSpec, PaneId, PaneInfo, Tmux, TmuxError};

/// Session holding the window shown to the user.
pub const MAIN_SESSION: &str = "meute";
/// Window of [`MAIN_SESSION`] holding the dashboard and the main area.
pub const MAIN_WINDOW: &str = "main";
/// Session holding the panes that are not displayed.
pub const BG_SESSION: &str = "meute-bg";
/// Pane option holding the meute session UUID.
pub const ID_OPTION: &str = "@meute_id";
/// Pane option holding the role of a layout pane.
pub const ROLE_OPTION: &str = "@meute_role";
/// Role of the dashboard pane.
pub const ROLE_BOARD: &str = "board";
/// Role of the welcome pane.
pub const ROLE_WELCOME: &str = "welcome";
/// Global option shown on the right of the status bar.
pub const STATUS_OPTION: &str = "@meute_status";

/// Current state of the `meute:main` window.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Layout {
    /// Dashboard pane.
    pub board: PaneId,
    /// Pane of the main area, if any.
    pub main: Option<PaneId>,
    /// Window width in columns.
    pub width: u16,
    /// Whether a pane of the window is zoomed.
    pub zoomed: bool,
}

/// Whether a window of this width is too narrow for side-by-side panes.
pub fn is_narrow(width: u16, threshold: u16) -> bool {
    width < threshold
}

/// `=meute:main`, the exact target of the main window.
fn main_target() -> String {
    format!("={MAIN_SESSION}:{MAIN_WINDOW}")
}

/// Panes of `meute:main`, in tmux order.
fn window_panes(tmux: &Tmux) -> Result<Vec<PaneInfo>, TmuxError> {
    let mut panes = tmux.list_panes()?;
    panes.retain(|pane| pane.session == MAIN_SESSION && pane.window == MAIN_WINDOW);
    Ok(panes)
}

fn is_board(pane: &PaneInfo) -> bool {
    pane.role.as_deref() == Some(ROLE_BOARD)
}

fn live_board(panes: &[PaneInfo]) -> Option<PaneId> {
    panes
        .iter()
        .find(|pane| is_board(pane) && !pane.dead)
        .map(|pane| pane.id.clone())
}

fn main_pane(panes: &[PaneInfo]) -> Option<PaneId> {
    panes
        .iter()
        .find(|pane| !is_board(pane))
        .map(|pane| pane.id.clone())
}

/// Reads the width and zoom flag of `meute:main`.
fn window_geometry(tmux: &Tmux) -> Result<(u16, bool), TmuxError> {
    let format = "#{window_width}\t#{window_zoomed_flag}";
    let output = tmux.run(&["display-message", "-p", "-t", &main_target(), format])?;
    let bad = || TmuxError::Parse(format!("géométrie de fenêtre illisible : {output:?}"));
    let (width, zoomed) = output.split_once('\t').ok_or_else(bad)?;
    let width = width.parse().map_err(|_| bad())?;
    Ok((width, zoomed == "1"))
}

/// Reads the layout; `None` without a live dashboard in `meute:main`.
pub fn find_layout(tmux: &Tmux) -> Result<Option<Layout>, TmuxError> {
    let panes = window_panes(tmux)?;
    let Some(board) = live_board(&panes) else {
        return Ok(None);
    };
    let main = panes
        .iter()
        .find(|pane| pane.id != board && !is_board(pane))
        .map(|pane| pane.id.clone());
    let (width, zoomed) = window_geometry(tmux)?;
    Ok(Some(Layout {
        board,
        main,
        width,
        zoomed,
    }))
}

/// Runs a pane-creating command, then tags the new pane with `role`.
fn create_pane(
    tmux: &Tmux,
    args: &[&str],
    command: &[String],
    role: &str,
) -> Result<PaneId, TmuxError> {
    let mut full = args.to_vec();
    full.extend(["-P", "-F", "#{pane_id}", "--"]);
    full.extend(command.iter().map(String::as_str));
    let pane = PaneId(tmux.run(&full)?);
    tmux.set_pane_option(&pane, ROLE_OPTION, role)?;
    Ok(pane)
}

fn split_board(tmux: &Tmux, spec: &LayoutSpec, target: &PaneId) -> Result<PaneId, TmuxError> {
    let width = spec.board_width.to_string();
    let args = ["split-window", "-h", "-l", &width, "-t", &target.0];
    create_pane(tmux, &args, &spec.board_command, ROLE_BOARD)
}

fn split_welcome(tmux: &Tmux, spec: &LayoutSpec, board: &PaneId) -> Result<PaneId, TmuxError> {
    let args = ["split-window", "-h", "-b", "-t", &board.0];
    create_pane(tmux, &args, &spec.welcome_command, ROLE_WELCOME)
}

/// Creates the `meute` session with its welcome pane and dashboard.
fn create_session(tmux: &Tmux, spec: &LayoutSpec) -> Result<(), TmuxError> {
    let args = [
        "new-session",
        "-d",
        "-s",
        MAIN_SESSION,
        "-n",
        MAIN_WINDOW,
        "-x",
        "200",
        "-y",
        "50",
    ];
    let welcome = create_pane(tmux, &args, &spec.welcome_command, ROLE_WELCOME)?;
    let board = split_board(tmux, spec, &welcome)?;
    tmux.select_pane(&board)
}

/// Recreates whichever of the dashboard and main pane is missing.
fn repair(tmux: &Tmux, spec: &LayoutSpec) -> Result<(), TmuxError> {
    let panes = window_panes(tmux)?;
    let main = main_pane(&panes);
    let board = match (live_board(&panes), &main) {
        (Some(board), _) => board,
        (None, Some(main)) => split_board(tmux, spec, main)?,
        (None, None) => match panes.first() {
            Some(dead_board) => split_board(tmux, spec, &dead_board.id)?,
            None => {
                let target = format!("={MAIN_SESSION}:");
                let args = ["new-window", "-d", "-t", &target, "-n", MAIN_WINDOW];
                let welcome = create_pane(tmux, &args, &spec.welcome_command, ROLE_WELCOME)?;
                return split_board(tmux, spec, &welcome).map(|_| ());
            }
        },
    };
    if main.is_none() {
        split_welcome(tmux, spec, &board)?;
    }
    for pane in panes.iter().filter(|pane| is_board(pane) && pane.dead) {
        tmux.kill_pane(&pane.id)?;
    }
    Ok(())
}

/// Creates or repairs the layout, then applies the narrow mode.
pub fn ensure_layout(tmux: &Tmux, spec: &LayoutSpec) -> Result<Layout, TmuxError> {
    if tmux.has_session(MAIN_SESSION)? {
        repair(tmux, spec)?;
    } else {
        create_session(tmux, spec)?;
    }
    let layout = find_layout(tmux)?.ok_or_else(|| {
        TmuxError::Parse("tableau de bord introuvable dans meute:main".to_owned())
    })?;
    let board = &layout.board.0;
    let narrow = is_narrow(layout.width, spec.narrow_threshold);
    if narrow != layout.zoomed {
        tmux.run(&["resize-pane", "-Z", "-t", board])?;
    }
    if !narrow {
        let width = spec.board_width.to_string();
        tmux.run(&["resize-pane", "-t", board, "-x", &width])?;
    }
    find_layout(tmux)?
        .ok_or_else(|| TmuxError::Parse("tableau de bord introuvable dans meute:main".to_owned()))
}
