//! Who did something, and through which channel.

use crate::{CoreError, Result};
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

    /// Parses an identifier produced by [`Author::id`].
    ///
    /// # Errors
    /// [`CoreError::Invalid`] on an unknown identifier.
    pub fn from_id(id: &str) -> Result<Self> {
        match id {
            "user" => Ok(Self::User),
            "claude" => Ok(Self::Claude),
            "system" => Ok(Self::System),
            other => Err(CoreError::Invalid(format!("auteur inconnu : {other}"))),
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

    /// Parses an identifier produced by [`Channel::id`].
    ///
    /// # Errors
    /// [`CoreError::Invalid`] on an unknown identifier.
    pub fn from_id(id: &str) -> Result<Self> {
        match id {
            "tui" => Ok(Self::Tui),
            "cli" => Ok(Self::Cli),
            "mcp" => Ok(Self::Mcp),
            "forge" => Ok(Self::Forge),
            other => Err(CoreError::Invalid(format!("canal inconnu : {other}"))),
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
