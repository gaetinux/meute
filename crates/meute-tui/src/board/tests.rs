use meute_core::repo::{Repo, RepoId};
use meute_core::session::{AgentKind, Session, SessionId, SessionState};
use ratatui::crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use std::path::PathBuf;

use super::{Board, BoardAction, BoardData, SessionRow};

fn sid(n: u128) -> SessionId {
    SessionId(uuid::Uuid::from_u128(n))
}

fn row(n: u128, state: SessionState, has_pane: bool) -> SessionRow {
    let at = "2026-10-16T08:00:00Z".parse().unwrap();
    SessionRow {
        session: Session {
            id: sid(n),
            agent: AgentKind::Bash,
            title: format!("session {n}"),
            project_id: None,
            repo_id: Some(RepoId(7)),
            task_id: None,
            cwd: PathBuf::from(format!("/work/s{n}")),
            state,
            last_activity_at: at,
            created_at: at,
            ended_at: None,
        },
        has_pane,
        displayed: false,
    }
}

fn repo(id: i64, name: &str) -> Repo {
    Repo {
        id: RepoId(id),
        path: PathBuf::from(format!("/repos/{name}")),
        name: name.into(),
        kind: None,
        discovered_at: "2026-10-16T08:00:00Z".parse().unwrap(),
    }
}

fn data(sessions: Vec<SessionRow>, repos: Vec<Repo>) -> BoardData {
    BoardData {
        sessions,
        repos,
        orphans: vec![],
        home: None,
    }
}

fn key(code: KeyCode) -> KeyEvent {
    KeyEvent::new(code, KeyModifiers::NONE)
}

fn board() -> Board {
    Board::new(data(
        vec![row(1, SessionState::Idle, true)],
        vec![repo(1, "alpha"), repo(2, "beta")],
    ))
}

#[test]
fn enter_on_session_shows_it() {
    let mut b = board();
    assert_eq!(
        b.on_key(key(KeyCode::Enter)),
        Some(BoardAction::Show(sid(1)))
    );
}

#[test]
fn enter_and_n_on_repo_launch_bash_there() {
    let mut b = board();
    b.on_key(key(KeyCode::Down));
    let expected = Some(BoardAction::LaunchBash {
        cwd: PathBuf::from("/repos/alpha"),
        repo_id: Some(RepoId(1)),
    });
    assert_eq!(b.on_key(key(KeyCode::Enter)), expected);
    assert_eq!(b.on_key(key(KeyCode::Char('n'))), expected);
}

#[test]
fn n_on_session_launches_in_its_cwd() {
    let mut b = board();
    assert_eq!(
        b.on_key(key(KeyCode::Char('n'))),
        Some(BoardAction::LaunchBash {
            cwd: PathBuf::from("/work/s1"),
            repo_id: Some(RepoId(7)),
        })
    );
}

#[test]
fn x_then_o_stops() {
    let mut b = board();
    assert_eq!(b.on_key(key(KeyCode::Char('x'))), None);
    assert_eq!(
        b.on_key(key(KeyCode::Char('o'))),
        Some(BoardAction::Stop(sid(1)))
    );
    assert_eq!(
        b.on_key(key(KeyCode::Enter)),
        Some(BoardAction::Show(sid(1)))
    );
}

#[test]
fn x_then_other_key_cancels() {
    let mut b = board();
    b.on_key(key(KeyCode::Char('x')));
    assert_eq!(b.on_key(key(KeyCode::Char('q'))), None);
    assert_eq!(b.on_key(key(KeyCode::Char('o'))), None);
}

#[test]
fn x_on_repo_does_nothing() {
    let mut b = board();
    b.on_key(key(KeyCode::Down));
    assert_eq!(b.on_key(key(KeyCode::Char('x'))), None);
    assert_eq!(b.on_key(key(KeyCode::Char('o'))), None);
}

#[test]
fn navigation_is_bounded() {
    let mut b = board();
    b.on_key(key(KeyCode::Up));
    b.on_key(key(KeyCode::Char('k')));
    assert_eq!(
        b.on_key(key(KeyCode::Enter)),
        Some(BoardAction::Show(sid(1)))
    );
    for _ in 0..10 {
        b.on_key(key(KeyCode::Down));
    }
    b.on_key(key(KeyCode::Char('j')));
    assert_eq!(
        b.on_key(key(KeyCode::Enter)),
        Some(BoardAction::LaunchBash {
            cwd: PathBuf::from("/repos/beta"),
            repo_id: Some(RepoId(2)),
        })
    );
}

#[test]
fn selection_survives_reordering() {
    let mut b = Board::new(data(
        vec![
            row(1, SessionState::Idle, true),
            row(2, SessionState::Idle, true),
        ],
        vec![],
    ));
    assert_eq!(
        b.on_key(key(KeyCode::Enter)),
        Some(BoardAction::Show(sid(1)))
    );
    b.set_data(data(
        vec![
            row(2, SessionState::Idle, true),
            row(1, SessionState::Idle, true),
        ],
        vec![],
    ));
    assert_eq!(
        b.on_key(key(KeyCode::Enter)),
        Some(BoardAction::Show(sid(1)))
    );
}

#[test]
fn ended_sessions_are_listed_after_live_ones_and_only_with_a_pane() {
    let mut b = Board::new(data(
        vec![
            row(1, SessionState::Exited { code: Some(0) }, true),
            row(2, SessionState::Unreachable, false),
            row(3, SessionState::Running, true),
        ],
        vec![],
    ));
    assert_eq!(
        b.on_key(key(KeyCode::Enter)),
        Some(BoardAction::Show(sid(3)))
    );
    b.on_key(key(KeyCode::Down));
    assert_eq!(
        b.on_key(key(KeyCode::Enter)),
        Some(BoardAction::Show(sid(1)))
    );
    b.on_key(key(KeyCode::Down));
    assert_eq!(
        b.on_key(key(KeyCode::Enter)),
        Some(BoardAction::Show(sid(1)))
    );
}

#[test]
fn release_events_are_ignored() {
    let mut b = board();
    let mut release = key(KeyCode::Enter);
    release.kind = ratatui::crossterm::event::KeyEventKind::Release;
    assert_eq!(b.on_key(release), None);
}
