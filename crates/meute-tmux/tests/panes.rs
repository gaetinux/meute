mod common;

use common::{TestServer, wait_until};
use meute_tmux::{PaneId, PaneInfo, Spawn, Tmux, TmuxError, parse_pane_line};
use std::path::PathBuf;

const UUID: &str = "8c1f6a52-0d0e-4a8e-9c53-3b7a7f0e5d11";

fn spawn(session: &str, meute_id: &str, command: &str) -> Spawn {
    Spawn {
        session: session.to_owned(),
        cwd: PathBuf::from("/tmp"),
        command: vec!["sh".to_owned(), "-c".to_owned(), command.to_owned()],
        env: vec![],
        pane_options: vec![("@meute_id".to_owned(), meute_id.to_owned())],
    }
}

fn pane_by_meute_id(tmux: &Tmux, meute_id: &str) -> Option<PaneInfo> {
    tmux.list_panes()
        .unwrap_or_else(|err| panic!("list-panes failed: {err}"))
        .into_iter()
        .find(|pane| pane.meute_id.as_deref() == Some(meute_id))
}

#[test]
fn parse_dead_pane_line() {
    let line = format!("%3\tmeute-bg\tw\t{UUID}\t\t1\t7\t80");
    let pane = parse_pane_line(&line).unwrap();
    assert_eq!(pane.id, PaneId("%3".to_owned()));
    assert_eq!(pane.session, "meute-bg");
    assert_eq!(pane.window, "w");
    assert_eq!(pane.meute_id.as_deref(), Some(UUID));
    assert_eq!(pane.role, None);
    assert!(pane.dead);
    assert_eq!(pane.dead_status, Some(7));
    assert_eq!(pane.width, 80);
}

#[test]
fn parse_live_pane_line() {
    let pane = parse_pane_line("%4\tmeute\tmain\t\tboard\t0\t\t40").unwrap();
    assert!(!pane.dead);
    assert_eq!(pane.dead_status, None);
    assert_eq!(pane.meute_id, None);
    assert_eq!(pane.role.as_deref(), Some("board"));
}

#[test]
fn parse_short_line_is_an_error() {
    let err = parse_pane_line("%3\tmeute-bg\tw\t\t\t1\t7").unwrap_err();
    assert!(matches!(err, TmuxError::Parse(_)));
}

#[test]
fn parse_non_numeric_width_is_an_error() {
    let err = parse_pane_line("%3\tmeute-bg\tw\t\t\t0\t\twide").unwrap_err();
    assert!(matches!(err, TmuxError::Parse(_)));
}

#[test]
fn list_panes_on_never_started_socket_is_empty() {
    let tmux = Tmux::new(format!("meute-test-{}", uuid::Uuid::new_v4()), None);
    assert!(tmux.list_panes().unwrap().is_empty());
}

#[test]
fn spawn_creates_bg_session_then_windows() {
    let server = TestServer::start();
    let tmux = server.tmux();
    let first = tmux
        .spawn_window(&spawn("bg", "one", "sleep 3600"))
        .unwrap();
    let second = tmux
        .spawn_window(&spawn("bg", "two", "sleep 3600"))
        .unwrap();
    assert_ne!(first, second);
    assert!(tmux.has_session("bg").unwrap());
    let panes = tmux.list_panes().unwrap();
    let bg: Vec<_> = panes.iter().filter(|pane| pane.session == "bg").collect();
    assert_eq!(bg.len(), 2);
    assert!(
        bg.iter()
            .any(|pane| pane.meute_id.as_deref() == Some("one"))
    );
    assert!(
        bg.iter()
            .any(|pane| pane.meute_id.as_deref() == Some("two"))
    );
}

#[test]
fn spawn_passes_cwd_and_env() {
    let server = TestServer::start();
    let dir = tempfile::tempdir().unwrap();
    let out = dir.path().join("out.txt");
    let cwd = tempfile::tempdir().unwrap();
    let cwd_path = cwd.path().canonicalize().unwrap();
    let request = Spawn {
        session: "bg".to_owned(),
        cwd: cwd_path.clone(),
        command: vec![
            "sh".to_owned(),
            "-c".to_owned(),
            r#"pwd > "$OUT"; echo "$MEUTE_SESSION" >> "$OUT"; sleep 3600"#.to_owned(),
        ],
        env: vec![
            ("OUT".to_owned(), out.display().to_string()),
            ("MEUTE_SESSION".to_owned(), UUID.to_owned()),
        ],
        pane_options: vec![],
    };
    server.tmux().spawn_window(&request).unwrap();
    wait_until("the command output", || {
        std::fs::read_to_string(&out).is_ok_and(|text| text.lines().count() == 2)
    });
    let text = std::fs::read_to_string(&out).unwrap();
    assert_eq!(text, format!("{}\n{UUID}\n", cwd_path.display()));
}

#[test]
fn remain_on_exit_keeps_dead_pane_with_status() {
    let server = TestServer::start();
    let tmux = server.tmux();
    tmux.set_global_option("remain-on-exit", "on").unwrap();
    tmux.spawn_window(&spawn("bg", "gone", "exit 3")).unwrap();
    wait_until("the pane to die", || {
        pane_by_meute_id(tmux, "gone").is_some_and(|pane| pane.dead)
    });
    let pane = pane_by_meute_id(tmux, "gone").unwrap();
    assert_eq!(pane.dead_status, Some(3));
}

#[test]
fn meute_id_follows_the_pane_through_swap() {
    let server = TestServer::start();
    let tmux = server.tmux();
    let a = tmux
        .spawn_window(&spawn("one", "id-a", "sleep 3600"))
        .unwrap();
    let b = tmux
        .spawn_window(&spawn("two", "id-b", "sleep 3600"))
        .unwrap();
    tmux.swap_panes(&a, &b).unwrap();
    let panes = tmux.list_panes().unwrap();
    let find = |id: &PaneId| panes.iter().find(|pane| &pane.id == id).unwrap();
    assert_eq!(find(&a).meute_id.as_deref(), Some("id-a"));
    assert_eq!(find(&a).session, "two");
    assert_eq!(find(&b).meute_id.as_deref(), Some("id-b"));
    assert_eq!(find(&b).session, "one");
}

#[test]
fn kill_pane_removes_it() {
    let server = TestServer::start();
    let tmux = server.tmux();
    let pane = tmux
        .spawn_window(&spawn("bg", "doomed", "sleep 3600"))
        .unwrap();
    tmux.kill_pane(&pane).unwrap();
    assert!(pane_by_meute_id(tmux, "doomed").is_none());
}
