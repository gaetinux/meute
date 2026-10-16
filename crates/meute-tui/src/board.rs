//! Dashboard state and key handling.

use std::path::PathBuf;

use meute_core::repo::{Repo, RepoId};
use meute_core::session::{Session, SessionId};
use ratatui::crossterm::event::{KeyCode, KeyEvent, KeyEventKind};

/// A session as shown on the dashboard.
#[derive(Debug, Clone, PartialEq)]
pub struct SessionRow {
    /// The stored session.
    pub session: Session,
    /// Whether its tmux pane still exists.
    pub has_pane: bool,
    /// Whether it is currently shown in the main area.
    pub displayed: bool,
}

/// Everything the dashboard displays.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct BoardData {
    /// All known sessions.
    pub sessions: Vec<SessionRow>,
    /// Discovered repositories.
    pub repos: Vec<Repo>,
    /// Identifiers of panes that belong to no session.
    pub orphans: Vec<String>,
    /// Home directory, replaced by `~` in displayed paths.
    pub home: Option<PathBuf>,
}

/// An action requested by the user.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum BoardAction {
    /// Show the session in the main area.
    Show(SessionId),
    /// Start a Bash session in a directory.
    LaunchBash {
        /// Working directory.
        cwd: PathBuf,
        /// Repository the directory belongs to, if any.
        repo_id: Option<RepoId>,
    },
    /// Stop the session.
    Stop(SessionId),
}

/// Source of data and executor of actions for [`crate::run_board`].
pub trait BoardBackend {
    /// New data, or `None` when nothing changed.
    ///
    /// # Errors
    /// A message to display in the footer.
    fn load(&mut self) -> Result<Option<BoardData>, String>;

    /// Carry out an action.
    ///
    /// # Errors
    /// A message to display in the footer.
    fn perform(&mut self, action: BoardAction) -> Result<(), String>;
}

/// The dashboard state.
#[derive(Debug)]
pub struct Board {
    pub(crate) data: BoardData,
    pub(crate) selected: usize,
    pub(crate) confirming: Option<SessionId>,
    pub(crate) error: Option<String>,
}

impl Board {
    /// A board showing `data`, with the first row selected.
    #[must_use]
    pub fn new(data: BoardData) -> Board {
        Board {
            data,
            selected: 0,
            confirming: None,
            error: None,
        }
    }

    /// Replace the data, keeping the selected session or repository selected when it still exists.
    pub fn set_data(&mut self, data: BoardData) {
        let previous = self.selected_row().map(|row| match row {
            Row::Session(r) => (Some(r.session.id), None),
            Row::Repo(r) => (None, Some(r.id)),
        });
        self.data = data;
        if let Some((session, repo)) = previous {
            let found = (0..self.row_count()).find(|&i| match self.row_at(i) {
                Some(Row::Session(r)) => Some(r.session.id) == session,
                Some(Row::Repo(r)) => Some(r.id) == repo,
                None => false,
            });
            if let Some(index) = found {
                self.selected = index;
            }
        }
        self.selected = self.selected.min(self.row_count().saturating_sub(1));
        let still_there = self
            .confirming
            .is_some_and(|id| self.visible_sessions().iter().any(|r| r.session.id == id));
        if !still_there {
            self.confirming = None;
        }
    }

    /// Show an error in the footer until the next key.
    pub fn set_error(&mut self, message: String) {
        self.error = Some(message);
    }

    /// Sessions to list: live ones first, then ended ones whose pane still exists.
    pub(crate) fn visible_sessions(&self) -> Vec<&SessionRow> {
        let live = self
            .data
            .sessions
            .iter()
            .filter(|r| r.session.state.is_live());
        let ended = self
            .data
            .sessions
            .iter()
            .filter(|r| !r.session.state.is_live() && r.has_pane);
        live.chain(ended).collect()
    }

    fn row_count(&self) -> usize {
        self.visible_sessions().len() + self.data.repos.len()
    }

    fn row_at(&self, index: usize) -> Option<Row<'_>> {
        let sessions = self.visible_sessions();
        match sessions.get(index) {
            Some(row) => Some(Row::Session(row)),
            None => self.data.repos.get(index - sessions.len()).map(Row::Repo),
        }
    }

    fn selected_row(&self) -> Option<Row<'_>> {
        self.row_at(self.selected)
    }

    /// Handle a key press.
    pub fn on_key(&mut self, key: KeyEvent) -> Option<BoardAction> {
        if key.kind != KeyEventKind::Press {
            return None;
        }
        self.error = None;
        if let Some(id) = self.confirming.take() {
            return (key.code == KeyCode::Char('o')).then_some(BoardAction::Stop(id));
        }
        let code = key.code;
        if matches!(code, KeyCode::Up | KeyCode::Char('k')) {
            self.selected = self.selected.saturating_sub(1);
            return None;
        }
        if matches!(code, KeyCode::Down | KeyCode::Char('j')) {
            self.selected = (self.selected + 1).min(self.row_count().saturating_sub(1));
            return None;
        }
        let row = self.selected_row()?;
        if code == KeyCode::Char('x') {
            if let Row::Session(r) = row {
                self.confirming = Some(r.session.id);
            }
            return None;
        }
        let enter = code == KeyCode::Enter;
        let new = code == KeyCode::Char('n');
        match row {
            Row::Session(r) if enter => Some(BoardAction::Show(r.session.id)),
            Row::Session(r) if new => Some(BoardAction::LaunchBash {
                cwd: r.session.cwd.clone(),
                repo_id: r.session.repo_id,
            }),
            Row::Repo(r) if enter || new => Some(launch_in_repo(r)),
            Row::Session(_) | Row::Repo(_) => None,
        }
    }
}

fn launch_in_repo(repo: &Repo) -> BoardAction {
    BoardAction::LaunchBash {
        cwd: repo.path.clone(),
        repo_id: Some(repo.id),
    }
}

/// A selectable row.
enum Row<'a> {
    Session(&'a SessionRow),
    Repo(&'a Repo),
}

#[cfg(test)]
mod tests;
