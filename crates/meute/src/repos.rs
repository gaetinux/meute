//! Repository scanning.
use crate::app::App;
use anyhow::Context;
use meute_core::repo::{NewRepo, Repo};
use meute_git::{DEFAULT_DEPTH, discover, expand_home};
use std::path::PathBuf;

/// Scans the configured roots and registers what was found.
pub fn scan(app: &mut App) -> anyhow::Result<Vec<Repo>> {
    let home = std::env::var_os("HOME").map(PathBuf::from);
    let roots: Vec<PathBuf> = app
        .config
        .repos
        .roots
        .iter()
        .map(|root| expand_home(root, home.as_deref()))
        .collect();
    let found: Vec<NewRepo> = discover(&roots, DEFAULT_DEPTH)
        .into_iter()
        .map(|repo| NewRepo {
            path: repo.path,
            name: repo.name,
            kind: repo.kind.map(|k| k.id().to_owned()),
        })
        .collect();
    app.db
        .sync_repos(&found)
        .context("enregistrement des dépôts")
}
