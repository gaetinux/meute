#![allow(dead_code, reason = "each test crate uses a subset of the helpers")]
use meute_tmux::Tmux;
use std::path::PathBuf;
use std::time::{Duration, Instant};

/// Throwaway tmux server on its own socket, killed on drop.
pub struct TestServer {
    tmux: Tmux,
}

impl TestServer {
    pub fn start() -> TestServer {
        let socket = format!("meute-test-{}", uuid::Uuid::new_v4());
        let tmux = Tmux::new(socket, Some(PathBuf::from("/dev/null")));
        let server = TestServer { tmux };
        server
            .tmux
            .run(&["new-session", "-d", "-s", "test", "-x", "200", "-y", "50"])
            .unwrap_or_else(|err| panic!("cannot start test tmux server: {err}"));
        server
    }

    pub fn tmux(&self) -> &Tmux {
        &self.tmux
    }
}

impl Drop for TestServer {
    fn drop(&mut self) {
        let _ = self.tmux.kill_server();
    }
}

/// Polls `f` every 100 ms for up to 10 s; panics with `what` on timeout.
pub fn wait_until(what: &str, mut f: impl FnMut() -> bool) {
    let deadline = Instant::now() + Duration::from_secs(10);
    while !f() {
        assert!(Instant::now() < deadline, "timed out waiting for {what}");
        std::thread::sleep(Duration::from_millis(100));
    }
}
