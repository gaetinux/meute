use super::*;
use crate::CoreError;

fn all_states() -> Vec<(SessionState, &'static str, Option<i32>)> {
    vec![
        (SessionState::Running, "running", None),
        (SessionState::SubagentRunning, "subagent_running", None),
        (SessionState::Compacting, "compacting", None),
        (
            SessionState::PermissionRequested,
            "permission_requested",
            None,
        ),
        (SessionState::WaitingInput, "waiting_input", None),
        (SessionState::Idle, "idle", None),
        (SessionState::Exited { code: Some(3) }, "exited", Some(3)),
        (SessionState::Unreachable, "unreachable", None),
        (SessionState::MaybeStuck, "maybe_stuck", None),
        (SessionState::Unknown, "unknown", None),
    ]
}

#[test]
fn state_ids_round_trip_through_from_parts() {
    for (state, id, code) in all_states() {
        assert_eq!(state.id(), id);
        assert_eq!(SessionState::from_parts(id, code).unwrap(), state);
    }
    assert_eq!(
        SessionState::from_parts("exited", None).unwrap(),
        SessionState::Exited { code: None }
    );
    assert!(matches!(
        SessionState::from_parts("nope", None),
        Err(CoreError::Invalid(_))
    ));
}

#[test]
fn only_exited_and_unreachable_are_not_live() {
    assert!(SessionState::Running.is_live());
    assert!(SessionState::SubagentRunning.is_live());
    assert!(SessionState::Compacting.is_live());
    assert!(SessionState::PermissionRequested.is_live());
    assert!(SessionState::WaitingInput.is_live());
    assert!(SessionState::Idle.is_live());
    assert!(!SessionState::Exited { code: Some(0) }.is_live());
    assert!(!SessionState::Exited { code: None }.is_live());
    assert!(!SessionState::Unreachable.is_live());
    assert!(SessionState::MaybeStuck.is_live());
    assert!(SessionState::Unknown.is_live());
}

#[test]
fn labels_match_the_spec() {
    assert_eq!(SessionState::Running.label(), "en cours");
    assert_eq!(SessionState::SubagentRunning.label(), "sous-agent");
    assert_eq!(SessionState::Compacting.label(), "compactage");
    assert_eq!(SessionState::PermissionRequested.label(), "permission");
    assert_eq!(SessionState::WaitingInput.label(), "attend ta réponse");
    assert_eq!(SessionState::Idle.label(), "inactive");
    assert_eq!(
        SessionState::Exited { code: Some(2) }.label(),
        "terminée (2)"
    );
    assert_eq!(SessionState::Exited { code: None }.label(), "terminée");
    assert_eq!(SessionState::Unreachable.label(), "injoignable");
    assert_eq!(SessionState::MaybeStuck.label(), "bloquée ?");
    assert_eq!(SessionState::Unknown.label(), "inconnu ?");
}

#[test]
fn state_json_shape_is_tagged() {
    assert_eq!(
        serde_json::to_string(&SessionState::Exited { code: Some(2) }).unwrap(),
        r#"{"kind":"exited","code":2}"#
    );
    assert_eq!(
        serde_json::to_string(&SessionState::Running).unwrap(),
        r#"{"kind":"running"}"#
    );
}

#[test]
fn session_id_parse_display_and_short() {
    let text = "aaaa1111-0000-4000-8000-000000000001";
    let id = SessionId::parse(text).unwrap();
    assert_eq!(id.to_string(), text);
    assert_eq!(id.short(), "aaaa1111");
    assert_ne!(SessionId::new(), SessionId::new());
    match SessionId::parse("pas-un-uuid") {
        Err(CoreError::Invalid(msg)) => {
            assert_eq!(msg, "identifiant de session invalide : pas-un-uuid");
        }
        other => panic!("unexpected: {other:?}"),
    }
}

#[test]
fn agent_ids_round_trip() {
    assert_eq!(AgentKind::Claude.id(), "claude");
    assert_eq!(AgentKind::Bash.id(), "bash");
    assert_eq!(AgentKind::from_id("claude").unwrap(), AgentKind::Claude);
    assert_eq!(AgentKind::from_id("bash").unwrap(), AgentKind::Bash);
    assert!(AgentKind::from_id("zsh").is_err());
}
