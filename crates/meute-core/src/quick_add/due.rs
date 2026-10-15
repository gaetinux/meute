//! Due-date token parsing.

use crate::task::Due;
use jiff::civil::{Date, DateTime, Weekday};
use jiff::{ToSpan, Zoned};

/// Parses a due token (without the leading `>`) relative to `now`.
///
/// Accepted forms: `demain`, `ce-soir`, `lun`..`dim`, `lun-9h`, `lun-14h30`,
/// `+Nh`, `+Nm`, `+Nj`, `YYYY-MM-DD` and `YYYY-MM-DDTHH:MM`.
/// Returns `None` for anything else, including invalid dates and times.
pub fn parse_due(token: &str, now: &Zoned) -> Option<Due> {
    match parse_iso(token) {
        Some(Iso::Date(date)) => Some(Due::Date(date)),
        Some(Iso::DateTime(dt)) => zoned_at(dt, now).map(Due::At),
        None => parse_relative(&token.to_lowercase(), now),
    }
}

enum Iso {
    Date(Date),
    DateTime(DateTime),
}

/// Recognises the two ISO forms; `None` when the token is not valid ISO.
fn parse_iso(token: &str) -> Option<Iso> {
    let starts_like_date = token.as_bytes().get(4) == Some(&b'-');
    if !starts_like_date {
        return None;
    }
    match token.len() {
        10 => token.parse().ok().map(Iso::Date),
        16 if token.as_bytes().get(10) == Some(&b'T') => token.parse().ok().map(Iso::DateTime),
        _ => None,
    }
}

fn parse_relative(token: &str, now: &Zoned) -> Option<Due> {
    match token {
        "demain" => now.date().tomorrow().ok().map(Due::Date),
        "ce-soir" => zoned_at(now.date().at(18, 0, 0, 0), now).map(Due::At),
        _ => {
            if let Some(delta) = token.strip_prefix('+') {
                return parse_delta(delta, now);
            }
            match token.split_once('-') {
                Some((day, time)) => {
                    let (hour, minute) = parse_time(time)?;
                    let date = next_weekday(day, now)?;
                    zoned_at(date.at(hour, minute, 0, 0), now).map(Due::At)
                }
                None => next_weekday(token, now).map(Due::Date),
            }
        }
    }
}

fn zoned_at(dt: DateTime, now: &Zoned) -> Option<jiff::Timestamp> {
    dt.to_zoned(now.time_zone().clone())
        .ok()
        .map(|z| z.timestamp())
}

/// The first day named `name` strictly after today.
fn next_weekday(name: &str, now: &Zoned) -> Option<Date> {
    let weekday = match name {
        "lun" => Weekday::Monday,
        "mar" => Weekday::Tuesday,
        "mer" => Weekday::Wednesday,
        "jeu" => Weekday::Thursday,
        "ven" => Weekday::Friday,
        "sam" => Weekday::Saturday,
        "dim" => Weekday::Sunday,
        _ => return None,
    };
    now.date().nth_weekday(1, weekday).ok()
}

/// Parses `9h` or `14h30` into (hour, minute).
fn parse_time(time: &str) -> Option<(i8, i8)> {
    let (hour, minute) = time.split_once('h')?;
    let hour = digits(hour, 1..=2)?;
    let minute = if minute.is_empty() {
        0
    } else {
        digits(minute, 2..=2)?
    };
    if hour > 23 || minute > 59 {
        return None;
    }
    Some((i8::try_from(hour).ok()?, i8::try_from(minute).ok()?))
}

/// Parses `Nh`, `Nm` or `Nj` (N in 1..=9999) and adds it to `now`.
fn parse_delta(delta: &str, now: &Zoned) -> Option<Due> {
    let unit = delta.chars().last()?;
    let count = i64::from(digits(delta.strip_suffix(unit)?, 1..=4)?);
    if count == 0 {
        return None;
    }
    let span = match unit {
        'h' => count.hours(),
        'm' => count.minutes(),
        'j' => count.days(),
        _ => return None,
    };
    now.checked_add(span).ok().map(|z| Due::At(z.timestamp()))
}

/// Parses an all-ASCII-digit string whose length is within `len`.
fn digits(s: &str, len: std::ops::RangeInclusive<usize>) -> Option<u32> {
    (len.contains(&s.len()) && s.bytes().all(|b| b.is_ascii_digit())).then(|| s.parse().ok())?
}
