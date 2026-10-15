//! Boundary of the overdue test, added after a cargo-mutants run.

use jiff::{Timestamp, Zoned};
use meute_core::task::{Due, Priority, Task, TaskId, TaskStatus};
use meute_core::views::is_overdue;

#[test]
fn deadline_exactly_now_is_not_overdue() {
    let now: Zoned = "2026-10-14T10:30[Europe/Paris]".parse().unwrap();
    let ts: Timestamp = "2026-10-01T00:00:00Z".parse().unwrap();
    let mut task = Task {
        id: TaskId(1),
        title: "t".into(),
        description: String::new(),
        status: TaskStatus::Todo,
        priority: Priority::Normal,
        due: Some(Due::At(now.timestamp())),
        project: None,
        repo_id: None,
        version: 1,
        created_at: ts,
        updated_at: ts,
        completed_at: None,
    };
    assert!(!is_overdue(&task, &now));
    task.due = Some(Due::At(
        now.timestamp() - jiff::SignedDuration::from_secs(1),
    ));
    assert!(is_overdue(&task, &now));
}
