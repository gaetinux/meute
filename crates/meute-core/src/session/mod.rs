//! Session domain types.

mod types;

pub use types::{AgentKind, NewSession, Session, SessionFilter, SessionId, SessionState};

#[cfg(test)]
mod tests;
