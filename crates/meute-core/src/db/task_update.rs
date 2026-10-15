//! Versioned task updates, deletion and notes.

use rusqlite::{Connection, OptionalExtension, TransactionBehavior, params};

use super::Db;
use super::tasks::{fetch_task, unknown_project};
use super::time::to_db;
use crate::actor::Actor;
use crate::error::{CoreError, Result};
use crate::project::ProjectId;
use crate::task::{Due, Task, TaskId, TaskPatch, TaskStatus};

/// One changed field, ready to be logged as an event.
struct Change {
    field: &'static str,
    old: Option<String>,
    new: Option<String>,
}

fn due_text(due: Option<Due>) -> Option<String> {
    due.map(|d| match d {
        Due::Date(date) => date.to_string(),
        Due::At(at) => at.to_string(),
    })
}

fn insert_event(
    conn: &Connection,
    id: TaskId,
    change: &Change,
    actor: &Actor,
    now: &str,
) -> Result<()> {
    conn.execute(
        "INSERT INTO task_events (task_id, field, old_value, new_value, author, channel, \
         session_id, created_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
        params![
            id.0,
            change.field,
            change.old,
            change.new,
            actor.author.id(),
            actor.channel.id(),
            actor.session_id,
            now
        ],
    )?;
    Ok(())
}

fn project_name(conn: &Connection, id: i64) -> Result<Option<String>> {
    Ok(conn
        .query_row("SELECT name FROM projects WHERE id = ?1", [id], |r| {
            r.get(0)
        })
        .optional()?)
}

/// Patch values after validation and normalisation.
struct Resolved {
    title: String,
    description: String,
    status: TaskStatus,
    priority: crate::task::Priority,
    due: Option<Due>,
    project: Option<ProjectId>,
}

fn text_change(field: &'static str, old: &str, new: &str, out: &mut Vec<Change>) {
    if old != new {
        out.push(Change {
            field,
            old: Some(old.to_owned()),
            new: Some(new.to_owned()),
        });
    }
}

/// Validate `patch`, apply it to a copy of `cur`'s values and list real changes.
fn resolve(cur: &Task, patch: &TaskPatch) -> Result<(Resolved, Vec<Change>)> {
    let title = patch.title.as_deref().map_or(cur.title.as_str(), str::trim);
    if title.is_empty() {
        return Err(CoreError::Invalid("le titre ne peut pas être vide".into()));
    }
    let status = match &patch.status {
        Some(TaskStatus::Blocked { reason }) => {
            let reason = reason.trim();
            if reason.is_empty() {
                return Err(CoreError::Invalid(
                    "une tâche bloquée doit avoir une raison".into(),
                ));
            }
            TaskStatus::Blocked {
                reason: reason.to_owned(),
            }
        }
        Some(other) => other.clone(),
        None => cur.status.clone(),
    };
    let next = Resolved {
        title: title.to_owned(),
        description: patch
            .description
            .clone()
            .unwrap_or_else(|| cur.description.clone()),
        status,
        priority: patch.priority.unwrap_or(cur.priority),
        due: patch.due.unwrap_or(cur.due),
        project: patch
            .project_id
            .unwrap_or_else(|| cur.project.as_ref().map(|p| p.id)),
    };
    let mut changes = Vec::new();
    text_change("title", &cur.title, &next.title, &mut changes);
    text_change(
        "description",
        &cur.description,
        &next.description,
        &mut changes,
    );
    if next.status != cur.status {
        changes.push(Change {
            field: "status",
            old: Some(cur.status.id().to_owned()),
            new: Some(next.status.id().to_owned()),
        });
    }
    if next.priority != cur.priority {
        changes.push(Change {
            field: "priority",
            old: Some(cur.priority.id().to_owned()),
            new: Some(next.priority.id().to_owned()),
        });
    }
    if next.due != cur.due {
        changes.push(Change {
            field: "due",
            old: due_text(cur.due),
            new: due_text(next.due),
        });
    }
    Ok((next, changes))
}

impl Db {
    /// Update a task if its version is still `expected_version`.
    ///
    /// A patch that changes nothing returns the task untouched (no version
    /// bump, no event). Otherwise the version is bumped once and one event is
    /// logged per changed field.
    ///
    /// # Errors
    /// [`CoreError::Conflict`] when the version differs (nothing is written);
    /// [`CoreError::NotFound`] for an unknown task or project;
    /// [`CoreError::Invalid`] on a blank title or blank blocked reason.
    pub fn update_task(
        &mut self,
        id: TaskId,
        expected_version: u32,
        patch: TaskPatch,
        actor: &Actor,
    ) -> Result<Task> {
        let now = to_db(self.now());
        let tx = self
            .conn
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let cur = fetch_task(&tx, id)?;
        if cur.version != expected_version {
            return Err(CoreError::Conflict {
                current: Box::new(cur),
            });
        }
        let (next, mut changes) = resolve(&cur, &patch)?;
        let cur_project = cur.project.as_ref().map(|p| p.id);
        if next.project != cur_project {
            changes.push(Change {
                field: "project",
                old: cur.project.as_ref().map(|p| p.name.clone()),
                new: None,
            });
        }
        if changes.is_empty() {
            return Ok(cur);
        }
        let completed_at = match (&cur.status, &next.status) {
            (TaskStatus::Done, TaskStatus::Done) => cur.completed_at.map(to_db),
            (_, TaskStatus::Done) => Some(now.clone()),
            (_, _) => None,
        };
        let reason = match &next.status {
            TaskStatus::Blocked { reason } => Some(reason.as_str()),
            TaskStatus::Todo | TaskStatus::InProgress | TaskStatus::Review | TaskStatus::Done => {
                None
            }
        };
        let (due_date, due_at) = match next.due {
            Some(Due::Date(d)) => (Some(d.to_string()), None),
            Some(Due::At(at)) => (None, Some(to_db(at))),
            None => (None, None),
        };
        let rows = tx
            .execute(
                "UPDATE tasks SET title = ?1, description = ?2, status = ?3, \
                 blocked_reason = ?4, priority = ?5, due_date = ?6, due_at = ?7, \
                 project_id = ?8, completed_at = ?9, version = version + 1, updated_at = ?10 \
                 WHERE id = ?11 AND version = ?12",
                params![
                    next.title,
                    next.description,
                    next.status.id(),
                    reason,
                    next.priority.id(),
                    due_date,
                    due_at,
                    next.project.map(|p| p.0),
                    completed_at,
                    now,
                    id.0,
                    expected_version
                ],
            )
            .map_err(|e| unknown_project(e, next.project))?;
        if rows == 0 {
            return Err(CoreError::Conflict {
                current: Box::new(fetch_task(&tx, id)?),
            });
        }
        for change in &mut changes {
            if change.field == "project" {
                change.new = match next.project {
                    Some(p) => project_name(&tx, p.0)?,
                    None => None,
                };
            }
            insert_event(&tx, id, change, actor, &now)?;
        }
        tx.commit()?;
        self.get_task(id)
    }

    /// Delete a task (and its notes) if its version is `expected_version`.
    /// The history is kept, with a final `deleted` event.
    ///
    /// # Errors
    /// [`CoreError::Conflict`] on a version mismatch; [`CoreError::NotFound`]
    /// when the task does not exist.
    pub fn delete_task(&mut self, id: TaskId, expected_version: u32, actor: &Actor) -> Result<()> {
        let now = to_db(self.now());
        let tx = self
            .conn
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let cur = fetch_task(&tx, id)?;
        if cur.version != expected_version {
            return Err(CoreError::Conflict {
                current: Box::new(cur),
            });
        }
        let change = Change {
            field: "deleted",
            old: Some(cur.title.clone()),
            new: None,
        };
        insert_event(&tx, id, &change, actor, &now)?;
        let rows = tx.execute(
            "DELETE FROM tasks WHERE id = ?1 AND version = ?2",
            params![id.0, expected_version],
        )?;
        if rows == 0 {
            return Err(CoreError::Conflict {
                current: Box::new(fetch_task(&tx, id)?),
            });
        }
        tx.commit()?;
        Ok(())
    }
}
