//! Quick-add parsing: `title @project !|!! >due`.

mod due;

pub use due::parse_due;

use crate::error::{CoreError, Result};
use crate::task::{Due, Priority};

/// Result of parsing a quick-add line.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct QuickAdd {
    /// Title left once the special tokens are removed.
    pub title: String,
    /// Project name given by an `@name` token (last one wins).
    pub project: Option<String>,
    /// Priority given by `!` or `!!` (last one wins), `Normal` otherwise.
    pub priority: Priority,
    /// Deadline given by a valid `>due` token (last one wins).
    pub due: Option<Due>,
}

/// Parses `title @project !|!! >due`, interpreting dates in the timezone of `now`.
///
/// Only whitespace-separated tokens that start with `@`, `!` or `>` are candidates;
/// unrecognised candidates stay in the title.
///
/// # Errors
///
/// Returns [`CoreError::Invalid`] when the title is empty once tokens are removed.
pub fn parse_quick_add(input: &str, now: &jiff::Zoned) -> Result<QuickAdd> {
    let mut title_words = Vec::new();
    let mut project = None;
    let mut priority = Priority::Normal;
    let mut due = None;

    for token in input.split_whitespace() {
        if let Some(name) = token.strip_prefix('@').filter(|n| !n.is_empty()) {
            project = Some(name.to_owned());
        } else if token == "!" {
            priority = Priority::High;
        } else if token == "!!" {
            priority = Priority::Urgent;
        } else if let Some(parsed) = token.strip_prefix('>').and_then(|d| parse_due(d, now)) {
            due = Some(parsed);
        } else {
            title_words.push(token);
        }
    }

    if title_words.is_empty() {
        return Err(CoreError::Invalid("titre vide".into()));
    }
    Ok(QuickAdd {
        title: title_words.join(" "),
        project,
        priority,
        due,
    })
}

#[cfg(test)]
mod tests;
