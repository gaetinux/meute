//! Task records and their inputs.

use super::{Priority, TaskStatus};
use crate::actor::{Author, Channel};
use crate::project::ProjectId;
use jiff::Timestamp;
use serde::ser::SerializeStruct;
use serde::{Deserialize, Serialize, Serializer};
use std::fmt;

/// Identifier of a task, displayed as `#N`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct TaskId(pub i64);

impl fmt::Display for TaskId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "#{}", self.0)
    }
}

/// Deadline of a task: a day, or an exact instant.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", content = "value", rename_all = "snake_case")]
pub enum Due {
    /// A calendar day without time.
    Date(jiff::civil::Date),
    /// An exact instant.
    At(Timestamp),
}

/// Lightweight reference to a task's project.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProjectRef {
    /// Project identifier.
    pub id: ProjectId,
    /// Project name.
    pub name: String,
}

/// A task as stored.
///
/// Serialization is hand-written (flat status, tagged due); there is
/// deliberately no `Deserialize`, so the two shapes cannot drift apart.
#[derive(Debug, Clone, PartialEq)]
pub struct Task {
    /// Identifier.
    pub id: TaskId,
    /// Short title.
    pub title: String,
    /// Longer description.
    pub description: String,
    /// Current status.
    pub status: TaskStatus,
    /// Priority.
    pub priority: Priority,
    /// Optional deadline.
    pub due: Option<Due>,
    /// Optional project.
    pub project: Option<ProjectRef>,
    /// Optional linked repository id.
    pub repo_id: Option<i64>,
    /// Optimistic-concurrency version.
    pub version: u32,
    /// Creation instant.
    pub created_at: Timestamp,
    /// Last update instant.
    pub updated_at: Timestamp,
    /// Completion instant, when done.
    pub completed_at: Option<Timestamp>,
}

impl Serialize for Task {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let blocked_reason = match &self.status {
            TaskStatus::Blocked { reason } => Some(reason.as_str()),
            TaskStatus::Todo | TaskStatus::InProgress | TaskStatus::Review | TaskStatus::Done => {
                None
            }
        };
        let mut s = serializer.serialize_struct("Task", 13)?;
        s.serialize_field("id", &self.id)?;
        s.serialize_field("title", &self.title)?;
        s.serialize_field("description", &self.description)?;
        s.serialize_field("status", self.status.id())?;
        s.serialize_field("blocked_reason", &blocked_reason)?;
        s.serialize_field("priority", &self.priority)?;
        s.serialize_field("due", &self.due)?;
        s.serialize_field("project", &self.project)?;
        s.serialize_field("repo_id", &self.repo_id)?;
        s.serialize_field("version", &self.version)?;
        s.serialize_field("created_at", &self.created_at)?;
        s.serialize_field("updated_at", &self.updated_at)?;
        s.serialize_field("completed_at", &self.completed_at)?;
        s.end()
    }
}

/// Input for creating a task.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct NewTask {
    /// Title (non-empty).
    pub title: String,
    /// Description.
    pub description: String,
    /// Priority.
    pub priority: Priority,
    /// Optional deadline.
    pub due: Option<Due>,
    /// Optional project.
    pub project_id: Option<ProjectId>,
}

/// Partial update; `None` leaves a field unchanged.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct TaskPatch {
    /// New title.
    pub title: Option<String>,
    /// New description.
    pub description: Option<String>,
    /// New status.
    pub status: Option<TaskStatus>,
    /// New priority.
    pub priority: Option<Priority>,
    /// New deadline (`Some(None)` clears it).
    pub due: Option<Option<Due>>,
    /// New project (`Some(None)` clears it).
    pub project_id: Option<Option<ProjectId>>,
}

/// A note attached to a task.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Note {
    /// Identifier.
    pub id: i64,
    /// Owning task.
    pub task_id: TaskId,
    /// Note text.
    pub body: String,
    /// Who wrote it.
    pub author: Author,
    /// Through which interface.
    pub channel: Channel,
    /// Claude session id, when relevant.
    pub session_id: Option<String>,
    /// Creation instant.
    pub created_at: Timestamp,
}

/// One entry of a task's change history.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct TaskEvent {
    /// Task concerned.
    pub task_id: TaskId,
    /// Field that changed.
    pub field: String,
    /// Previous value, if any.
    pub old_value: Option<String>,
    /// New value, if any.
    pub new_value: Option<String>,
    /// Who made the change.
    pub author: Author,
    /// Through which interface.
    pub channel: Channel,
    /// Claude session id, when relevant.
    pub session_id: Option<String>,
    /// When it happened.
    pub created_at: Timestamp,
}
