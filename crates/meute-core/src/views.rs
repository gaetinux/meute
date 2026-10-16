//! Pure view helpers: urgency buckets, display order and French due dates.

use crate::task::{Due, Priority, Task, TaskStatus};
use jiff::civil::{Date, Time};
use jiff::tz::TimeZone;
use jiff::{Timestamp, Zoned};
use std::cmp::Ordering;

const DAYS: [&str; 7] = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."];
const MONTHS: [&str; 12] = [
    "janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.",
    "déc.",
];

/// Urgency group a task is displayed in.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Bucket {
    /// Open and past its deadline.
    Overdue,
    /// Open and due today.
    Today,
    /// Open and due later.
    Upcoming,
    /// Open without a deadline.
    NoDue,
    /// Completed today.
    DoneToday,
}

impl Bucket {
    /// French label shown to the user.
    #[must_use]
    pub fn label(self) -> &'static str {
        match self {
            Self::Overdue => "En retard",
            Self::Today => "Aujourd'hui",
            Self::Upcoming => "À venir",
            Self::NoDue => "Sans échéance",
            Self::DoneToday => "Faites aujourd'hui",
        }
    }
}

/// Bucket of a task relative to `now`; `None` for a task done before today.
#[must_use]
pub fn bucket_of(task: &Task, now: &Zoned) -> Option<Bucket> {
    let today = now.date();
    match &task.status {
        TaskStatus::Done => {
            let done = task.completed_at?.to_zoned(now.time_zone().clone()).date();
            (done == today).then_some(Bucket::DoneToday)
        }
        TaskStatus::Todo
        | TaskStatus::InProgress
        | TaskStatus::Blocked { .. }
        | TaskStatus::Review => Some(match task.due {
            None => Bucket::NoDue,
            Some(Due::Date(d)) => match d.cmp(&today) {
                Ordering::Less => Bucket::Overdue,
                Ordering::Equal => Bucket::Today,
                Ordering::Greater => Bucket::Upcoming,
            },
            Some(Due::At(t)) => {
                if t < now.timestamp() {
                    Bucket::Overdue
                } else if t.to_zoned(now.time_zone().clone()).date() == today {
                    Bucket::Today
                } else {
                    Bucket::Upcoming
                }
            }
        }),
    }
}

/// Whether the task is open and past its deadline.
#[must_use]
pub fn is_overdue(task: &Task, now: &Zoned) -> bool {
    bucket_of(task, now) == Some(Bucket::Overdue)
}

/// Sort key of a deadline: a `Date` counts as 23:59:59 that day in `tz`.
fn due_key(due: Option<Due>, tz: &TimeZone) -> Option<Timestamp> {
    match due? {
        Due::At(t) => Some(t),
        Due::Date(d) => d
            .to_datetime(Time::constant(23, 59, 59, 0))
            .to_zoned(tz.clone())
            .ok()
            .map(|z| z.timestamp()),
    }
}

fn priority_rank(p: &Priority) -> u8 {
    match p {
        Priority::Urgent => 0,
        Priority::High => 1,
        Priority::Normal => 2,
        Priority::Low => 3,
    }
}

/// Sort by deadline (none last), then priority (urgent first), then id.
pub fn sort_for_display(tasks: &mut [Task], tz: &TimeZone) {
    tasks.sort_by(|a, b| {
        let (ka, kb) = (due_key(a.due, tz), due_key(b.due, tz));
        let by_due = match (ka, kb) {
            (Some(x), Some(y)) => x.cmp(&y),
            (Some(_), None) => Ordering::Less,
            (None, Some(_)) => Ordering::Greater,
            (None, None) => Ordering::Equal,
        };
        by_due
            .then_with(|| priority_rank(&a.priority).cmp(&priority_rank(&b.priority)))
            .then_with(|| a.id.0.cmp(&b.id.0))
    });
}

fn format_date(date: Date, now: &Zoned) -> String {
    let today = now.date();
    if date == today {
        return "aujourd'hui".to_owned();
    }
    if today.tomorrow().is_ok_and(|t| t == date) {
        return "demain".to_owned();
    }
    let day = DAYS[usize::from(date.weekday().to_monday_zero_offset() as u8)];
    let month = MONTHS[usize::from((date.month() - 1) as u8)];
    let mut out = format!("{day} {} {month}", date.day());
    if date.year() != today.year() {
        out.push_str(&format!(" {}", date.year()));
    }
    out
}

/// French display of a deadline, e.g. `demain`, `lun. 19 oct. 09:00`.
#[must_use]
pub fn format_due(due: &Due, now: &Zoned) -> String {
    match due {
        Due::Date(d) => format_date(*d, now),
        Due::At(t) => {
            let z = t.to_zoned(now.time_zone().clone());
            format!(
                "{} {:02}:{:02}",
                format_date(z.date(), now),
                z.hour(),
                z.minute()
            )
        }
    }
}

#[cfg(test)]
mod tests;
