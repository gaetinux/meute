//! Fixed-width storage format of timestamps, so text order is time order.

use jiff::Timestamp;

/// Formats a timestamp as `YYYY-MM-DDTHH:MM:SS.ffffffZ` (UTC, microseconds).
#[must_use]
pub fn to_db(ts: Timestamp) -> String {
    ts.strftime("%Y-%m-%dT%H:%M:%S.%6fZ").to_string()
}

/// Parses a stored timestamp (the fixed format, or any RFC 3339 text).
///
/// # Errors
/// Returns the parser error when `text` is not a valid timestamp.
pub fn from_db(text: &str) -> Result<Timestamp, jiff::Error> {
    text.parse()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ts(text: &str) -> Timestamp {
        text.parse().unwrap()
    }

    #[test]
    fn stored_strings_sort_like_the_instants() {
        let ordered = [
            ts("2026-10-14T08:30:00Z"),
            ts("2026-10-14T08:30:00.5Z"),
            ts("2026-10-14T08:30:01Z"),
            ts("2026-10-14T08:30:01.000001Z"),
        ];
        let strings: Vec<String> = ordered.iter().map(|t| to_db(*t)).collect();
        let mut sorted = strings.clone();
        sorted.sort();
        assert_eq!(strings, sorted);
        assert!(strings.iter().all(|s| s.len() == 27), "{strings:?}");
    }

    #[test]
    fn round_trips_at_microsecond_precision() {
        let t = ts("2026-10-14T08:30:00.123456Z");
        assert_eq!(to_db(t), "2026-10-14T08:30:00.123456Z");
        assert_eq!(from_db(&to_db(t)).unwrap(), t);
    }
}
