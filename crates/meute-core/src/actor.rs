//! Who did something, and through which channel.

use serde::{Deserialize, Serialize};

/// Who performed an action.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Author {
    /// The human user.
    User,
    /// A Claude session.
    Claude,
    /// meute itself.
    System,
}

impl Author {
    /// Stable lowercase identifier (storage and JSON).
    #[must_use]
    pub fn id(&self) -> &'static str {
        match self {
            Self::User => "user",
            Self::Claude => "claude",
            Self::System => "system",
        }
    }
}

/// Interface through which an action came in.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Channel {
    /// Terminal UI.
    Tui,
    /// Command line.
    Cli,
    /// MCP server.
    Mcp,
    /// Forge integration.
    Forge,
}

impl Channel {
    /// Stable lowercase identifier (storage and JSON).
    #[must_use]
    pub fn id(&self) -> &'static str {
        match self {
            Self::Tui => "tui",
            Self::Cli => "cli",
            Self::Mcp => "mcp",
            Self::Forge => "forge",
        }
    }
}

/// Full attribution of a change.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Actor {
    /// Who.
    pub author: Author,
    /// Through which interface.
    pub channel: Channel,
    /// Claude session id, when relevant.
    pub session_id: Option<String>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ids_are_lowercase() {
        assert_eq!(Author::Claude.id(), "claude");
        assert_eq!(Channel::Forge.id(), "forge");
        assert_eq!(serde_json::to_string(&Channel::Mcp).unwrap(), "\"mcp\"");
    }
}
