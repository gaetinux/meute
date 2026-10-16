use super::*;
use crate::project::ProjectId;

#[test]
fn status_ids_labels_symbols_match_spec() {
    let all = [
        TaskStatus::Todo,
        TaskStatus::InProgress,
        TaskStatus::Blocked { reason: "x".into() },
        TaskStatus::Review,
        TaskStatus::Done,
    ];
    let ids: Vec<_> = all.iter().map(|s| s.id()).collect();
    assert_eq!(ids, ["todo", "in_progress", "blocked", "review", "done"]);
    let symbols: String = all.iter().map(|s| s.symbol()).collect();
    assert_eq!(symbols, "·»✕◎✓");
    assert_eq!(TaskStatus::Review.label(), "à relire");
    assert!(!TaskStatus::Done.is_open() && TaskStatus::Review.is_open());
}

#[test]
fn status_parses_from_id_and_blocked_needs_reason() {
    assert_eq!(
        TaskStatus::from_id("review", None).unwrap(),
        TaskStatus::Review
    );
    assert!(TaskStatus::from_id("blocked", None).is_err());
    assert!(TaskStatus::from_id("blocked", Some("  ")).is_err());
    assert!(TaskStatus::from_id("nope", None).is_err());
}

#[test]
fn priority_markers_and_order() {
    assert_eq!(Priority::Urgent.marker(), "!!");
    assert_eq!(Priority::High.marker(), "!");
    let mut v = vec![
        Priority::Low,
        Priority::Urgent,
        Priority::Normal,
        Priority::High,
    ];
    v.sort();
    assert_eq!(
        v,
        [
            Priority::Urgent,
            Priority::High,
            Priority::Normal,
            Priority::Low
        ]
    );
}

#[test]
fn task_id_displays_with_hash() {
    assert_eq!(TaskId(12).to_string(), "#12");
}

#[test]
fn priority_from_id_roundtrips() {
    for p in [
        Priority::Urgent,
        Priority::High,
        Priority::Normal,
        Priority::Low,
    ] {
        assert_eq!(Priority::from_id(p.id()).unwrap(), p);
    }
    assert!(Priority::from_id("nope").is_err());
}

#[test]
fn task_serializes_flat_status_and_due() {
    let ts: jiff::Timestamp = "2026-10-15T08:00:00Z".parse().unwrap();
    let task = Task {
        id: TaskId(3),
        title: "t".into(),
        description: String::new(),
        status: TaskStatus::Blocked {
            reason: "attend review".into(),
        },
        priority: Priority::High,
        due: Some(Due::Date("2026-10-20".parse().unwrap())),
        project: Some(ProjectRef {
            id: ProjectId(1),
            name: "meute".into(),
        }),
        repo_id: None,
        version: 2,
        created_at: ts,
        updated_at: ts,
        completed_at: None,
    };
    let v = serde_json::to_value(&task).unwrap();
    assert_eq!(v["id"], 3);
    assert_eq!(v["status"], "blocked");
    assert_eq!(v["blocked_reason"], "attend review");
    assert_eq!(v["priority"], "high");
    assert_eq!(
        v["due"],
        serde_json::json!({"kind": "date", "value": "2026-10-20"})
    );
    assert_eq!(v["project"], serde_json::json!({"id": 1, "name": "meute"}));
    assert_eq!(v["created_at"], "2026-10-15T08:00:00Z");
    assert!(v["completed_at"].is_null());
}
