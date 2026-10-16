//! Reconciliation of stored sessions with the tmux panes that carry `@meute_id` (spec § 5.4).

use std::collections::{HashMap, HashSet};

use super::{AgentKind, Session, SessionId, SessionState};

/// A pane carrying `@meute_id`, as seen by tmux.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PaneObservation {
    /// Value of the pane's `@meute_id` option.
    pub meute_id: String,
    /// Whether the pane's process ended (`remain-on-exit`).
    pub dead: bool,
    /// Exit status of a dead pane, when tmux reports one.
    pub exit_code: Option<i32>,
}

/// Outcome of [`reconcile`].
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Reconciliation {
    /// State changes to store.
    pub updates: Vec<(SessionId, SessionState)>,
    /// Pane identifiers that match no stored session.
    pub orphans: Vec<String>,
}

/// Compare stored sessions with observed panes. Pure: no I/O.
///
/// Only live sessions are updated; ended sessions are never resurrected.
#[must_use]
pub fn reconcile(sessions: &[Session], panes: &[PaneObservation]) -> Reconciliation {
    let by_id: HashMap<&str, &PaneObservation> =
        panes.iter().map(|p| (p.meute_id.as_str(), p)).collect();
    let updates = sessions
        .iter()
        .filter(|s| s.state.is_live())
        .filter_map(|s| {
            let next = next_state(s, by_id.get(s.id.to_string().as_str()).copied())?;
            Some((s.id, next))
        })
        .collect();
    let known: HashSet<String> = sessions.iter().map(|s| s.id.to_string()).collect();
    let mut seen = HashSet::new();
    let orphans = panes
        .iter()
        .filter(|p| !known.contains(&p.meute_id) && seen.insert(p.meute_id.as_str()))
        .map(|p| p.meute_id.clone())
        .collect();
    Reconciliation { updates, orphans }
}

/// New state of a live session given its pane, or `None` when nothing changes.
fn next_state(session: &Session, pane: Option<&PaneObservation>) -> Option<SessionState> {
    let Some(pane) = pane else {
        return Some(SessionState::Unreachable);
    };
    if pane.dead {
        return Some(SessionState::Exited {
            code: pane.exit_code,
        });
    }
    match session.agent {
        AgentKind::Bash if session.state != SessionState::Running => Some(SessionState::Running),
        AgentKind::Bash | AgentKind::Claude => None,
    }
}

#[cfg(test)]
mod tests;
