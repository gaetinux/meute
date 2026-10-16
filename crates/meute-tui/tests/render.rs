use std::path::PathBuf;

use meute_core::repo::{Repo, RepoId};
use meute_core::session::{AgentKind, Session, SessionId, SessionState};
use meute_tui::{Board, BoardData, SessionRow};
use ratatui::Terminal;
use ratatui::backend::TestBackend;
use ratatui::crossterm::event::{KeyCode, KeyEvent, KeyModifiers};

const AT: jiff::Timestamp = jiff::Timestamp::UNIX_EPOCH;

fn session_row(
    n: u128,
    title: &str,
    cwd: &str,
    state: SessionState,
    displayed: bool,
) -> SessionRow {
    SessionRow {
        session: Session {
            id: SessionId(uuid::Uuid::from_u128(n)),
            agent: AgentKind::Bash,
            title: title.into(),
            project_id: None,
            repo_id: None,
            task_id: None,
            cwd: PathBuf::from(cwd),
            state,
            last_activity_at: AT,
            created_at: AT,
            ended_at: None,
        },
        has_pane: true,
        displayed,
    }
}

fn repo(id: i64, name: &str, kind: Option<&str>) -> Repo {
    Repo {
        id: RepoId(id),
        path: PathBuf::from(format!("/home/gaetinux/git/{name}")),
        name: name.into(),
        kind: kind.map(str::to_owned),
        discovered_at: AT,
    }
}

fn full_data() -> BoardData {
    BoardData {
        sessions: vec![
            session_row(
                1,
                "Bash principal",
                "/home/gaetinux/git/meute",
                SessionState::Idle,
                true,
            ),
            session_row(
                2,
                "Tests",
                "/home/gaetinux/git/meute/crates",
                SessionState::Exited { code: Some(2) },
                false,
            ),
        ],
        repos: vec![repo(1, "meute", Some("rust")), repo(2, "dotfiles", None)],
        orphans: vec!["%12".into()],
        home: Some(PathBuf::from("/home/gaetinux")),
    }
}

type TestResult = Result<(), std::io::Error>;

fn draw(board: &Board, width: u16) -> Result<String, std::io::Error> {
    let mut terminal = Terminal::new(TestBackend::new(width, 20))?;
    terminal.draw(|frame| board.render(frame))?;
    Ok(terminal.backend().to_string())
}

fn key(code: KeyCode) -> KeyEvent {
    KeyEvent::new(code, KeyModifiers::NONE)
}

#[test]
fn board_60_columns() -> TestResult {
    insta::assert_snapshot!(draw(&Board::new(full_data()), 60)?);
    Ok(())
}

#[test]
fn board_100_columns() -> TestResult {
    insta::assert_snapshot!(draw(&Board::new(full_data()), 100)?);
    Ok(())
}

#[test]
fn board_empty() -> TestResult {
    let data = BoardData {
        repos: vec![repo(1, "meute", Some("rust"))],
        ..BoardData::default()
    };
    insta::assert_snapshot!(draw(&Board::new(data), 60)?);
    Ok(())
}

#[test]
fn board_confirming_stop() -> TestResult {
    let mut board = Board::new(full_data());
    board.on_key(key(KeyCode::Char('x')));
    insta::assert_snapshot!(draw(&board, 60)?);
    Ok(())
}

#[test]
fn board_with_error() -> TestResult {
    let mut board = Board::new(full_data());
    board.set_error("tmux est introuvable".into());
    insta::assert_snapshot!(draw(&board, 60)?);
    Ok(())
}
