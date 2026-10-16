use crate::client::is_no_server;
use crate::{Tmux, TmuxError};
use std::fmt;
use std::path::PathBuf;

/// Identifier of a tmux pane, such as `%12`.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct PaneId(pub String);

impl fmt::Display for PaneId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

/// A pane as reported by `list-panes`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PaneInfo {
    /// Pane identifier.
    pub id: PaneId,
    /// Name of the session holding the pane.
    pub session: String,
    /// Name of the window holding the pane.
    pub window: String,
    /// Value of the `@meute_id` pane option, if set.
    pub meute_id: Option<String>,
    /// Value of the `@meute_role` pane option, if set.
    pub role: Option<String>,
    /// Whether the command has exited (pane kept by `remain-on-exit`).
    pub dead: bool,
    /// Exit status of a dead pane.
    pub dead_status: Option<i32>,
    /// Width in columns.
    pub width: u16,
}

/// Parameters for starting a command in a new tmux window.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Spawn {
    /// Target session, created if missing.
    pub session: String,
    /// Working directory of the command.
    pub cwd: PathBuf,
    /// Command and arguments.
    pub command: Vec<String>,
    /// Environment variables set for the command.
    pub env: Vec<(String, String)>,
    /// Pane options set right after creation, in order.
    pub pane_options: Vec<(String, String)>,
}

const PANE_FORMAT: &str = "#{pane_id}\t#{session_name}\t#{window_name}\t#{@meute_id}\t#{@meute_role}\t#{pane_dead}\t#{pane_dead_status}\t#{pane_width}";

fn non_empty(field: &str) -> Option<String> {
    (!field.is_empty()).then(|| field.to_owned())
}

/// Parses one line of `list-panes` output.
pub fn parse_pane_line(line: &str) -> Result<PaneInfo, TmuxError> {
    let bad = |what: &str| TmuxError::Parse(format!("{what} : {line:?}"));
    let fields: Vec<&str> = line.split('\t').collect();
    let [
        id,
        session,
        window,
        meute_id,
        role,
        dead,
        dead_status,
        width,
    ] = fields[..]
    else {
        return Err(bad("ligne de panneau incomplète"));
    };
    let dead_status = match dead_status {
        "" => None,
        text => Some(
            text.parse()
                .map_err(|_| bad("statut de sortie illisible"))?,
        ),
    };
    Ok(PaneInfo {
        id: PaneId(id.to_owned()),
        session: session.to_owned(),
        window: window.to_owned(),
        meute_id: non_empty(meute_id),
        role: non_empty(role),
        dead: dead == "1",
        dead_status,
        width: width.parse().map_err(|_| bad("largeur illisible"))?,
    })
}

impl Tmux {
    /// Lists every pane of the server; no server means no panes.
    pub fn list_panes(&self) -> Result<Vec<PaneInfo>, TmuxError> {
        match self.run(&["list-panes", "-a", "-F", PANE_FORMAT]) {
            Ok(output) => output.lines().map(parse_pane_line).collect(),
            Err(err) if is_no_server(&err) => Ok(vec![]),
            Err(err) => Err(err),
        }
    }
    /// Starts a command in a new window of `spawn.session`, creating the
    /// session if needed, then applies the pane options in order.
    pub fn spawn_window(&self, spawn: &Spawn) -> Result<PaneId, TmuxError> {
        let target = format!("={}:", spawn.session);
        let cwd = spawn.cwd.to_string_lossy();
        let env: Vec<String> = spawn.env.iter().map(|(k, v)| format!("{k}={v}")).collect();
        let mut args: Vec<&str> = if self.has_session(&spawn.session)? {
            vec!["new-window", "-d", "-t", &target]
        } else {
            vec!["new-session", "-d", "-s", &spawn.session]
        };
        args.extend(["-P", "-F", "#{pane_id}", "-c", &cwd]);
        for pair in &env {
            args.extend(["-e", pair]);
        }
        args.push("--");
        args.extend(spawn.command.iter().map(String::as_str));
        let pane = PaneId(self.run(&args)?);
        for (name, value) in &spawn.pane_options {
            self.set_pane_option(&pane, name, value)?;
        }
        Ok(pane)
    }
    /// Sets a pane option.
    pub fn set_pane_option(&self, pane: &PaneId, name: &str, value: &str) -> Result<(), TmuxError> {
        self.run(&["set-option", "-p", "-t", &pane.0, name, value])
            .map(|_| ())
    }
    /// Sets a global (server) option.
    pub fn set_global_option(&self, name: &str, value: &str) -> Result<(), TmuxError> {
        self.run(&["set-option", "-g", name, value]).map(|_| ())
    }
    /// Swaps two panes without changing the focus.
    pub fn swap_panes(&self, src: &PaneId, dst: &PaneId) -> Result<(), TmuxError> {
        self.run(&["swap-pane", "-d", "-s", &src.0, "-t", &dst.0])
            .map(|_| ())
    }
    /// Gives the focus to a pane.
    pub fn select_pane(&self, pane: &PaneId) -> Result<(), TmuxError> {
        self.run(&["select-pane", "-t", &pane.0]).map(|_| ())
    }
    /// Sends keys to a pane.
    pub fn send_keys(&self, pane: &PaneId, keys: &[&str]) -> Result<(), TmuxError> {
        let mut args = vec!["send-keys", "-t", &pane.0];
        args.extend(keys);
        self.run(&args).map(|_| ())
    }
    /// Kills a pane.
    pub fn kill_pane(&self, pane: &PaneId) -> Result<(), TmuxError> {
        self.run(&["kill-pane", "-t", &pane.0]).map(|_| ())
    }
    /// Points the attached client at the pane's window.
    pub fn switch_client_to(&self, pane: &PaneId) -> Result<(), TmuxError> {
        self.run(&["switch-client", "-t", &pane.0]).map(|_| ())
    }
}
