use super::*;
use crate::CoreError;
use crate::task::{Due, Priority};
use proptest::prelude::*;

fn now() -> jiff::Zoned {
    "2026-10-14T10:30[Europe/Paris]".parse().unwrap()
}
fn date(s: &str) -> Due {
    Due::Date(s.parse().unwrap())
}
fn at(s: &str) -> Due {
    Due::At(s.parse::<jiff::Zoned>().unwrap().timestamp())
}

#[test]
fn full_syntax_from_spec() {
    let q = parse_quick_add("Relire la PR @meute ! >demain", &now()).unwrap();
    assert_eq!(q.title, "Relire la PR");
    assert_eq!(q.project.as_deref(), Some("meute"));
    assert_eq!(q.priority, Priority::High);
    assert_eq!(q.due, Some(date("2026-10-15")));
}

#[test]
fn due_forms_from_spec() {
    let n = now();
    assert_eq!(
        parse_due("ce-soir", &n),
        Some(at("2026-10-14T18:00[Europe/Paris]"))
    );
    assert_eq!(parse_due("lun", &n), Some(date("2026-10-19")));
    assert_eq!(parse_due("mer", &n), Some(date("2026-10-21"))); // strictement après aujourd'hui
    assert_eq!(
        parse_due("lun-9h", &n),
        Some(at("2026-10-19T09:00[Europe/Paris]"))
    );
    assert_eq!(
        parse_due("ven-14h30", &n),
        Some(at("2026-10-16T14:30[Europe/Paris]"))
    );
    assert_eq!(
        parse_due("+2h", &n),
        Some(at("2026-10-14T12:30[Europe/Paris]"))
    );
    assert_eq!(
        parse_due("+3j", &n),
        Some(at("2026-10-17T10:30[Europe/Paris]"))
    );
    assert_eq!(parse_due("2026-10-20", &n), Some(date("2026-10-20")));
    assert_eq!(
        parse_due("2026-10-20T14:00", &n),
        Some(at("2026-10-20T14:00[Europe/Paris]"))
    );
}

#[test]
fn invalid_due_tokens_stay_in_title() {
    let q = parse_quick_add("Payer >2026-02-30 >lun-25h >+0h >bientot", &now()).unwrap();
    assert_eq!(q.title, "Payer >2026-02-30 >lun-25h >+0h >bientot");
    assert_eq!(q.due, None);
}

#[test]
fn punctuation_and_emails_are_not_tokens() {
    let q = parse_quick_add("Corriger le bug! écrire à a@b.fr", &now()).unwrap();
    assert_eq!(q.title, "Corriger le bug! écrire à a@b.fr");
    assert_eq!((q.project, q.priority), (None, Priority::Normal));
}

#[test]
fn last_token_wins_and_triple_bang_stays() {
    let q = parse_quick_add("x @a @b ! !! !!!", &now()).unwrap();
    assert_eq!(q.title, "x !!!");
    assert_eq!(q.project.as_deref(), Some("b"));
    assert_eq!(q.priority, Priority::Urgent);
}

#[test]
fn only_tokens_is_an_error() {
    assert!(matches!(
        parse_quick_add("@meute !! >demain", &now()),
        Err(CoreError::Invalid(_))
    ));
    assert!(matches!(
        parse_quick_add("   ", &now()),
        Err(CoreError::Invalid(_))
    ));
}

proptest! {
    #[test]
    fn never_panics(input in ".{0,200}") {
        let _ = parse_quick_add(&input, &now());
        let _ = parse_due(&input, &now());
    }

    #[test]
    fn ok_title_is_non_empty_trimmed_single_spaced(input in "[a-zA-Z0-9@!>+:\\- ]{0,80}") {
        if let Ok(q) = parse_quick_add(&input, &now()) {
            prop_assert!(!q.title.is_empty());
            prop_assert_eq!(q.title.trim(), q.title.as_str());
            prop_assert!(!q.title.contains("  "));
        }
    }

    #[test]
    fn plain_words_are_kept_verbatim(words in proptest::collection::vec("[a-zéè]{1,10}", 1..8)) {
        let input = words.join(" ");
        let q = parse_quick_add(&input, &now()).unwrap();
        prop_assert_eq!(q.title, input);
        prop_assert_eq!(q.priority, Priority::Normal);
    }
}
