mod common;

use common::{TestServer, wait_until};
use meute_tmux::{
    Keys, Layout, LayoutSpec, MAIN_SESSION, MAIN_WINDOW, PaneId, PaneInfo, ROLE_BOARD,
    ROLE_WELCOME, Tmux, ensure_layout, render_config,
};

fn strings(items: &[&str]) -> Vec<String> {
    items.iter().map(|item| (*item).to_owned()).collect()
}

fn spec(sync_command: &[&str]) -> LayoutSpec {
    LayoutSpec {
        board_width: 60,
        narrow_threshold: 120,
        board_command: strings(&["sh", "-c", "sleep 3600"]),
        welcome_command: strings(&["sh", "-c", "sleep 3600"]),
        sync_command: strings(sync_command),
        keys: Keys {
            focus_board: "M-p".to_owned(),
            focus_main: "M-o".to_owned(),
        },
    }
}

fn layout_spec() -> LayoutSpec {
    spec(&["/opt/meute/bin/meute", "layout", "sync"])
}

fn main_window_panes(tmux: &Tmux) -> Vec<PaneInfo> {
    tmux.list_panes()
        .unwrap_or_else(|err| panic!("list-panes failed: {err}"))
        .into_iter()
        .filter(|pane| pane.session == MAIN_SESSION && pane.window == MAIN_WINDOW)
        .collect()
}

fn pane(tmux: &Tmux, id: &PaneId) -> PaneInfo {
    main_window_panes(tmux)
        .into_iter()
        .find(|pane| &pane.id == id)
        .unwrap_or_else(|| panic!("pane {id} not found in meute:main"))
}

fn ensure(tmux: &Tmux) -> Layout {
    ensure_layout(tmux, &layout_spec()).unwrap_or_else(|err| panic!("ensure_layout: {err}"))
}

fn assert_board_and_welcome(tmux: &Tmux, layout: &Layout) {
    let panes = main_window_panes(tmux);
    assert_eq!(panes.len(), 2, "{panes:?}");
    let board = pane(tmux, &layout.board);
    assert_eq!(board.role.as_deref(), Some(ROLE_BOARD));
    assert_eq!(board.width, 60);
    let Some(main) = &layout.main else {
        panic!("no main pane in {layout:?}");
    };
    assert_eq!(pane(tmux, main).role.as_deref(), Some(ROLE_WELCOME));
}

#[test]
fn generated_config() {
    insta::assert_snapshot!(render_config(&layout_spec()));
}

#[test]
fn generated_config_is_accepted_by_tmux() {
    let server = TestServer::start();
    let dir = tempfile::tempdir().unwrap();
    let config = render_config(&spec(&["/opt/l'appli meute/meute", "layout", "sync"]));
    let path = dir.path().join("tmux.conf");
    std::fs::write(&path, config).unwrap();
    let path = path.to_str().unwrap();
    server.tmux().run(&["source-file", path]).unwrap();
    let keys = server.tmux().run(&["list-keys", "-T", "root"]).unwrap();
    assert!(keys.contains("M-p"), "{keys}");
    assert!(keys.contains("M-o"), "{keys}");
}

#[test]
fn generated_hook_runs_sync_command_with_quoted_path() {
    let server = TestServer::start();
    let dir = tempfile::tempdir().unwrap();
    let bin_dir = dir.path().join("l'appli $HOME meute");
    std::fs::create_dir(&bin_dir).unwrap();
    let out = dir.path().join("out");
    let script = bin_dir.join("meute");
    let body = format!("#!/bin/sh\necho \"$@\" > '{}'\n", out.display());
    std::fs::write(&script, body).unwrap();
    std::fs::set_permissions(&script, std::os::unix::fs::PermissionsExt::from_mode(0o755)).unwrap();
    let config = render_config(&spec(&[script.to_str().unwrap(), "layout", "sync"]));
    let path = dir.path().join("tmux.conf");
    std::fs::write(&path, config).unwrap();
    let tmux = server.tmux();
    tmux.run(&["source-file", path.to_str().unwrap()]).unwrap();
    tmux.run(&["set-hook", "-g", "-R", "client-attached"])
        .unwrap();
    wait_until("sync command run by the hook", || {
        std::fs::read_to_string(&out).is_ok_and(|text| text == "layout sync\n")
    });
}

#[test]
fn is_narrow() {
    assert!(meute_tmux::is_narrow(119, 120));
    assert!(!meute_tmux::is_narrow(120, 120));
}

#[test]
fn fresh_server_gets_board_and_welcome() {
    let server = TestServer::start();
    let layout = ensure(server.tmux());
    assert_board_and_welcome(server.tmux(), &layout);
    assert!(!layout.zoomed);
}

#[test]
fn ensure_is_idempotent() {
    let server = TestServer::start();
    let first = ensure(server.tmux());
    let second = ensure(server.tmux());
    assert_eq!(first.board, second.board);
    assert_eq!(first.main, second.main);
    assert_eq!(main_window_panes(server.tmux()).len(), 2);
}

#[test]
fn killed_main_pane_is_replaced_by_welcome() {
    let server = TestServer::start();
    let tmux = server.tmux();
    let first = ensure(tmux);
    let old_main = first.main.unwrap();
    tmux.kill_pane(&old_main).unwrap();
    wait_until("main pane gone", || main_window_panes(tmux).len() == 1);
    let layout = ensure(tmux);
    assert_board_and_welcome(tmux, &layout);
    assert_ne!(layout.main, Some(old_main));
}

#[test]
fn killed_board_is_recreated() {
    let server = TestServer::start();
    let tmux = server.tmux();
    let first = ensure(tmux);
    tmux.kill_pane(&first.board).unwrap();
    wait_until("board gone", || main_window_panes(tmux).len() == 1);
    let layout = ensure(tmux);
    assert_board_and_welcome(tmux, &layout);
    assert_ne!(layout.board, first.board);
    assert_eq!(layout.main, first.main);
}

#[test]
fn narrow_window_zooms_board_and_wide_unzooms() {
    let server = TestServer::start();
    let tmux = server.tmux();
    ensure(tmux);
    tmux.run(&["resize-window", "-t", "=meute:main", "-x", "100"])
        .unwrap();
    let narrow = ensure(tmux);
    assert!(narrow.zoomed);
    assert_eq!(narrow.width, 100);
    tmux.run(&["resize-window", "-t", "=meute:main", "-x", "200"])
        .unwrap();
    let wide = ensure(tmux);
    assert!(!wide.zoomed);
    assert_eq!(wide.width, 200);
    assert_eq!(pane(tmux, &wide.board).width, 60);
}

#[test]
fn killed_main_window_is_recreated() {
    let server = TestServer::start();
    let tmux = server.tmux();
    ensure(tmux);
    tmux.run(&["new-window", "-d", "-t", "=meute:", "-n", "other"])
        .unwrap();
    tmux.run(&["kill-window", "-t", "=meute:main"]).unwrap();
    wait_until("main window gone", || main_window_panes(tmux).is_empty());
    let layout = ensure(tmux);
    assert_board_and_welcome(tmux, &layout);
}

#[test]
fn dead_board_is_replaced_and_removed() {
    let server = TestServer::start();
    let tmux = server.tmux();
    let first = ensure(tmux);
    let board = &first.board.0;
    tmux.run(&["set-option", "-p", "-t", board, "remain-on-exit", "on"])
        .unwrap();
    tmux.run(&["respawn-pane", "-k", "-t", board, "true"])
        .unwrap();
    wait_until("board dead", || pane(tmux, &first.board).dead);
    let layout = ensure(tmux);
    assert_board_and_welcome(tmux, &layout);
    assert_ne!(layout.board, first.board);
    assert_eq!(layout.main, first.main);
}
