use crate::{MIN_VERSION, TmuxError, TmuxVersion, parse_version};
use std::io;
use std::path::{Path, PathBuf};
use std::process::Command;

/// Handle on a dedicated tmux server, identified by its socket name.
#[derive(Debug, Clone)]
pub struct Tmux {
    socket: String,
    config_file: Option<PathBuf>,
}

fn classify_spawn_error(err: io::Error) -> TmuxError {
    if err.kind() == io::ErrorKind::NotFound {
        TmuxError::NotInstalled
    } else {
        TmuxError::Io(err)
    }
}

/// Interprets the output of `tmux -V` against the minimum version.
fn classify_version(output: &str) -> Result<Option<TmuxVersion>, TmuxError> {
    let text = output.trim();
    match parse_version(text) {
        Some(found) if found < MIN_VERSION => Err(TmuxError::TooOld {
            found: text.strip_prefix("tmux").unwrap_or(text).trim().to_owned(),
        }),
        other => Ok(other),
    }
}

/// Whether the error means that no tmux server is listening on the socket.
pub(crate) fn is_no_server(err: &TmuxError) -> bool {
    matches!(err, TmuxError::Command { stderr, .. }
        if stderr.contains("no server running") || stderr.contains("error connecting to"))
}

impl Tmux {
    /// Creates a handle; nothing is spawned.
    pub fn new(socket: impl Into<String>, config_file: Option<PathBuf>) -> Tmux {
        Tmux {
            socket: socket.into(),
            config_file,
        }
    }
    /// Socket name passed to `-L`.
    pub fn socket(&self) -> &str {
        &self.socket
    }
    /// Configuration file passed to `-f`, if any.
    pub fn config_file(&self) -> Option<&Path> {
        self.config_file.as_deref()
    }
    /// `tmux -L <socket> [-f <config>]` with no other argument.
    pub fn command(&self) -> Command {
        let mut cmd = Command::new("tmux");
        cmd.arg("-L").arg(&self.socket);
        if let Some(config) = &self.config_file {
            cmd.arg("-f").arg(config);
        }
        cmd
    }
    /// Runs a tmux command and returns stdout without the final newline.
    pub fn run(&self, args: &[&str]) -> Result<String, TmuxError> {
        let output = self
            .command()
            .args(args)
            .output()
            .map_err(classify_spawn_error)?;
        if !output.status.success() {
            return Err(TmuxError::Command {
                args: args.join(" "),
                stderr: String::from_utf8_lossy(&output.stderr)
                    .trim_end()
                    .to_owned(),
            });
        }
        let stdout = String::from_utf8_lossy(&output.stdout);
        Ok(stdout.strip_suffix('\n').unwrap_or(&stdout).to_owned())
    }
    /// Whether a server is listening on the socket.
    pub fn is_running(&self) -> Result<bool, TmuxError> {
        match self.run(&["list-sessions"]) {
            Ok(_) => Ok(true),
            Err(err) if is_no_server(&err) => Ok(false),
            Err(err) => Err(err),
        }
    }
    /// Whether a session with exactly this name exists.
    pub fn has_session(&self, name: &str) -> Result<bool, TmuxError> {
        match self.run(&["has-session", "-t", &format!("={name}")]) {
            Ok(_) => Ok(true),
            Err(TmuxError::Command { .. }) => Ok(false),
            Err(err) => Err(err),
        }
    }
    /// Kills the server.
    pub fn kill_server(&self) -> Result<(), TmuxError> {
        self.run(&["kill-server"]).map(|_| ())
    }
    /// Runs `tmux -V` and checks it against the minimum version.
    pub fn check_version(&self) -> Result<Option<TmuxVersion>, TmuxError> {
        let output = Command::new("tmux")
            .arg("-V")
            .output()
            .map_err(classify_spawn_error)?;
        if !output.status.success() {
            return Err(TmuxError::Command {
                args: "-V".to_owned(),
                stderr: String::from_utf8_lossy(&output.stderr)
                    .trim_end()
                    .to_owned(),
            });
        }
        classify_version(&String::from_utf8_lossy(&output.stdout))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn missing_binary_is_not_installed() {
        let err = classify_spawn_error(io::Error::from(io::ErrorKind::NotFound));
        assert!(matches!(err, TmuxError::NotInstalled));
    }

    #[test]
    fn too_old_version_is_reported_without_prefix() {
        let err = classify_version("tmux 2.9a").unwrap_err();
        assert!(matches!(&err, TmuxError::TooOld { found } if found == "2.9a"));
        assert_eq!(
            err.to_string(),
            "tmux 2.9a est trop ancien : meute a besoin de tmux 3.2 ou plus récent"
        );
    }

    #[test]
    fn recent_and_unreadable_versions_are_accepted() {
        let found = classify_version("tmux 3.5a").unwrap();
        assert_eq!(found, Some(TmuxVersion { major: 3, minor: 5 }));
        assert_eq!(classify_version("tmux master").unwrap(), None);
    }

    #[test]
    fn other_io_errors_stay_io() {
        let err = classify_spawn_error(io::Error::from(io::ErrorKind::PermissionDenied));
        assert!(matches!(err, TmuxError::Io(_)));
    }
}
