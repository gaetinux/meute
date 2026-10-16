/// Errors raised while talking to tmux.
#[derive(Debug, thiserror::Error)]
pub enum TmuxError {
    /// The tmux binary was not found.
    #[error(
        "tmux introuvable : meute a besoin de tmux 3.2 ou plus récent (par exemple : sudo apt install tmux)"
    )]
    NotInstalled,
    /// The installed tmux is older than the minimum supported version.
    #[error("tmux {found} est trop ancien : meute a besoin de tmux 3.2 ou plus récent")]
    TooOld {
        /// Version as read from `tmux -V`.
        found: String,
    },
    /// A tmux command exited with a non-zero status.
    #[error("tmux {args} a échoué : {stderr}")]
    Command {
        /// Arguments of the failed command, space separated.
        args: String,
        /// Standard error of the command.
        stderr: String,
    },
    /// An I/O error occurred while spawning or reading tmux.
    #[error("erreur d'entrée/sortie avec tmux")]
    Io(#[from] std::io::Error),
    /// The output of tmux could not be understood.
    #[error("sortie de tmux illisible : {0}")]
    Parse(String),
}
