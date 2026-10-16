/// A tmux version (`major.minor`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub struct TmuxVersion {
    /// Major number.
    pub major: u32,
    /// Minor number.
    pub minor: u32,
}

/// Oldest tmux version supported by meute.
pub const MIN_VERSION: TmuxVersion = TmuxVersion { major: 3, minor: 2 };

/// Parses the output of `tmux -V`; `None` when the version is unreadable.
pub fn parse_version(output: &str) -> Option<TmuxVersion> {
    let rest = output.trim().strip_prefix("tmux")?.trim_start();
    let rest = rest.strip_prefix("next-").unwrap_or(rest);
    let (major, rest) = split_number(rest)?;
    let (minor, _) = split_number(rest.strip_prefix('.')?)?;
    Some(TmuxVersion { major, minor })
}

/// Splits a leading run of ASCII digits off `s` and parses it.
fn split_number(s: &str) -> Option<(u32, &str)> {
    let end = s.find(|c: char| !c.is_ascii_digit()).unwrap_or(s.len());
    let (digits, rest) = s.split_at(end);
    Some((digits.parse().ok()?, rest))
}

#[cfg(test)]
mod tests {
    use super::*;
    use proptest::prelude::*;

    fn v(major: u32, minor: u32) -> Option<TmuxVersion> {
        Some(TmuxVersion { major, minor })
    }

    #[test]
    fn parses_known_formats() {
        assert_eq!(parse_version("tmux 3.5a"), v(3, 5));
        assert_eq!(parse_version("tmux 3.2"), v(3, 2));
        assert_eq!(parse_version("tmux next-3.6"), v(3, 6));
        assert_eq!(parse_version("tmux 2.9a"), v(2, 9));
    }

    #[test]
    fn unreadable_versions_are_none() {
        assert_eq!(parse_version("tmux master"), None);
        assert_eq!(parse_version("tmux openbsd-7.6"), None);
        assert_eq!(parse_version(""), None);
    }

    #[test]
    fn versions_compare() {
        assert!(TmuxVersion { major: 3, minor: 1 } < MIN_VERSION);
        assert!(
            TmuxVersion {
                major: 3,
                minor: 10
            } > TmuxVersion { major: 3, minor: 2 }
        );
    }

    proptest! {
        #[test]
        fn never_panics(s in any::<String>()) {
            let _ = parse_version(&s);
        }
    }
}
