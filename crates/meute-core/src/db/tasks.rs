//! Task repository: creation and reading.

use std::str::FromStr;

use jiff::Timestamp;
use rusqlite::types::{Type, Value};
use rusqlite::{Row, params, params_from_iter};

use super::Db;
use crate::actor::{Actor, Author, Channel};
use crate::error::{CoreError, Result};
use crate::project::ProjectId;
use crate::task::{Due, NewTask, Priority, ProjectRef, Task, TaskEvent, TaskId, TaskStatus};

/// Which projects a task listing covers.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum ProjectFilter {
    /// Every task.
    #[default]
    Any,
    /// Tasks of one project.
    Project(ProjectId),
    /// Floating tasks, without a project.
    Floating,
}

/// Filter for [`Db::list_tasks`].
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct TaskFilter {
    /// Include tasks that are done.
    pub include_done: bool,
    /// Project restriction.
    pub project: ProjectFilter,
    /// Restrict to one status identifier (see [`TaskStatus::id`]).
    pub status: Option<&'static str>,
}

const TASK_SELECT: &str = "SELECT t.id, t.title, t.description, t.status, t.blocked_reason, \
     t.priority, t.due_date, t.due_at, t.project_id, p.name, t.repo_id, t.version, \
     t.created_at, t.updated_at, t.completed_at \
     FROM tasks t LEFT JOIN projects p ON p.id = t.project_id";

fn conversion<E>(idx: usize, err: E) -> rusqlite::Error
where
    E: std::error::Error + Send + Sync + 'static,
{
    rusqlite::Error::FromSqlConversionFailure(idx, Type::Text, Box::new(err))
}

fn parse_at<T>(idx: usize, text: &str) -> rusqlite::Result<T>
where
    T: FromStr,
    T::Err: std::error::Error + Send + Sync + 'static,
{
    text.parse().map_err(|e| conversion(idx, e))
}

fn parse_opt<T>(idx: usize, text: Option<String>) -> rusqlite::Result<Option<T>>
where
    T: FromStr,
    T::Err: std::error::Error + Send + Sync + 'static,
{
    text.map(|s| parse_at(idx, &s)).transpose()
}

fn row_to_task(row: &Row) -> rusqlite::Result<Task> {
    let status_id: String = row.get(3)?;
    let reason: Option<String> = row.get(4)?;
    let priority: String = row.get(5)?;
    let due_date: Option<jiff::civil::Date> = parse_opt(6, row.get(6)?)?;
    let due_at: Option<Timestamp> = parse_opt(7, row.get(7)?)?;
    let due = match (due_date, due_at) {
        (Some(d), _) => Some(Due::Date(d)),
        (None, Some(at)) => Some(Due::At(at)),
        (None, None) => None,
    };
    let project_id: Option<i64> = row.get(8)?;
    let project_name: Option<String> = row.get(9)?;
    let project = match (project_id, project_name) {
        (Some(id), Some(name)) => Some(ProjectRef {
            id: ProjectId(id),
            name,
        }),
        (Some(_), None) | (None, _) => None,
    };
    let created_at: String = row.get(12)?;
    let updated_at: String = row.get(13)?;
    Ok(Task {
        id: TaskId(row.get(0)?),
        title: row.get(1)?,
        description: row.get(2)?,
        status: TaskStatus::from_id(&status_id, reason.as_deref()).map_err(|e| conversion(3, e))?,
        priority: Priority::from_id(&priority).map_err(|e| conversion(5, e))?,
        due,
        project,
        repo_id: row.get(10)?,
        version: row.get(11)?,
        created_at: parse_at(12, &created_at)?,
        updated_at: parse_at(13, &updated_at)?,
        completed_at: parse_opt(14, row.get(14)?)?,
    })
}

fn row_to_event(row: &Row) -> rusqlite::Result<TaskEvent> {
    let author: String = row.get(4)?;
    let channel: String = row.get(5)?;
    let created_at: String = row.get(7)?;
    Ok(TaskEvent {
        task_id: TaskId(row.get(0)?),
        field: row.get(1)?,
        old_value: row.get(2)?,
        new_value: row.get(3)?,
        author: Author::from_id(&author).map_err(|e| conversion(4, e))?,
        channel: Channel::from_id(&channel).map_err(|e| conversion(5, e))?,
        session_id: row.get(6)?,
        created_at: parse_at(7, &created_at)?,
    })
}

impl Db {
    /// Create a task (status `Todo`, version 1) and record a `created` event.
    ///
    /// # Errors
    /// [`CoreError::Invalid`] on a blank title; [`CoreError::Db`] on an unknown project.
    pub fn create_task(&mut self, new: NewTask, actor: &Actor) -> Result<Task> {
        let title = new.title.trim();
        if title.is_empty() {
            return Err(CoreError::Invalid("le titre ne peut pas être vide".into()));
        }
        let now = self.now().to_string();
        let (due_date, due_at) = match new.due {
            Some(Due::Date(d)) => (Some(d.to_string()), None),
            Some(Due::At(at)) => (None, Some(at.to_string())),
            None => (None, None),
        };
        let tx = self.conn.transaction()?;
        tx.execute(
            "INSERT INTO tasks (title, description, status, priority, due_date, due_at, \
             project_id, version, created_at, updated_at) \
             VALUES (?1, ?2, 'todo', ?3, ?4, ?5, ?6, 1, ?7, ?7)",
            params![
                title,
                new.description,
                new.priority.id(),
                due_date,
                due_at,
                new.project_id.map(|p| p.0),
                now
            ],
        )?;
        let id = tx.last_insert_rowid();
        tx.execute(
            "INSERT INTO task_events (task_id, field, old_value, new_value, author, channel, \
             session_id, created_at) VALUES (?1, 'created', NULL, ?2, ?3, ?4, ?5, ?6)",
            params![
                id,
                title,
                actor.author.id(),
                actor.channel.id(),
                actor.session_id,
                now
            ],
        )?;
        tx.commit()?;
        self.get_task(TaskId(id))
    }

    /// Fetch one task.
    ///
    /// # Errors
    /// [`CoreError::NotFound`] when the task does not exist.
    pub fn get_task(&self, id: TaskId) -> Result<Task> {
        match self.conn.query_row(
            &format!("{TASK_SELECT} WHERE t.id = ?1"),
            [id.0],
            row_to_task,
        ) {
            Ok(task) => Ok(task),
            Err(rusqlite::Error::QueryReturnedNoRows) => Err(CoreError::NotFound {
                entity: "tâche",
                id: id.to_string(),
            }),
            Err(other) => Err(other.into()),
        }
    }

    /// List tasks matching `filter`, by increasing id.
    pub fn list_tasks(&self, filter: &TaskFilter) -> Result<Vec<Task>> {
        let mut sql = format!("{TASK_SELECT} WHERE 1 = 1");
        let mut args: Vec<Value> = Vec::new();
        if !filter.include_done {
            sql.push_str(" AND t.status <> 'done'");
        }
        match filter.project {
            ProjectFilter::Any => {}
            ProjectFilter::Project(p) => {
                sql.push_str(" AND t.project_id = ?");
                args.push(Value::Integer(p.0));
            }
            ProjectFilter::Floating => sql.push_str(" AND t.project_id IS NULL"),
        }
        if let Some(status) = filter.status {
            sql.push_str(" AND t.status = ?");
            args.push(Value::Text(status.to_owned()));
        }
        sql.push_str(" ORDER BY t.id");
        let mut stmt = self.conn.prepare(&sql)?;
        let rows = stmt.query_map(params_from_iter(args), row_to_task)?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }

    /// Change history of a task, oldest first.
    pub fn history(&self, id: TaskId) -> Result<Vec<TaskEvent>> {
        let mut stmt = self.conn.prepare(
            "SELECT task_id, field, old_value, new_value, author, channel, session_id, \
             created_at FROM task_events WHERE task_id = ?1 ORDER BY id",
        )?;
        let rows = stmt.query_map([id.0], row_to_event)?;
        Ok(rows.collect::<rusqlite::Result<Vec<_>>>()?)
    }
}
