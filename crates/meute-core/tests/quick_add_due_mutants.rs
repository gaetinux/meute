//! Boundary tests for due-date parsing, added after a cargo-mutants run.

use jiff::Zoned;
use meute_core::quick_add::parse_due;
use meute_core::task::Due;

#[expect(
    clippy::unwrap_used,
    reason = "shared test helper, not itself a #[test] function"
)]
fn now() -> Zoned {
    "2026-10-14T10:30[Europe/Paris]".parse().unwrap()
}

#[expect(
    clippy::unwrap_used,
    reason = "shared test helper, not itself a #[test] function"
)]
fn date(s: &str) -> Due {
    Due::Date(s.parse().unwrap())
}

#[expect(
    clippy::unwrap_used,
    reason = "shared test helper, not itself a #[test] function"
)]
fn at(s: &str) -> Due {
    Due::At(s.parse::<Zoned>().unwrap().timestamp())
}

#[test]
fn every_weekday_name_is_recognised() {
    // 2026-10-14 is a Wednesday.
    let n = now();
    for (name, day) in [
        ("lun", "2026-10-19"),
        ("mar", "2026-10-20"),
        ("mer", "2026-10-21"),
        ("jeu", "2026-10-15"),
        ("ven", "2026-10-16"),
        ("sam", "2026-10-17"),
        ("dim", "2026-10-18"),
    ] {
        assert_eq!(parse_due(name, &n), Some(date(day)), "{name}");
    }
}

#[test]
fn iso_datetime_requires_a_t_separator() {
    let n = now();
    assert_eq!(
        parse_due("2026-10-14T16:45", &n),
        Some(at("2026-10-14T16:45[Europe/Paris]"))
    );
    assert_eq!(parse_due("2026-10-14 16:45", &n), None);
}

#[test]
fn time_bounds_are_inclusive_upper_limits() {
    let n = now();
    assert_eq!(
        parse_due("lun-23h", &n),
        Some(at("2026-10-19T23:00[Europe/Paris]"))
    );
    assert_eq!(
        parse_due("lun-9h59", &n),
        Some(at("2026-10-19T09:59[Europe/Paris]"))
    );
    assert_eq!(parse_due("lun-24h", &n), None);
    assert_eq!(parse_due("lun-9h60", &n), None);
}

#[test]
fn time_digits_must_be_ascii_digits_not_a_sign() {
    let n = now();
    assert_eq!(parse_due("lun-+5h", &n), None);
    assert_eq!(parse_due("lun-9h+5", &n), None);
}

#[test]
fn minutes_delta_is_supported() {
    let n = now();
    assert_eq!(
        parse_due("+30m", &n),
        Some(at("2026-10-14T11:00[Europe/Paris]"))
    );
}

#[test]
fn delta_with_more_than_four_digits_is_rejected() {
    let n = now();
    assert!(parse_due("+9999h", &n).is_some());
    assert_eq!(parse_due("+10000h", &n), None);
}
