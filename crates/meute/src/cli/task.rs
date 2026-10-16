//! `meute task …`
use super::task_edit;
use crate::app::App;
use crate::render;
use clap::{Args, Subcommand};
use meute_core::db::{ProjectFilter, TaskFilter};
use meute_core::quick_add::parse_quick_add;
use meute_core::task::{NewTask, StatusKind, TaskId};
use meute_core::views::sort_for_display;

#[derive(Subcommand)]
pub enum TaskCommand {
    /// Créer une tâche depuis la saisie rapide (`titre @projet !|!! >échéance`).
    Add {
        /// Saisie rapide.
        #[arg(required = true)]
        input: Vec<String>,
        /// Afficher le résultat analysé sans rien créer.
        #[arg(long)]
        dry_run: bool,
    },
    /// Lister les tâches.
    List(ListArgs),
    /// Afficher une tâche et ses notes.
    Show {
        /// Identifiant de la tâche.
        id: i64,
        /// Sortie JSON.
        #[arg(long)]
        json: bool,
    },
    #[command(flatten)]
    Edit(task_edit::EditCommand),
}

#[derive(Args)]
pub struct ListArgs {
    /// Inclure les tâches faites.
    #[arg(long)]
    all: bool,
    /// Restreindre à un projet.
    #[arg(long, conflicts_with = "floating")]
    project: Option<String>,
    /// Seulement les tâches volantes (sans projet).
    #[arg(long)]
    floating: bool,
    /// Restreindre à un statut (todo, in_progress, blocked, review, done).
    #[arg(long)]
    status: Option<String>,
    /// Sortie JSON.
    #[arg(long)]
    json: bool,
}

pub fn run(cmd: TaskCommand, app: &mut App) -> anyhow::Result<()> {
    match cmd {
        TaskCommand::Add { input, dry_run } => add(app, &input.join(" "), dry_run),
        TaskCommand::List(args) => list(app, &args),
        TaskCommand::Show { id, json } => show(app, TaskId(id), json),
        TaskCommand::Edit(cmd) => task_edit::run(cmd, app),
    }
}

fn add(app: &mut App, input: &str, dry_run: bool) -> anyhow::Result<()> {
    let parsed = parse_quick_add(input, &app.now)?;
    let project = parsed
        .project
        .as_deref()
        .map(|name| app.require_project(name))
        .transpose()?;
    if dry_run {
        println!("Analysé : {}", render::preview_line(&parsed, &app.now));
        return Ok(());
    }
    let new = NewTask {
        title: parsed.title,
        description: String::new(),
        priority: parsed.priority,
        due: parsed.due,
        project_id: project.map(|p| p.id),
    };
    let task = app.db.create_task(new, &app.actor)?;
    println!("Créée : {}", render::task_line(&task, &app.now));
    Ok(())
}

fn list(app: &mut App, args: &ListArgs) -> anyhow::Result<()> {
    let status = args
        .status
        .as_deref()
        .map(StatusKind::from_id)
        .transpose()?;
    let project = match (&args.project, args.floating) {
        (Some(name), _) => ProjectFilter::Project(app.require_project(name)?.id),
        (None, true) => ProjectFilter::Floating,
        (None, false) => ProjectFilter::Any,
    };
    let filter = TaskFilter {
        include_done: args.all,
        project,
        status,
    };
    let mut tasks = app.db.list_tasks(&filter)?;
    sort_for_display(&mut tasks, app.now.time_zone());
    if args.json {
        println!("{}", serde_json::to_string(&tasks)?);
    } else {
        for task in &tasks {
            println!("{}", render::task_line(task, &app.now));
        }
    }
    Ok(())
}

fn show(app: &mut App, id: TaskId, json: bool) -> anyhow::Result<()> {
    let task = app.db.get_task(id)?;
    let notes = app.db.notes(id)?;
    if json {
        let mut value = serde_json::to_value(&task)?;
        value["notes"] = serde_json::to_value(&notes)?;
        println!("{value}");
    } else {
        print!("{}", render::task_detail(&task, &notes, &app.now));
    }
    Ok(())
}
