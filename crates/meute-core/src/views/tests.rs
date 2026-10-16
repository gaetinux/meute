use super::*;
use crate::task::{Due, Priority::*, Task, TaskId, TaskStatus, TaskStatus::*};
use jiff::{Timestamp, Zoned};

fn now() -> Zoned {
    "2026-10-14T10:30[Europe/Paris]".parse().unwrap()
}

fn date(s: &str) -> Due {
    Due::Date(s.parse().unwrap())
}

fn at(s: &str) -> Due {
    let z: Zoned = s.parse().unwrap();
    Due::At(z.timestamp())
}

fn task(due: Option<Due>, status: TaskStatus, priority: crate::task::Priority, id: i64) -> Task {
    let ts: Timestamp = "2026-10-01T00:00:00Z".parse().unwrap();
    Task {
        id: TaskId(id),
        title: format!("task {id}"),
        description: String::new(),
        status,
        priority,
        due,
        project: None,
        repo_id: None,
        version: 1,
        created_at: ts,
        updated_at: ts,
        completed_at: None,
    }
}

fn done_at(rfc3339: &str) -> Task {
    let mut t = task(None, Done, Normal, 99);
    t.completed_at = Some(rfc3339.parse().unwrap());
    t
}

#[test]
fn buckets_follow_rules() {
    let n = now();
    assert_eq!(
        bucket_of(&task(Some(date("2026-10-13")), Todo, Normal, 1), &n),
        Some(Bucket::Overdue)
    );
    assert_eq!(
        bucket_of(
            &task(Some(at("2026-10-14T09:00[Europe/Paris]")), Todo, Normal, 2),
            &n
        ),
        Some(Bucket::Overdue)
    );
    assert_eq!(
        bucket_of(&task(Some(date("2026-10-14")), Todo, Normal, 3), &n),
        Some(Bucket::Today)
    );
    assert_eq!(
        bucket_of(
            &task(Some(at("2026-10-14T18:00[Europe/Paris]")), Todo, Normal, 4),
            &n
        ),
        Some(Bucket::Today)
    );
    assert_eq!(
        bucket_of(&task(Some(date("2026-10-15")), Todo, Normal, 5), &n),
        Some(Bucket::Upcoming)
    );
    assert_eq!(
        bucket_of(&task(None, Todo, Normal, 6), &n),
        Some(Bucket::NoDue)
    );
    assert_eq!(
        bucket_of(&done_at("2026-10-14T07:00Z"), &n),
        Some(Bucket::DoneToday)
    );
    assert_eq!(bucket_of(&done_at("2026-10-13T07:00Z"), &n), None);
}

#[test]
fn sort_by_due_then_priority_then_id() {
    let mut v = vec![
        task(None, Todo, Urgent, 1),
        task(Some(date("2026-10-15")), Todo, Low, 2),
        task(Some(date("2026-10-15")), Todo, High, 3),
        task(Some(at("2026-10-15T09:00[Europe/Paris]")), Todo, Low, 4),
    ];
    sort_for_display(&mut v, now().time_zone());
    assert_eq!(v.iter().map(|t| t.id.0).collect::<Vec<_>>(), [4, 3, 2, 1]);
}

#[test]
fn due_formatting_in_french() {
    let n = now();
    assert_eq!(format_due(&date("2026-10-14"), &n), "aujourd'hui");
    assert_eq!(format_due(&date("2026-10-15"), &n), "demain");
    assert_eq!(format_due(&date("2026-10-19"), &n), "lun. 19 oct.");
    assert_eq!(
        format_due(&at("2026-10-14T18:00[Europe/Paris]"), &n),
        "aujourd'hui 18:00"
    );
    assert_eq!(format_due(&date("2027-01-05"), &n), "mar. 5 janv. 2027");
}

#[test]
fn labels_and_is_overdue() {
    let n = now();
    assert_eq!(Bucket::Overdue.label(), "En retard");
    assert_eq!(Bucket::Today.label(), "Aujourd'hui");
    assert_eq!(Bucket::Upcoming.label(), "À venir");
    assert_eq!(Bucket::NoDue.label(), "Sans échéance");
    assert_eq!(Bucket::DoneToday.label(), "Faites aujourd'hui");
    assert!(is_overdue(
        &task(Some(date("2026-10-13")), Todo, Normal, 1),
        &n
    ));
    assert!(!is_overdue(
        &task(Some(date("2026-10-14")), Todo, Normal, 1),
        &n
    ));
    assert!(!is_overdue(&task(None, Todo, Normal, 1), &n));
}
