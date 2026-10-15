//! Pure text rendering of tasks.
use jiff::Zoned;
use meute_core::quick_add::QuickAdd;
use meute_core::task::{Due, Note, Priority, Task, TaskStatus};
use meute_core::views::{format_due, is_overdue};

/// Assembles `symbol [marker] title [@project] [· tail]`.
fn compose(
    symbol: char,
    marker: &str,
    title: &str,
    project: Option<&str>,
    tail: Option<String>,
) -> String {
    let mut line = String::from(symbol);
    if !marker.is_empty() {
        line.push(' ');
        line.push_str(marker);
    }
    line.push(' ');
    line.push_str(title);
    if let Some(name) = project {
        line.push_str(" @");
        line.push_str(name);
    }
    if let Some(tail) = tail {
        line.push_str(" · ");
        line.push_str(&tail);
    }
    line
}

/// One-line summary of a task (spec § 9.5).
pub fn task_line(task: &Task, now: &Zoned) -> String {
    let tail = match &task.status {
        TaskStatus::Blocked { reason } => Some(format!("bloquée : {reason}")),
        TaskStatus::Review => Some("à relire".to_owned()),
        TaskStatus::Todo | TaskStatus::InProgress | TaskStatus::Done => task.due.map(|due| {
            let text = format_due(&due, now);
            if is_overdue(task, now) {
                format!("{text} (en retard)")
            } else {
                text
            }
        }),
    };
    let body = compose(
        task.status.symbol(),
        task.priority.marker(),
        &task.title,
        task.project.as_ref().map(|p| p.name.as_str()),
        tail,
    );
    format!("{} {body}", task.id)
}

/// Preview of a parsed quick-add input (`--dry-run`).
pub fn preview_line(parsed: &QuickAdd, now: &Zoned) -> String {
    let status = TaskStatus::Todo;
    compose(
        status.symbol(),
        parsed.priority.marker(),
        &parsed.title,
        parsed.project.as_deref(),
        parsed.due.map(|due| format_due(&due, now)),
    )
}

fn priority_label(priority: &Priority) -> &'static str {
    match priority {
        Priority::Urgent => "urgente",
        Priority::High => "haute",
        Priority::Normal => "normale",
        Priority::Low => "basse",
    }
}

fn stamp(ts: jiff::Timestamp, now: &Zoned) -> String {
    ts.to_zoned(now.time_zone().clone())
        .strftime("%Y-%m-%d %H:%M")
        .to_string()
}

/// Multi-line detail of a task, followed by its notes.
pub fn task_detail(task: &Task, notes: &[Note], now: &Zoned) -> String {
    let mut status = task.status.label().to_owned();
    if let TaskStatus::Blocked { reason } = &task.status {
        status.push_str(&format!(" ({reason})"));
    }
    let due = task
        .due
        .as_ref()
        .map_or_else(|| "—".to_owned(), |d: &Due| format_due(d, now));
    let project = task.project.as_ref().map_or("—", |p| p.name.as_str());
    let mut out = format!(
        "{} {}\nStatut : {status}\nPriorité : {}\nÉchéance : {due}\nProjet : {project}\nVersion : {}\nCréée : {}\nModifiée : {}\n",
        task.id,
        task.title,
        priority_label(&task.priority),
        task.version,
        stamp(task.created_at, now),
        stamp(task.updated_at, now),
    );
    if let Some(done) = task.completed_at {
        out.push_str(&format!("Terminée : {}\n", stamp(done, now)));
    }
    if !task.description.is_empty() {
        out.push_str(&format!("Description : {}\n", task.description));
    }
    if !notes.is_empty() {
        out.push_str("Notes :\n");
        for note in notes {
            out.push_str(&format!(
                "[{}] {} : {}\n",
                stamp(note.created_at, now),
                note.author.id(),
                note.body
            ));
        }
    }
    out
}
