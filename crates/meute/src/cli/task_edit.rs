//! `meute task edit|status|note|rm`
use crate::app::App;
use crate::render;
use anyhow::{anyhow, bail};
use clap::{Args, Subcommand};
use meute_core::project::ProjectId;
use meute_core::quick_add::parse_due;
use meute_core::task::{Priority, TaskId, TaskPatch, TaskStatus};
use std::io::{BufRead, IsTerminal, Write};

/// Token that clears an optional field (`--due none`, `--project none`).
const CLEAR: &str = "none";

#[derive(Subcommand)]
pub enum EditCommand {
    /// Modifier une tâche.
    Edit(EditArgs),
    /// Changer le statut d'une tâche.
    Status {
        /// Identifiant de la tâche.
        id: i64,
        /// Nouveau statut (todo, in_progress, blocked, review, done).
        status: String,
        /// Raison (obligatoire pour `blocked`).
        #[arg(long)]
        reason: Option<String>,
        /// Version attendue de la tâche.
        #[arg(long)]
        expected_version: Option<u32>,
    },
    /// Ajouter une note à une tâche.
    Note {
        /// Identifiant de la tâche.
        id: i64,
        /// Texte de la note.
        #[arg(required = true)]
        text: Vec<String>,
    },
    /// Supprimer une tâche.
    Rm {
        /// Identifiant de la tâche.
        id: i64,
        /// Ne pas demander de confirmation.
        #[arg(long)]
        yes: bool,
        /// Version attendue de la tâche.
        #[arg(long)]
        expected_version: Option<u32>,
    },
}

#[derive(Args)]
pub struct EditArgs {
    /// Identifiant de la tâche.
    id: i64,
    /// Nouveau titre.
    #[arg(long)]
    title: Option<String>,
    /// Nouvelle description.
    #[arg(long)]
    description: Option<String>,
    /// Nouvelle priorité (urgent, high, normal, low).
    #[arg(long)]
    priority: Option<String>,
    /// Nouvelle échéance (jeton de saisie rapide) ou `none`.
    #[arg(long)]
    due: Option<String>,
    /// Nouveau projet ou `none`.
    #[arg(long)]
    project: Option<String>,
    /// Version attendue de la tâche.
    #[arg(long)]
    expected_version: Option<u32>,
}

pub fn run(cmd: EditCommand, app: &mut App) -> anyhow::Result<()> {
    match cmd {
        EditCommand::Edit(args) => edit(app, &args),
        EditCommand::Status {
            id,
            status,
            reason,
            expected_version,
        } => {
            let patch = TaskPatch {
                status: Some(TaskStatus::from_id(&status, reason.as_deref())?),
                ..TaskPatch::default()
            };
            apply(app, TaskId(id), expected_version, patch)
        }
        EditCommand::Note { id, text } => {
            app.db.add_note(TaskId(id), &text.join(" "), &app.actor)?;
            println!("Note ajoutée à #{id}");
            Ok(())
        }
        EditCommand::Rm {
            id,
            yes,
            expected_version,
        } => remove(app, TaskId(id), yes, expected_version),
    }
}

fn edit(app: &mut App, args: &EditArgs) -> anyhow::Result<()> {
    let due = match args.due.as_deref() {
        None => None,
        Some(CLEAR) => Some(None),
        Some(token) => Some(Some(
            parse_due(token, &app.now).ok_or_else(|| anyhow!("échéance invalide : {token}"))?,
        )),
    };
    let project_id: Option<Option<ProjectId>> = match args.project.as_deref() {
        None => None,
        Some(CLEAR) => Some(None),
        Some(name) => Some(Some(app.require_project(name)?.id)),
    };
    let patch = TaskPatch {
        title: args.title.clone(),
        description: args.description.clone(),
        priority: args
            .priority
            .as_deref()
            .map(Priority::from_id)
            .transpose()?,
        due,
        project_id,
        status: None,
    };
    apply(app, TaskId(args.id), args.expected_version, patch)
}

/// Applies a patch against the expected version (the freshly read one by default).
fn apply(
    app: &mut App,
    id: TaskId,
    expected_version: Option<u32>,
    patch: TaskPatch,
) -> anyhow::Result<()> {
    let version = match expected_version {
        Some(version) => version,
        None => app.db.get_task(id)?.version,
    };
    let task = app.db.update_task(id, version, patch, &app.actor)?;
    println!("{}", render::task_line(&task, &app.now));
    Ok(())
}

fn remove(
    app: &mut App,
    id: TaskId,
    yes: bool,
    expected_version: Option<u32>,
) -> anyhow::Result<()> {
    let task = app.db.get_task(id)?;
    if !yes {
        confirm(&format!("Supprimer {id} « {} » ? [o/N] ", task.title))?;
    }
    app.db
        .delete_task(id, expected_version.unwrap_or(task.version), &app.actor)?;
    println!("Supprimée : {id}");
    Ok(())
}

/// Asks for a yes/no answer on a terminal; refuses off-terminal.
fn confirm(prompt: &str) -> anyhow::Result<()> {
    let stdin = std::io::stdin();
    if !stdin.is_terminal() {
        bail!("confirmation requise : relancez avec --yes");
    }
    print!("{prompt}");
    std::io::stdout().flush()?;
    let mut answer = String::new();
    stdin.lock().read_line(&mut answer)?;
    match answer.trim().to_lowercase().as_str() {
        "o" | "oui" => Ok(()),
        _ => bail!("suppression annulée"),
    }
}
