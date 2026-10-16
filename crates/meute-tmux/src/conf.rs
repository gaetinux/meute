//! Generated tmux configuration of the `meute` server.

use crate::{MAIN_SESSION, MAIN_WINDOW, STATUS_OPTION};

/// Key bindings installed by meute (tmux key names such as `M-p`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Keys {
    /// Key that focuses the dashboard from anywhere.
    pub focus_board: String,
    /// Key that focuses the main area.
    pub focus_main: String,
}

/// Everything needed to build and render the `meute` layout.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LayoutSpec {
    /// Width of the dashboard pane, in columns.
    pub board_width: u16,
    /// Window width below which the dashboard is zoomed.
    pub narrow_threshold: u16,
    /// Command run in the dashboard pane.
    pub board_command: Vec<String>,
    /// Command run in the welcome pane.
    pub welcome_command: Vec<String>,
    /// Command run by tmux hooks to resynchronise the layout.
    pub sync_command: Vec<String>,
    /// Key bindings.
    pub keys: Keys,
}

/// Hooks that resynchronise the layout when a client appears or resizes.
const SYNC_HOOKS: [&str; 2] = ["client-attached", "client-resized"];

/// Renders the tmux configuration file of the `meute` server.
pub fn render_config(spec: &LayoutSpec) -> String {
    let target = format!("={MAIN_SESSION}:{MAIN_WINDOW}");
    let shell: Vec<String> = spec.sync_command.iter().map(|w| sh_quote(w)).collect();
    // The shell text is parsed twice by tmux: once when the file is sourced,
    // once when the hook command `run-shell -b "..."` is parsed.
    let run_shell = format!("run-shell -b \"{}\"", tmux_escape(&shell.join(" ")));
    let hook = tmux_escape(&run_shell);
    let mut lines = vec![
        "# Généré par meute : ce fichier est réécrit à chaque lancement, ne pas le modifier."
            .to_owned(),
        "set -g status-left \"[meute] \"".to_owned(),
        format!("set -g status-right \"#{{{STATUS_OPTION}}}\""),
        "set -g status-right-length 80".to_owned(),
        format!(
            "bind -n {} switch-client -t {target} \\; select-pane -t '{target}.{{right}}'",
            spec.keys.focus_board
        ),
        format!(
            "bind -n {} select-pane -t '{target}.{{left}}'",
            spec.keys.focus_main
        ),
    ];
    for name in SYNC_HOOKS {
        lines.push(format!("set-hook -g {name} \"{hook}\""));
    }
    let mut text = lines.join("\n");
    text.push('\n');
    text
}

/// Quotes a word for `sh` with single quotes.
fn sh_quote(word: &str) -> String {
    format!("'{}'", word.replace('\'', r"'\''"))
}

/// Escapes text for a double-quoted tmux string.
fn tmux_escape(text: &str) -> String {
    let mut escaped = String::with_capacity(text.len());
    for c in text.chars() {
        if matches!(c, '\\' | '"' | '$') {
            escaped.push('\\');
        }
        escaped.push(c);
    }
    escaped
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sh_quote_wraps_in_single_quotes() {
        assert_eq!(sh_quote("/opt/meute"), "'/opt/meute'");
        assert_eq!(sh_quote("a b"), "'a b'");
        assert_eq!(sh_quote(""), "''");
    }

    #[test]
    fn sh_quote_escapes_single_quotes() {
        assert_eq!(sh_quote("l'appli"), r"'l'\''appli'");
    }

    #[test]
    fn tmux_escape_backslash_double_quote_and_dollar() {
        assert_eq!(tmux_escape(r#"a\b"c$d"#), r#"a\\b\"c\$d"#);
        assert_eq!(tmux_escape("'x y'"), "'x y'");
    }
}
