//! Session domain types.

use std::fmt;
use std::path::PathBuf;

use jiff::Timestamp;
use serde::{Deserialize, Serialize};

use crate::error::{CoreError, Result};
use crate::project::ProjectId;
use crate::repo::RepoId;
use crate::task::TaskId;

/// Identifier of a session (a v4 UUID, also stored in the tmux `@meute_id` option).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct SessionId(pub uuid::Uuid);

impl SessionId {
    /// A fresh random identifier.
    #[must_use]
    pub fn new() -> SessionId {
        SessionId(uuid::Uuid::new_v4())
    }

    /// Parse a full hyphenated identifier.
    ///
    /// # Errors
    /// [`CoreError::Invalid`] when `s` is not a UUID.
    pub fn parse(s: &str) -> Result<SessionId> {
        uuid::Uuid::parse_str(s)
            .map(SessionId)
            .map_err(|_| CoreError::Invalid(format!("identifiant de session invalide : {s}")))
    }

    /// The first 8 characters, for display.
    #[must_use]
    pub fn short(&self) -> String {
        self.to_string().chars().take(8).collect()
    }
}

impl Default for SessionId {
    fn default() -> Self {
        SessionId::new()
    }
}

impl fmt::Display for SessionId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0.hyphenated())
    }
}

/// Kind of program running in a session.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AgentKind {
    /// A Claude Code session.
    Claude,
    /// A plain Bash shell.
    Bash,
}

impl AgentKind {
    /// Stable identifier used in storage and JSON.
    #[must_use]
    pub fn id(&self) -> &'static str {
        match self {
            AgentKind::Claude => "claude",
            AgentKind::Bash => "bash",
        }
    }

    /// Inverse of [`AgentKind::id`].
    ///
    /// # Errors
    /// [`CoreError::Invalid`] on an unknown identifier.
    pub fn from_id(id: &str) -> Result<AgentKind> {
        match id {
            "claude" => Ok(AgentKind::Claude),
            "bash" => Ok(AgentKind::Bash),
            other => Err(CoreError::Invalid(format!("agent inconnu : {other}"))),
        }
    }
}

/// State of a session (spec § 6.1).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum SessionState {
    /// The agent is working.
    Running,
    /// A sub-agent is working.
    SubagentRunning,
    /// The context is being compacted.
    Compacting,
    /// A permission is awaited.
    PermissionRequested,
    /// The agent waits for the user's answer.
    WaitingInput,
    /// Nothing is happening.
    Idle,
    /// The process ended.
    Exited {
        /// Exit code, when known.
        code: Option<i32>,
    },
    /// The tmux pane is gone.
    Unreachable,
    /// Presumed stuck (assumed state).
    MaybeStuck,
    /// State could not be determined (assumed state).
    Unknown,
}

impl SessionState {
    /// Stable identifier used in storage and JSON.
    #[must_use]
    pub fn id(&self) -> &'static str {
        match self {
            SessionState::Running => "running",
            SessionState::SubagentRunning => "subagent_running",
            SessionState::Compacting => "compacting",
            SessionState::PermissionRequested => "permission_requested",
            SessionState::WaitingInput => "waiting_input",
            SessionState::Idle => "idle",
            SessionState::Exited { .. } => "exited",
            SessionState::Unreachable => "unreachable",
            SessionState::MaybeStuck => "maybe_stuck",
            SessionState::Unknown => "unknown",
        }
    }

    /// Rebuild a state from its identifier and exit code (the code only counts for `exited`).
    ///
    /// # Errors
    /// [`CoreError::Invalid`] on an unknown identifier.
    pub fn from_parts(id: &str, code: Option<i32>) -> Result<SessionState> {
        match id {
            "running" => Ok(SessionState::Running),
            "subagent_running" => Ok(SessionState::SubagentRunning),
            "compacting" => Ok(SessionState::Compacting),
            "permission_requested" => Ok(SessionState::PermissionRequested),
            "waiting_input" => Ok(SessionState::WaitingInput),
            "idle" => Ok(SessionState::Idle),
            "exited" => Ok(SessionState::Exited { code }),
            "unreachable" => Ok(SessionState::Unreachable),
            "maybe_stuck" => Ok(SessionState::MaybeStuck),
            "unknown" => Ok(SessionState::Unknown),
            other => Err(CoreError::Invalid(format!(
                "état de session inconnu : {other}"
            ))),
        }
    }

    /// Whether the session still runs (false for `Exited` and `Unreachable` only).
    #[must_use]
    pub fn is_live(&self) -> bool {
        match self {
            SessionState::Exited { .. } | SessionState::Unreachable => false,
            SessionState::Running
            | SessionState::SubagentRunning
            | SessionState::Compacting
            | SessionState::PermissionRequested
            | SessionState::WaitingInput
            | SessionState::Idle
            | SessionState::MaybeStuck
            | SessionState::Unknown => true,
        }
    }

    /// French label; assumed states carry a `?`.
    #[must_use]
    pub fn label(&self) -> String {
        match self {
            SessionState::Running => "en cours".into(),
            SessionState::SubagentRunning => "sous-agent".into(),
            SessionState::Compacting => "compactage".into(),
            SessionState::PermissionRequested => "permission".into(),
            SessionState::WaitingInput => "attend ta réponse".into(),
            SessionState::Idle => "inactive".into(),
            SessionState::Exited { code: Some(code) } => format!("terminée ({code})"),
            SessionState::Exited { code: None } => "terminée".into(),
            SessionState::Unreachable => "injoignable".into(),
            SessionState::MaybeStuck => "bloquée ?".into(),
            SessionState::Unknown => "inconnu ?".into(),
        }
    }
}

/// A stored session.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Session {
    /// Identifier.
    pub id: SessionId,
    /// Kind of program.
    pub agent: AgentKind,
    /// Display title.
    pub title: String,
    /// Optional project.
    pub project_id: Option<ProjectId>,
    /// Optional repository.
    pub repo_id: Option<RepoId>,
    /// Optional task.
    pub task_id: Option<TaskId>,
    /// Working directory.
    pub cwd: PathBuf,
    /// Current state.
    pub state: SessionState,
    /// Last state change or activity.
    pub last_activity_at: Timestamp,
    /// Creation time.
    pub created_at: Timestamp,
    /// When the session left the live states.
    pub ended_at: Option<Timestamp>,
}

/// Input of [`crate::db::Db::create_session`].
#[derive(Debug, Clone)]
pub struct NewSession {
    /// Identifier chosen by the caller.
    pub id: SessionId,
    /// Kind of program.
    pub agent: AgentKind,
    /// Display title.
    pub title: String,
    /// Working directory.
    pub cwd: PathBuf,
    /// Optional project.
    pub project_id: Option<ProjectId>,
    /// Optional repository.
    pub repo_id: Option<RepoId>,
    /// Optional task.
    pub task_id: Option<TaskId>,
    /// Initial state.
    pub state: SessionState,
}

/// Filter for [`crate::db::Db::list_sessions`].
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct SessionFilter {
    /// Include sessions that are no longer live.
    pub include_ended: bool,
}
