//! `meute project …`
use crate::app::App;
use clap::Subcommand;

#[derive(Subcommand)]
pub enum ProjectCommand {
    /// Créer un projet.
    Add {
        /// Nom du projet.
        name: String,
        /// Description du projet.
        #[arg(long, default_value = "")]
        description: String,
    },
    /// Lister les projets.
    List {
        /// Sortie JSON.
        #[arg(long)]
        json: bool,
    },
}

pub fn run(cmd: ProjectCommand, app: &mut App) -> anyhow::Result<()> {
    match cmd {
        ProjectCommand::Add { name, description } => {
            let project = app.db.create_project(&name, &description)?;
            println!("Projet créé : {}", project.name);
        }
        ProjectCommand::List { json } => {
            let projects = app.db.list_projects()?;
            if json {
                println!("{}", serde_json::to_string(&projects)?);
            } else {
                for project in projects {
                    println!("{}", project.name);
                }
            }
        }
    }
    Ok(())
}
