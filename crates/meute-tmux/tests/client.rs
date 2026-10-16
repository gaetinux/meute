mod common;

use common::TestServer;
use meute_tmux::{Tmux, TmuxError};

#[test]
fn start_run_and_kill() {
    let server = TestServer::start();
    let tmux = server.tmux();
    assert!(tmux.has_session("test").unwrap());
    assert!(!tmux.has_session("tes").unwrap());
    tmux.kill_server().unwrap();
    assert!(!tmux.is_running().unwrap());
}

#[test]
fn failed_command_reports_stderr() {
    let server = TestServer::start();
    let err = server.tmux().run(&["kill-pane", "-t", "%999"]).unwrap_err();
    let TmuxError::Command { stderr, .. } = err else {
        panic!("expected a Command error, got: {err}");
    };
    assert!(!stderr.is_empty());
}

#[test]
fn never_started_socket_is_not_running() {
    let tmux = Tmux::new(format!("meute-test-{}", uuid::Uuid::new_v4()), None);
    assert!(!tmux.is_running().unwrap());
}

#[test]
fn installed_tmux_passes_version_check() {
    let tmux = Tmux::new("meute-test-unused", None);
    assert!(tmux.check_version().is_ok());
}
