//! Task status and priority.

use crate::{CoreError, Result};
use serde::{Deserialize, Serialize};

/// Status of a task without its payload (the blocked reason).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum StatusKind {
    /// Not started.
    Todo,
    /// Being worked on.
    InProgress,
    /// Waiting on something.
    Blocked,
    /// Waiting for a review.
    Review,
    /// Finished.
    Done,
}

impl StatusKind {
    /// Stable identifier (same as [`TaskStatus::id`]).
    #[must_use]
    pub fn id(self) -> &'static str {
        match self {
            Self::Todo => "todo",
            Self::InProgress => "in_progress",
            Self::Blocked => "blocked",
            Self::Review => "review",
            Self::Done => "done",
        }
    }

    /// Parses a status identifier.
    ///
    /// # Errors
    /// [`CoreError::Invalid`] on an unknown identifier.
    pub fn from_id(id: &str) -> Result<Self> {
        match id {
            "todo" => Ok(Self::Todo),
            "in_progress" => Ok(Self::InProgress),
            "blocked" => Ok(Self::Blocked),
            "review" => Ok(Self::Review),
            "done" => Ok(Self::Done),
            other => Err(CoreError::Invalid(format!("statut inconnu : {other}"))),
        }
    }
}

/// Lifecycle state of a task.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TaskStatus {
    /// Not started.
    Todo,
    /// Being worked on.
    InProgress,
    /// Waiting on something.
    Blocked {
        /// Why the task is blocked (never empty).
        reason: String,
    },
    /// Waiting for a review.
    Review,
    /// Finished.
    Done,
}

impl TaskStatus {
    /// The status without its payload.
    #[must_use]
    pub fn kind(&self) -> StatusKind {
        match self {
            Self::Todo => StatusKind::Todo,
            Self::InProgress => StatusKind::InProgress,
            Self::Blocked { .. } => StatusKind::Blocked,
            Self::Review => StatusKind::Review,
            Self::Done => StatusKind::Done,
        }
    }

    /// Stable identifier (storage and JSON).
    #[must_use]
    pub fn id(&self) -> &'static str {
        self.kind().id()
    }

    /// French label shown to the user.
    #[must_use]
    pub fn label(&self) -> &'static str {
        match self {
            Self::Todo => "à faire",
            Self::InProgress => "en cours",
            Self::Blocked { .. } => "bloquée",
            Self::Review => "à relire",
            Self::Done => "faite",
        }
    }

    /// Single-character symbol (spec § 9.5).
    #[must_use]
    pub fn symbol(&self) -> char {
        match self {
            Self::Todo => '·',
            Self::InProgress => '»',
            Self::Blocked { .. } => '✕',
            Self::Review => '◎',
            Self::Done => '✓',
        }
    }

    /// True for every status except `Done`.
    #[must_use]
    pub fn is_open(&self) -> bool {
        match self {
            Self::Todo | Self::InProgress | Self::Blocked { .. } | Self::Review => true,
            Self::Done => false,
        }
    }

    /// Parses a status identifier; `blocked` requires a non-blank reason.
    ///
    /// # Errors
    /// [`CoreError::Invalid`] on an unknown identifier or a missing reason.
    pub fn from_id(id: &str, reason: Option<&str>) -> Result<Self> {
        match id {
            "todo" => Ok(Self::Todo),
            "in_progress" => Ok(Self::InProgress),
            "blocked" => match reason.map(str::trim) {
                Some(r) if !r.is_empty() => Ok(Self::Blocked {
                    reason: r.to_owned(),
                }),
                Some(_) | None => Err(CoreError::Invalid(
                    "une tâche bloquée requiert une raison non vide".into(),
                )),
            },
            "review" => Ok(Self::Review),
            "done" => Ok(Self::Done),
            other => Err(CoreError::Invalid(format!("statut inconnu : {other}"))),
        }
    }
}

/// Task priority; sorts most urgent first.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Priority {
    /// Most urgent.
    Urgent,
    /// High.
    High,
    /// Default.
    Normal,
    /// Least urgent.
    Low,
}

impl Priority {
    /// Stable identifier (storage and JSON).
    #[must_use]
    pub fn id(&self) -> &'static str {
        match self {
            Self::Urgent => "urgent",
            Self::High => "high",
            Self::Normal => "normal",
            Self::Low => "low",
        }
    }

    /// Compact marker shown in lists (empty for normal and low).
    #[must_use]
    pub fn marker(&self) -> &'static str {
        match self {
            Self::Urgent => "!!",
            Self::High => "!",
            Self::Normal | Self::Low => "",
        }
    }

    /// Parses a priority identifier.
    ///
    /// # Errors
    /// [`CoreError::Invalid`] on an unknown identifier.
    pub fn from_id(id: &str) -> Result<Self> {
        match id {
            "urgent" => Ok(Self::Urgent),
            "high" => Ok(Self::High),
            "normal" => Ok(Self::Normal),
            "low" => Ok(Self::Low),
            other => Err(CoreError::Invalid(format!("priorité inconnue : {other}"))),
        }
    }
}
