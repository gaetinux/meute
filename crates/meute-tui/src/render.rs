//! Drawing of the dashboard.

use std::path::Path;

use ratatui::Frame;
use ratatui::layout::{Constraint, Layout};
use ratatui::style::{Modifier, Style};
use ratatui::text::Line;
use ratatui::widgets::Paragraph;

use crate::board::Board;

const HELP: &str = "↑↓ choisir · Entrée afficher · n nouveau Bash · x arrêter";
const NO_SESSION: &str = "Aucune session. Choisissez un dépôt et appuyez sur n.";

impl Board {
    /// Draw the board on the whole frame.
    pub fn render(&self, frame: &mut Frame) {
        let [body, footer] =
            Layout::vertical([Constraint::Min(0), Constraint::Length(1)]).areas(frame.area());
        frame.render_widget(Paragraph::new(self.body_lines()), body);
        frame.render_widget(Paragraph::new(self.footer_text()), footer);
    }

    fn body_lines(&self) -> Vec<Line<'static>> {
        let home = self.data.home.as_deref();
        let sessions = self.visible_sessions();
        let mut lines = vec![
            Line::styled("meute", Style::new().add_modifier(Modifier::BOLD)),
            Line::default(),
            Line::styled("Sessions", Style::new().add_modifier(Modifier::BOLD)),
        ];
        if sessions.is_empty() {
            lines.push(Line::from(NO_SESSION));
        }
        for (index, row) in sessions.iter().enumerate() {
            let marker = if row.displayed { "▶" } else { " " };
            let text = format!(
                "{marker} {}  {}  {}",
                row.session.title,
                row.session.state.label(),
                display_path(&row.session.cwd, home)
            );
            lines.push(self.row_line(index, text));
        }
        lines.push(Line::default());
        lines.push(Line::styled(
            "Dépôts",
            Style::new().add_modifier(Modifier::BOLD),
        ));
        for (offset, repo) in self.data.repos.iter().enumerate() {
            let text = match &repo.kind {
                Some(kind) => format!("  {} ({kind})", repo.name),
                None => format!("  {}", repo.name),
            };
            lines.push(self.row_line(sessions.len() + offset, text));
        }
        if !self.data.orphans.is_empty() {
            lines.push(Line::default());
            lines.push(Line::styled(
                "Orphelins",
                Style::new().add_modifier(Modifier::BOLD),
            ));
            lines.extend(
                self.data
                    .orphans
                    .iter()
                    .map(|id| Line::from(format!("  {id}"))),
            );
        }
        lines
    }

    fn row_line(&self, index: usize, text: String) -> Line<'static> {
        if index == self.selected {
            Line::styled(text, Style::new().add_modifier(Modifier::REVERSED))
        } else {
            Line::from(text)
        }
    }

    fn footer_text(&self) -> String {
        if let Some(message) = &self.error {
            return format!("Erreur : {message}");
        }
        if let Some(id) = self.confirming {
            let title = self
                .data
                .sessions
                .iter()
                .find(|r| r.session.id == id)
                .map_or("", |r| r.session.title.as_str());
            return format!("Arrêter « {title} » ? o : oui · autre touche : non");
        }
        HELP.to_owned()
    }
}

/// `path` with the `home` prefix replaced by `~` (component-based).
fn display_path(path: &Path, home: Option<&Path>) -> String {
    match home.and_then(|home| path.strip_prefix(home).ok()) {
        Some(rest) if rest.as_os_str().is_empty() => "~".to_owned(),
        Some(rest) => format!("~/{}", rest.display()),
        None => path.display().to_string(),
    }
}
