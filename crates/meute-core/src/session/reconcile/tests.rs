use jiff::Timestamp;
use uuid::Uuid;

use super::*;
use crate::session::AgentKind;

fn id(n: u128) -> SessionId {
    SessionId(Uuid::from_u128(n))
}

fn session(n: u128, agent: AgentKind, state: SessionState) -> Session {
    Session {
        id: id(n),
        agent,
        title: format!("s{n}"),
        project_id: None,
        repo_id: None,
        task_id: None,
        cwd: "/tmp".into(),
        state,
        last_activity_at: Timestamp::UNIX_EPOCH,
        created_at: Timestamp::UNIX_EPOCH,
        ended_at: None,
    }
}

fn alive(n: u128) -> PaneObservation {
    PaneObservation {
        meute_id: id(n).to_string(),
        dead: false,
        exit_code: None,
    }
}

fn dead(n: u128, exit_code: Option<i32>) -> PaneObservation {
    PaneObservation {
        meute_id: id(n).to_string(),
        dead: true,
        exit_code,
    }
}

fn raw(meute_id: &str) -> PaneObservation {
    PaneObservation {
        meute_id: meute_id.into(),
        dead: false,
        exit_code: None,
    }
}

#[test]
fn missing_pane_makes_live_session_unreachable() {
    let s = [session(1, AgentKind::Claude, SessionState::Idle)];
    let r = reconcile(&s, &[]);
    assert_eq!(r.updates, vec![(id(1), SessionState::Unreachable)]);
    assert!(r.orphans.is_empty());
}

#[test]
fn dead_pane_gives_exited_with_code() {
    let s = [session(1, AgentKind::Bash, SessionState::Running)];
    let r = reconcile(&s, &[dead(1, Some(7))]);
    assert_eq!(
        r.updates,
        vec![(id(1), SessionState::Exited { code: Some(7) })]
    );
}

#[test]
fn dead_pane_without_status_gives_exited_none() {
    let s = [session(1, AgentKind::Claude, SessionState::WaitingInput)];
    let r = reconcile(&s, &[dead(1, None)]);
    assert_eq!(
        r.updates,
        vec![(id(1), SessionState::Exited { code: None })]
    );
}

#[test]
fn live_bash_pane_restores_running_from_unknown() {
    let s = [session(1, AgentKind::Bash, SessionState::Unknown)];
    let r = reconcile(&s, &[alive(1)]);
    assert_eq!(r.updates, vec![(id(1), SessionState::Running)]);
}

#[test]
fn running_bash_with_live_pane_needs_no_update() {
    let s = [session(1, AgentKind::Bash, SessionState::Running)];
    assert_eq!(reconcile(&s, &[alive(1)]), Reconciliation::default());
}

#[test]
fn claude_session_with_live_pane_is_untouched() {
    let s = [session(1, AgentKind::Claude, SessionState::Unknown)];
    assert_eq!(reconcile(&s, &[alive(1)]), Reconciliation::default());
}

#[test]
fn ended_sessions_are_never_updated() {
    let s = [
        session(1, AgentKind::Bash, SessionState::Exited { code: Some(0) }),
        session(2, AgentKind::Claude, SessionState::Unreachable),
    ];
    assert_eq!(reconcile(&s, &[]), Reconciliation::default());
}

#[test]
fn pane_of_an_ended_session_is_not_an_orphan() {
    let s = [session(
        1,
        AgentKind::Bash,
        SessionState::Exited { code: None },
    )];
    assert_eq!(reconcile(&s, &[alive(1)]), Reconciliation::default());
}

#[test]
fn unknown_and_malformed_ids_are_orphans_once() {
    let s = [session(1, AgentKind::Bash, SessionState::Running)];
    let panes = [raw("pas-un-uuid"), alive(1), alive(9), raw("pas-un-uuid")];
    let r = reconcile(&s, &panes);
    assert!(r.updates.is_empty());
    assert_eq!(
        r.orphans,
        vec!["pas-un-uuid".to_string(), id(9).to_string()]
    );
}
