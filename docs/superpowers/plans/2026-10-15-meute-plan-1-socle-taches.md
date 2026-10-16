> **Plan Rust obsolète, conservé pour l'historique. Ne pas l'exécuter.** L'implémentation de référence se trouve sous le tag `rust-plan-1` ; ce plan est remplacé par le [plan 1 Python](2026-10-16-meute-plan-1-python-socle-taches.md).

# meute — Plan 1 : socle et tâches — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Objectif :** créer le workspace Rust de meute et livrer une gestion de tâches et de projets complète en CLI, adossée à SQLite. Cette gestion comprend la saisie rapide, le contrôle de concurrence, l'historique et les notes.

**Architecture :** toute la logique métier vit dans la crate bibliothèque `meute-core` : modèle, analyse de la saisie rapide, accès SQLite et migrations, configuration et chemins XDG. Le binaire `meute` n'est qu'une couche `clap` qui appelle `meute-core` et met en forme la sortie, en texte ou en `--json`. Le code est entièrement synchrone.

**Stack technique :**
- Rust stable (édition 2024) ;
- `rusqlite` (`bundled`) et `rusqlite_migration` ;
- `serde`, `serde_json`, `toml`, `toml_edit` ;
- `jiff` (fonctionnalité `serde`) ;
- `thiserror`, `directories`, `clap` (fonctionnalité `derive`), `anyhow` ;
- tests : `tempfile`, `assert_cmd`, `predicates`, `proptest`, `insta`, `cargo-nextest`, `cargo-insta` ;
- qualité : `cargo-deny`, `cargo-machete`, `cargo-mutants`, linker `mold` (via `clang`).

**Guide de référence :** `docs/dev/developpement-assiste-par-ia.md` (pratiques de développement assisté par IA). Il fait partie des exigences : chaque tâche doit le respecter.

**Spécification :** `docs/superpowers/specs/2026-10-15-meute-design.md` (et la feuille de route `docs/superpowers/plans/2026-10-15-meute-v1-roadmap.md`).

## Contraintes globales

**Langage et code**
- Rust stable, `edition = "2024"`, `rust-version = "1.85"`. Les champs `[workspace.package]` sont partagés par toutes les crates.
- Licence `MIT OR Apache-2.0`, avec les fichiers `LICENSE-MIT` et `LICENSE-APACHE` à la racine.
- Lints : ceux du tableau du § 3 du guide, sans exception, déclarés dans `[workspace.lints]`. Un `clippy.toml` contient `allow-unwrap-in-tests = true` et `allow-expect-in-tests = true`. Dans `meute-core`, les attributs de crate sont `#![warn(missing_docs)]` et `#![deny(clippy::print_stdout, clippy::print_stderr)]`. Toute exception passe par `#[expect(lint, reason = "…")]` et est mentionnée dans la PR (spécification § 16, guide § 3).
- Pas de `_ =>` sur nos propres enums, ni de `#[non_exhaustive]` sur des types internes au workspace (guide § 2).
- Tous les éléments publics de `meute-core` sont documentés par des `///`.
- Fichiers de moins de 300 lignes, avec un maximum indicatif de 400. Au-delà, on découpe en sous-modules (guide § 6).
- En dehors des chemins critiques, on préfère des données possédées et `.clone()` à des signatures avec plusieurs durées de vie (guide § 6).
- Dépendances ajoutées uniquement avec `cargo add`. La documentation de la version réellement installée est consultée (context7, docs.rs) avant d'utiliser une API. `Cargo.lock` est commité (guide § 7).
- Erreurs typées avec `thiserror` dans `meute-core`, `anyhow` dans le binaire `meute` (§ 16).
- Code synchrone, sans `tokio` dans ce plan (§ 4.3).
- Identifiants et commentaires de code en anglais. Textes affichés à l'utilisateur en français pour la V1.
- Toute règle métier vit dans `meute-core`. Le binaire n'appelle que ses fonctions publiques (§ 4.3).

**Données et fichiers**
- Chemins XDG via `directories::ProjectDirs::from("", "", "meute")` :
  - configuration : `~/.config/meute/config.toml` ;
  - base : `~/.local/share/meute/meute.db` ;
  - état : `~/.local/state/meute/`.

  Les variables `XDG_CONFIG_HOME`, `XDG_DATA_HOME` et `XDG_STATE_HOME` sont respectées, ce qui permet d'isoler les tests (§ 13).
- Une configuration existante n'est **jamais** écrasée (§ 13).
- SQLite : `journal_mode=WAL`, `foreign_keys=ON`, `busy_timeout` de 5000 ms pour la CLI. Avant chaque migration d'une base existante, une sauvegarde `meute.db.bak-<version actuelle>` est créée (§ 13).
- Les horodatages sont stockés en texte RFC 3339 UTC (`jiff::Timestamp`), et les dates sans heure en `YYYY-MM-DD`.

**Qualité et workflow**
- **TDD systématique** : pour chaque comportement, on écrit le test, on le voit échouer pour la bonne raison, on écrit le code minimal qui le fait passer, puis on refactorise avec les tests au vert. Un correctif de bug commence toujours par un test qui reproduit le bug.
- On ne modifie, ne supprime ni ne désactive (`#[ignore]`) jamais un test existant pour le faire passer. Si un test semble faux, on s'arrête et on le signale (guide § 1).
- Les instantanés `insta` sont relus ligne par ligne par rapport à la spécification avant d'être acceptés avec `cargo insta review`. On n'utilise jamais `cargo insta accept` à l'aveugle (guide § 1).
- Chaque tâche se termine par la vérification complète du § 9 du guide : `cargo fmt --check && cargo clippy --workspace --all-targets -- -D warnings && cargo nextest run --workspace && cargo deny check && cargo machete` (spécification § 17). Les hooks du Task 2 l'appliquent automatiquement à partir du Task 3.
- Workflow Git :
  - une branche `feat/plan-1-socle-taches` créée depuis `main` ;
  - un commit par tâche ;
  - à la fin, une PR assignée à `gaetinux`, qui la merge lui-même ;
  - jamais de push sur `main`.

## Points de vigilance

1. **Ponctuation et adresses e-mail dans la saisie rapide.** `Corriger le bug!` et `écrire à a@b.fr` gardent `bug!` et `a@b.fr` dans le titre. Seuls les jetons séparés par des espaces et *commençant* par `@`, `!` ou `>` sont interprétés. Test au Task 5.
2. **Saisie réduite à des jetons.** `@meute !! >demain` provoque une erreur « titre vide », et rien n'est créé. Test au Task 5.
3. **Deux écritures concurrentes avec la même version.** La seconde reçoit `Conflict` avec l'état courant, aucun événement d'historique n'est écrit et la version n'est pas incrémentée deux fois. Test au Task 8.
4. **Projet inconnu dans la saisie rapide.** `meute task add "x @inconnu"` échoue avec la liste des projets connus, et rien n'est créé : on ne crée jamais de projet sur une faute de frappe. Test au Task 10.
5. **Configuration existante modifiée à la main.** `config set` préserve les commentaires et les clés inconnues. Un TOML invalide provoque une erreur qui cite le chemin et la ligne, et ne remplace jamais le fichier par les valeurs par défaut. Test au Task 3.

---

### Task 1 : workspace, lints, outillage, CI et règles du projet

**Fichiers :**
- Créer : `Cargo.toml` (workspace), `Cargo.lock`, `rust-toolchain.toml`, `clippy.toml`, `rustfmt.toml` (vide), `deny.toml`, `.cargo/config.toml`, `LICENSE-MIT`, `LICENSE-APACHE`, `CLAUDE.md`, `.github/workflows/ci.yml`
- Créer : `crates/meute-core/Cargo.toml`, `crates/meute-core/src/lib.rs`
- Créer : `crates/meute/Cargo.toml`, `crates/meute/src/main.rs`
- Test : `crates/meute/tests/cli_basics.rs`, `crates/meute-core/tests/lint_guard.rs`

**Interfaces :**
- Produit :
  - la crate bibliothèque `meute_core`, avec les attributs de crate du guide § 3 ;
  - le binaire `meute` avec `clap`, qui expose `meute --version` (affiche `meute <version>`) ;
  - la vérification complète (guide § 9), qui passe à vide.

- [ ] **Étape 1 : vérifier la chaîne d'outils.**
  - Installer ce qui manque :
    - Rust : `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y`, puis `source ~/.cargo/env` ;
    - outils cargo : `cargo install cargo-nextest cargo-insta cargo-deny cargo-machete cargo-mutants --locked` ;
    - linker : `sudo apt install mold clang`. Cette commande demande des droits administrateur : si elle échoue, s'arrêter et demander à l'utilisateur de la lancer lui-même.
  - Vérification : `cargo --version && cargo nextest --version && cargo insta --version && cargo deny --version && cargo machete --version && cargo mutants --version && mold --version` affiche toutes les versions.

- [ ] **Étape 2 : écrire les tests qui doivent échouer.**

```rust
// crates/meute/tests/cli_basics.rs
use assert_cmd::Command;
use predicates::str::starts_with;

#[test]
fn version_flag_prints_name_and_version() {
    Command::cargo_bin("meute").unwrap()
        .arg("--version")
        .assert()
        .success()
        .stdout(starts_with(format!("meute {}", env!("CARGO_PKG_VERSION"))));
}
```

```rust
// crates/meute-core/tests/lint_guard.rs
// Garde-fou : les lints exigés par le guide (§ 3) sont bien déclarés dans le workspace.
#[test]
fn workspace_declares_required_lints() {
    let manifest = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/../../Cargo.toml")).unwrap();
    let doc: toml::Table = manifest.parse().unwrap();
    let lints = &doc["workspace"]["lints"];
    assert_eq!(lints["rust"]["unsafe_code"].as_str(), Some("forbid"));
    for name in ["unwrap_used", "expect_used", "todo", "unimplemented", "dbg_macro",
                 "allow_attributes_without_reason", "wildcard_enum_match_arm"] {
        assert_eq!(lints["clippy"][name].as_str(), Some("deny"), "clippy::{name}");
    }
}
```

  `toml` est ajouté comme dépendance de développement de `meute-core`, avec `cargo add --dev toml`.

- [ ] **Étape 3 : lancer les tests et constater l'échec.**
  Commande : `cargo nextest run`.
  Attendu : échec. Au tout premier passage, le workspace n'existe pas encore : créer d'abord les fichiers `Cargo.toml` minimaux, *sans* lints ni binaire, puis relancer pour voir les deux tests échouer sur leurs assertions.

- [ ] **Étape 4 : compléter le workspace pour faire passer les tests.**
  - Workspace `members = ["crates/*"]`, `resolver = "3"`.
  - `[workspace.package]` : `version = "0.1.0"`, `edition = "2024"`, `rust-version = "1.85"`, `license = "MIT OR Apache-2.0"`, `repository = "https://github.com/gaetinux/meute"`.
  - `[workspace.lints]` : exactement le tableau du guide § 3. Chaque crate déclare `[lints] workspace = true`.
  - `meute-core/src/lib.rs` : `#![warn(missing_docs)]`, `#![deny(clippy::print_stdout, clippy::print_stderr)]`, et une doc de crate `//!` d'une phrase.
  - `rust-toolchain.toml` : `channel = "stable"`, avec `components = ["rustfmt", "clippy"]`.
  - `.cargo/config.toml` : pour `[target.x86_64-unknown-linux-gnu]`, `linker = "clang"` et `rustflags = ["-C", "link-arg=-fuse-ld=mold"]`.
  - `deny.toml` (créé avec `cargo deny init`, puis ajusté) :
    - `[licenses] allow = ["MIT", "Apache-2.0", "Apache-2.0 WITH LLVM-exception", "BSD-2-Clause", "BSD-3-Clause", "ISC", "Unicode-3.0", "Zlib"]`. Si une dépendance exige une autre licence, on l'ajoute avec un commentaire qui justifie le besoin, et on le mentionne dans la PR ;
    - `[advisories]` : on refuse les vulnérabilités connues ;
    - `[sources]` : uniquement crates.io.
  - `main.rs` : un `#[derive(Parser)]` avec `#[command(name = "meute", version)]`, sans sous-commande pour l'instant.
  - `CLAUDE.md` : court, pas plus de 60 lignes. Il contient, dans cet ordre :
    1. une phrase de présentation du projet, avec un lien vers la spécification et vers la feuille de route ;
    2. **la règle du TDD systématique et l'interdiction de modifier un test pour le faire passer** ;
    3. la commande de vérification complète du guide § 9 ;
    4. un résumé en une ligne de chaque section du guide, avec un lien vers `docs/dev/developpement-assiste-par-ia.md` ;
    5. la règle de langue : code et commentaires en anglais, interface en français ;
    6. le workflow Git : une branche, une PR assignée à gaetinux, jamais de push sur `main`, pas de lien de session dans les commits.
  - `ci.yml` : sur `pull_request` et sur `push` vers `main`, trois jobs :
    - `check` : `rui314/setup-mold@v1`, puis `cargo fmt --check`, `cargo clippy --workspace --all-targets -- -D warnings` et `cargo nextest run --workspace`. nextest est installé avec `taiki-e/install-action@nextest` ;
    - `deny` : `EmbarkStudios/cargo-deny-action@v2` ;
    - `machete` : `bnjbvr/cargo-machete@main`.

- [ ] **Étape 5 : faire la vérification complète (guide § 9).**
  Attendu : `2 tests run: 2 passed`, aucun avertissement, `cargo deny check` sans erreur et `cargo machete` sans dépendance inutilisée.

- [ ] **Étape 6 : commiter.** `git commit -m "chore: workspace Rust, lints, outillage, CI et règles du projet"`

---

### Task 2 : hooks Claude Code du dépôt

**Fichiers :**
- Créer : `.claude/settings.json`, `.claude/hooks/rust-check.sh`, `.claude/hooks/verify.sh`
- Test : `.claude/hooks/tests/run.sh`, avec ses données de test dans `.claude/hooks/tests/fixtures/`

**Interfaces :**
- Produit : les deux hooks décrits au § 5 du guide. Leur comportement exact est le suivant.
  - **`rust-check.sh`** : il lit le JSON du hook sur stdin et prend `tool_input.file_path` (avec `jq`).
    - Si le chemin ne se termine pas par `.rs`, il sort avec le code 0, sans rien afficher.
    - Sinon, il lance `rustfmt --edition 2024 <fichier>`, puis `cargo check --workspace --all-targets --message-format=short`. Le dossier de travail est la racine du dépôt (`$CLAUDE_PROJECT_DIR`, ou par défaut le dossier courant).
    - Si la vérification échoue, il écrit sur stderr `cargo check a échoué :` suivi des erreurs, en se limitant aux 60 premières lignes, puis sort avec le code **2**. Sinon, il sort avec le code 0.
  - **`verify.sh`** : il lit le JSON sur stdin.
    - Si `git status --porcelain -- '*.rs' 'Cargo.toml' '*/Cargo.toml' 'Cargo.lock'` est vide, il sort avec le code 0.
    - Sinon, il lance `cargo clippy --workspace --all-targets -- -D warnings`, puis `cargo nextest run --workspace --failure-output final --hide-progress-bar`.
    - Si tout passe, il sort avec le code 0.
    - En cas d'échec, si `stop_hook_active` vaut `true`, il écrit `vérification toujours en échec — signale-le explicitement dans ton rapport` sur stderr et sort avec le code 0, pour éviter une boucle infinie.
    - En cas d'échec sinon, il écrit `vérification en échec, corrige avant de terminer :` suivi des 60 dernières lignes de sortie, et sort avec le code **2**.
  - **`.claude/settings.json`** :
    - `hooks.PostToolUse` avec `matcher: "Edit|Write|MultiEdit"`, qui appelle `"$CLAUDE_PROJECT_DIR"/.claude/hooks/rust-check.sh` ;
    - `hooks.Stop` et `hooks.SubagentStop`, qui appellent `"$CLAUDE_PROJECT_DIR"/.claude/hooks/verify.sh`.

    Les deux scripts sont exécutables et commencent par `#!/usr/bin/env bash` et `set -uo pipefail`.

- [ ] **Étape 1 : écrire le test qui doit échouer.** Le script `.claude/hooks/tests/run.sh` travaille dans un dossier temporaire. Il copie le contenu de `fixtures/` : une petite crate `fixture` avec un `src/lib.rs` valide, un `Cargo.toml` et un dépôt Git initialisé, avec un premier commit. Entre deux cas, il remet l'arbre dans son état initial (`git checkout -- . && git clean -fdq -e target`). Il vérifie ensuite chaque cas et affiche `OK <cas>` ou `ÉCHEC <cas>`. Il sort avec un code différent de 0 si au moins un cas échoue.

| Cas | Entrée | Attendu |
|---|---|---|
| `non_rust_ignored` | `{"tool_input":{"file_path":"README.md"}}` vers `rust-check.sh` | code 0, stderr vide |
| `rust_ok` | `lib.rs` valide | code 0 |
| `rust_error_blocks` | `lib.rs` contenant `fn x() -> u8 { "a" }` | code 2, stderr contenant `cargo check a échoué` et `mismatched types` |
| `verify_clean_tree` | arbre Git sans modification, avec un faux `cargo` placé en tête du `PATH` qui crée un fichier témoin | code 0, et le fichier témoin n'existe pas (cargo n'a pas été lancé) |
| `verify_failing_blocks` | test en échec ajouté à la crate de test, `{"stop_hook_active":false}` | code 2, stderr contenant `corrige avant de terminer` |
| `verify_loop_guard` | même arbre, `{"stop_hook_active":true}` | code 0, stderr contenant `signale-le explicitement` |

- [ ] **Étape 2 : lancer le test et constater l'échec.**
  Commande : `bash .claude/hooks/tests/run.sh`.
  Attendu : `ÉCHEC` sur tous les cas, puisque les scripts n'existent pas encore.

- [ ] **Étape 3 : écrire `rust-check.sh`, `verify.sh` et `.claude/settings.json` selon les interfaces ci-dessus.**

- [ ] **Étape 4 : lancer le test et vérifier qu'il passe.**
  Commande : `bash .claude/hooks/tests/run.sh`.
  Attendu : six lignes `OK` et le code de sortie 0.

- [ ] **Étape 5 : brancher le test dans la CI.** Ajouter au job `check` de `ci.yml` une étape `bash .claude/hooks/tests/run.sh`. Puis faire la vérification complète (guide § 9).

- [ ] **Étape 6 : commiter.** `git commit -m "chore: hooks Claude Code de vérification Rust"`

**Note pour l'exécutant :** les hooks ne s'activent qu'au chargement de la configuration du projet par Claude Code. À partir du Task 3, chaque sous-agent lancé dans le dépôt bénéficie de `cargo check` après chaque édition, et de la vérification avant de terminer.

---

### Task 3 : chemins XDG et configuration

**Fichiers :**
- Créer : `crates/meute-core/src/error.rs`, `crates/meute-core/src/paths.rs`, `crates/meute-core/src/config.rs`
- Modifier : `crates/meute-core/src/lib.rs` (déclaration des modules)
- Test : tests unitaires dans `config.rs` et `paths.rs`

**Interfaces :**
- Produit :
  - `pub enum CoreError`. Ce task crée les variantes `Config { path: PathBuf, message: String }`, `Io(#[from] std::io::Error)` et `Invalid(String)`. Les tasks suivants ajoutent les leurs.
  - `pub type Result<T> = std::result::Result<T, CoreError>`.
  - `pub struct Paths { pub config_file: PathBuf, pub db_file: PathBuf, pub state_dir: PathBuf }`, avec `Paths::from_env() -> Result<Paths>` et `Paths::ensure_dirs(&self) -> Result<()>`.
  - `pub const DEFAULT_CONFIG: &str`.
  - `pub struct Config { pub repos: ReposConfig, pub claude: ClaudeConfig, pub ui: UiConfig, pub quotas: QuotasConfig }`, avec `Deserialize` et `Default`.
  - `pub fn ensure_config(path: &Path) -> Result<bool>` renvoie `true` si le fichier a été créé.
  - `pub fn load_config(path: &Path) -> Result<Config>`.
  - `pub fn config_get(path: &Path, key: &str) -> Result<String>`.
  - `pub fn config_set(path: &Path, key: &str, value: &str) -> Result<()>`.

Contenu exact de `DEFAULT_CONFIG`. Ses valeurs viennent des § 3.1, 5.1, 5.2, 6.2, 7.4 et 10 de la spécification :

```toml
# Configuration de meute — modifiable à la main ou avec `meute config set`.

[repos]
# Dossiers où meute cherche les dépôts Git (profondeur 3).
roots = ["~/git"]

[claude]
# Mode de permission des sessions Claude lancées par meute :
# manual, acceptEdits, plan, auto, dontAsk, bypassPermissions.
permission_mode = "manual"

[ui]
# Largeur du tableau de bord, en colonnes.
board_width = 60
# En dessous de cette largeur, le tableau de bord passe en plein écran.
narrow_threshold = 120

[quotas]
# Heures pleines : jours ouvrés, de peak_start_hour à peak_end_hour, dans ce fuseau.
peak_timezone = "America/New_York"
peak_start_hour = 8
peak_end_hour = 14
```

- [ ] **Étape 1 : écrire les tests qui doivent échouer** (dans `config.rs`, `#[cfg(test)]`, avec `tempfile::tempdir()`).

```rust
#[test]
fn ensure_config_writes_default_once_and_never_overwrites() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("config.toml");
    assert!(ensure_config(&path).unwrap());
    std::fs::write(&path, "# mine\n[ui]\nboard_width = 80\n").unwrap();
    assert!(!ensure_config(&path).unwrap());
    assert_eq!(std::fs::read_to_string(&path).unwrap(), "# mine\n[ui]\nboard_width = 80\n");
}

#[test]
fn default_config_parses_to_default_values() {
    let cfg: Config = toml::from_str(DEFAULT_CONFIG).unwrap();
    assert_eq!(cfg.repos.roots, vec!["~/git".to_string()]);
    assert_eq!(cfg.claude.permission_mode, "manual");
    assert_eq!((cfg.ui.board_width, cfg.ui.narrow_threshold), (60, 120));
    assert_eq!(cfg.quotas.peak_timezone, "America/New_York");
    assert_eq!((cfg.quotas.peak_start_hour, cfg.quotas.peak_end_hour), (8, 14));
}

#[test]
fn missing_keys_fall_back_to_defaults() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("config.toml");
    std::fs::write(&path, "[ui]\nboard_width = 80\n").unwrap();
    let cfg = load_config(&path).unwrap();
    assert_eq!(cfg.ui.board_width, 80);
    assert_eq!(cfg.ui.narrow_threshold, 120);
}

#[test]
fn config_set_preserves_comments_and_unknown_keys() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("config.toml");
    std::fs::write(&path, "# garde-moi\n[ui]\nboard_width = 60 # largeur\n[perso]\nx = 1\n").unwrap();
    config_set(&path, "ui.board_width", "72").unwrap();
    let text = std::fs::read_to_string(&path).unwrap();
    assert!(text.contains("# garde-moi") && text.contains("# largeur") && text.contains("[perso]"));
    assert_eq!(config_get(&path, "ui.board_width").unwrap(), "72");
}

#[test]
fn config_set_rejects_unknown_key_and_wrong_type() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("config.toml");
    ensure_config(&path).unwrap();
    assert!(matches!(config_set(&path, "ui.nope", "1"), Err(CoreError::Invalid(_))));
    assert!(matches!(config_set(&path, "ui.board_width", "large"), Err(CoreError::Invalid(_))));
}

#[test]
fn invalid_toml_reports_path_and_line_without_touching_file() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("config.toml");
    std::fs::write(&path, "[ui]\nboard_width = = 3\n").unwrap();
    let err = load_config(&path).unwrap_err();
    let msg = err.to_string();
    assert!(msg.contains("config.toml") && msg.contains("line 2"), "{msg}");
    assert_eq!(std::fs::read_to_string(&path).unwrap(), "[ui]\nboard_width = = 3\n");
}

#[test]
fn config_get_returns_default_for_absent_key() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("config.toml");
    std::fs::write(&path, "").unwrap();
    assert_eq!(config_get(&path, "claude.permission_mode").unwrap(), "manual");
}
```

  Dans `paths.rs`, un test vérifie qu'avec `XDG_CONFIG_HOME=<tmp>/c` et `XDG_DATA_HOME=<tmp>/d`, on obtient `config_file == <tmp>/c/meute/config.toml` et `db_file == <tmp>/d/meute/meute.db`. Comme ce test modifie des variables d'environnement, il tourne dans son propre processus de test : nextest isole déjà chaque test.

- [ ] **Étape 2 : lancer les tests et constater l'échec.**
  Commande : `cargo nextest run -p meute-core config paths`.
  Attendu : erreur de compilation, `ensure_config` et `load_config` n'existent pas.

- [ ] **Étape 3 : implémenter.**
  - `ensure_config` écrit de façon atomique (fichier temporaire dans le même dossier, puis `rename`) et crée les dossiers parents.
  - `load_config` : un fichier absent donne `Config::default()`, ce qui équivaut à `DEFAULT_CONFIG`. Les erreurs de `toml::from_str` deviennent `CoreError::Config { path, message }`, dont l'affichage contient le chemin et le message de `toml`, qui inclut lui-même `line N`.
  - `config_get` : lit la clé pointée (`section.cle`) avec `toml_edit`. Si elle est absente, il renvoie la valeur de `Config::default()` passée par `toml::Value`. Une clé inconnue de `Config` donne `Invalid`.
  - `config_set` : modifie le document `toml_edit`. La valeur est interprétée comme une valeur TOML si elle est valide, comme une chaîne sinon. Le document entier est ensuite revalidé en `Config`, avec `#[serde(deny_unknown_fields)]` sur les sections connues uniquement. Si cette validation échoue, on renvoie `Invalid` et le fichier n'est pas modifié. L'écriture est atomique.
  - Une section inconnue (`[perso]`) est tolérée. Pour cela, `Config` ignore les sections de premier niveau inconnues.

- [ ] **Étape 4 : lancer les tests et vérifier qu'ils passent.**
  Commande : `cargo nextest run -p meute-core`.
  Attendu : tout passe.

- [ ] **Étape 5 : commiter.** `git commit -m "feat(core): chemins XDG et configuration TOML"`

---

### Task 4 : types du domaine

**Fichiers :**
- Créer : `crates/meute-core/src/task.rs`, `crates/meute-core/src/actor.rs`, `crates/meute-core/src/project.rs`
- Test : tests unitaires dans chaque fichier

**Interfaces :**
- Produit, dans `task.rs` (tous les types dérivent `Debug`, `Clone`, `PartialEq`, `Serialize`, `Deserialize`) :
  - `pub struct TaskId(pub i64)`, affiché `#N` ;
  - `pub enum TaskStatus { Todo, InProgress, Blocked { reason: String }, Review, Done }`, avec :
    - `fn id(&self) -> &'static str`, qui renvoie `todo`, `in_progress`, `blocked`, `review` ou `done` ;
    - `fn label(&self) -> &'static str`, qui renvoie `à faire`, `en cours`, `bloquée`, `à relire` ou `faite` ;
    - `fn symbol(&self) -> char`, qui renvoie `·`, `»`, `✕`, `◎` ou `✓` (spécification § 9.5) ;
    - `fn is_open(&self) -> bool`, faux seulement pour `Done` ;
  - `pub enum Priority { Urgent, High, Normal, Low }`, avec :
    - `fn id()` : `urgent`, `high`, `normal` ou `low` ;
    - `fn marker() -> &'static str` : `!!`, `!`, `""` ou `""` ;
    - un ordre de tri où `Urgent` vient en premier ;
  - `pub enum Due { Date(jiff::civil::Date), At(jiff::Timestamp) }` ;
  - `pub struct ProjectRef { pub id: ProjectId, pub name: String }` ;
  - `pub struct Task { pub id: TaskId, pub title: String, pub description: String, pub status: TaskStatus, pub priority: Priority, pub due: Option<Due>, pub project: Option<ProjectRef>, pub repo_id: Option<i64>, pub version: u32, pub created_at: Timestamp, pub updated_at: Timestamp, pub completed_at: Option<Timestamp> }` ;
  - `pub struct NewTask { pub title: String, pub description: String, pub priority: Priority, pub due: Option<Due>, pub project_id: Option<ProjectId> }` ;
  - `pub struct TaskPatch { pub title: Option<String>, pub description: Option<String>, pub status: Option<TaskStatus>, pub priority: Option<Priority>, pub due: Option<Option<Due>>, pub project_id: Option<Option<ProjectId>> }`, avec `Default` ;
  - `pub struct Note { pub id: i64, pub task_id: TaskId, pub body: String, pub author: Author, pub channel: Channel, pub session_id: Option<String>, pub created_at: Timestamp }` ;
  - `pub struct TaskEvent { pub task_id: TaskId, pub field: String, pub old_value: Option<String>, pub new_value: Option<String>, pub author: Author, pub channel: Channel, pub session_id: Option<String>, pub created_at: Timestamp }`.
- Produit, dans `actor.rs` :
  - `pub enum Author { User, Claude, System }` ;
  - `pub enum Channel { Tui, Cli, Mcp, Forge }`. Leurs `id()` sont en minuscules ;
  - `pub struct Actor { pub author: Author, pub channel: Channel, pub session_id: Option<String> }`.
- Produit, dans `project.rs` :
  - `pub struct ProjectId(pub i64)` ;
  - `pub struct Project { pub id: ProjectId, pub name: String, pub description: String, pub instructions: String, pub created_at: Timestamp }`.
- Les énumérations sérialisées en JSON utilisent leur `id()`, avec `#[serde(rename_all = "snake_case")]`. `TaskStatus::Blocked` est sérialisé à plat, sous la forme `"status": "blocked", "blocked_reason": "…"`, grâce à la sérialisation de `Task` décrite à l'étape 3.

- [ ] **Étape 1 : écrire les tests qui doivent échouer.**

```rust
#[test]
fn status_ids_labels_symbols_match_spec() {
    let all = [TaskStatus::Todo, TaskStatus::InProgress,
               TaskStatus::Blocked { reason: "x".into() }, TaskStatus::Review, TaskStatus::Done];
    let ids: Vec<_> = all.iter().map(|s| s.id()).collect();
    assert_eq!(ids, ["todo", "in_progress", "blocked", "review", "done"]);
    let symbols: String = all.iter().map(|s| s.symbol()).collect();
    assert_eq!(symbols, "·»✕◎✓");
    assert_eq!(TaskStatus::Review.label(), "à relire");
    assert!(!TaskStatus::Done.is_open() && TaskStatus::Review.is_open());
}

#[test]
fn status_parses_from_id_and_blocked_needs_reason() {
    assert_eq!(TaskStatus::from_id("review", None).unwrap(), TaskStatus::Review);
    assert!(TaskStatus::from_id("blocked", None).is_err());
    assert!(TaskStatus::from_id("blocked", Some("  ")).is_err());
    assert!(TaskStatus::from_id("nope", None).is_err());
}

#[test]
fn priority_markers_and_order() {
    assert_eq!(Priority::Urgent.marker(), "!!");
    assert_eq!(Priority::High.marker(), "!");
    let mut v = vec![Priority::Low, Priority::Urgent, Priority::Normal, Priority::High];
    v.sort();
    assert_eq!(v, [Priority::Urgent, Priority::High, Priority::Normal, Priority::Low]);
}

#[test]
fn task_id_displays_with_hash() {
    assert_eq!(TaskId(12).to_string(), "#12");
}
```

- [ ] **Étape 2 : lancer les tests et constater l'échec.**
  Commande : `cargo nextest run -p meute-core task`.
  Attendu : erreur de compilation.

- [ ] **Étape 3 : implémenter les types ci-dessus.**
  - `TaskStatus::from_id(id: &str, reason: Option<&str>) -> Result<TaskStatus>` renvoie `CoreError::Invalid` si l'identifiant est inconnu, ou si le statut est `blocked` sans raison non vide (après `trim`).
  - `Priority::from_id(&str) -> Result<Priority>`.
  - Le `Serialize` de `Task` est écrit à la main pour produire `status` et `blocked_reason` à plat, ainsi que `due` sous la forme `{"kind": "date" | "at", "value": "…"}`.

- [ ] **Étape 4 : lancer les tests et vérifier qu'ils passent.**
  Commande : `cargo nextest run -p meute-core`.
  Attendu : tout passe.

- [ ] **Étape 5 : commiter.** `git commit -m "feat(core): types du domaine (tâches, projets, auteurs)"`

---

### Task 5 : saisie rapide et échéances

**Fichiers :**
- Créer : `crates/meute-core/src/quick_add.rs`
- Test : tests unitaires dans `quick_add.rs`

**Interfaces :**
- Consomme : `Priority` et `Due` (Task 4).
- Produit :
  - `pub struct QuickAdd { pub title: String, pub project: Option<String>, pub priority: Priority, pub due: Option<Due> }` ;
  - `pub fn parse_quick_add(input: &str, now: &jiff::Zoned) -> Result<QuickAdd>` ;
  - `pub fn parse_due(token: &str, now: &jiff::Zoned) -> Option<Due>` (le jeton est passé sans le `>`). La CLI s'en sert aussi pour `--due`.

**Règles.** Elles viennent de la spécification § 9.3. Les points que la spécification ne précise pas sont tranchés ici :
- L'entrée est découpée sur les espaces. Seul un jeton qui **commence** par `@`, `!` ou `>` est candidat. Tous les autres jetons, et les candidats non reconnus, restent dans le titre, dans leur ordre d'origine, séparés par une seule espace.
- `@nom` (où `nom` n'est pas vide) désigne le projet. Si plusieurs jetons `@` sont présents, le dernier l'emporte.
- `!` donne `High` et `!!` donne `Urgent`. Tout autre jeton composé de `!` reste dans le titre. Si plusieurs jetons de priorité sont présents, le dernier l'emporte. Sans jeton de priorité, la priorité est `Normal`.
- `>X` est passé à `parse_due(X)`. Si le résultat est `None`, le jeton `>X` reste dans le titre.
- Si le titre est vide après extraction, on renvoie `CoreError::Invalid("titre vide")`.
- Formes acceptées par `parse_due`, interprétées dans le fuseau de `now` (les jours `lun`, `mar`, `mer`, `jeu`, `ven`, `sam` et `dim` sont insensibles à la casse) :

| Jeton | Résultat |
|---|---|
| `demain` | `Date(aujourd'hui + 1)` |
| `ce-soir` | `At(aujourd'hui 18:00)`, même si cette heure est déjà passée |
| `lun` … `dim` | `Date(prochain jour de ce nom, strictement après aujourd'hui)` |
| `lun-9h`, `lun-14h30` | `At(ce même jour à H:MM)`, avec H entre 0 et 23 et MM entre 00 et 59 |
| `+Nh`, `+Nm`, `+Nj` | `At(now + N heures, minutes ou jours)`, avec N entre 1 et 9999 |
| `2026-10-20` | `Date`, uniquement si la date est valide |
| `2026-10-20T14:00` | `At` (heure locale), uniquement si elle est valide |

- [ ] **Étape 1 : écrire les tests qui doivent échouer.** `now` vaut le mercredi 2026-10-14 à 10:30, en `Europe/Paris`.

```rust
fn now() -> jiff::Zoned { "2026-10-14T10:30[Europe/Paris]".parse().unwrap() }
fn date(s: &str) -> Due { Due::Date(s.parse().unwrap()) }
fn at(s: &str) -> Due { Due::At(s.parse::<jiff::Zoned>().unwrap().timestamp()) }

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
    assert_eq!(parse_due("ce-soir", &n), Some(at("2026-10-14T18:00[Europe/Paris]")));
    assert_eq!(parse_due("lun", &n), Some(date("2026-10-19")));
    assert_eq!(parse_due("mer", &n), Some(date("2026-10-21"))); // strictement après aujourd'hui
    assert_eq!(parse_due("lun-9h", &n), Some(at("2026-10-19T09:00[Europe/Paris]")));
    assert_eq!(parse_due("ven-14h30", &n), Some(at("2026-10-16T14:30[Europe/Paris]")));
    assert_eq!(parse_due("+2h", &n), Some(at("2026-10-14T12:30[Europe/Paris]")));
    assert_eq!(parse_due("+3j", &n), Some(at("2026-10-17T10:30[Europe/Paris]")));
    assert_eq!(parse_due("2026-10-20", &n), Some(date("2026-10-20")));
    assert_eq!(parse_due("2026-10-20T14:00", &n), Some(at("2026-10-20T14:00[Europe/Paris]")));
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
    assert!(matches!(parse_quick_add("@meute !! >demain", &now()), Err(CoreError::Invalid(_))));
    assert!(matches!(parse_quick_add("   ", &now()), Err(CoreError::Invalid(_))));
}
```

- [ ] **Étape 2 : lancer les tests et constater l'échec.**
  Commande : `cargo nextest run -p meute-core quick_add`.
  Attendu : erreur de compilation.

  On ajoute des tests de propriétés `proptest` (guide § 4), avec `cargo add --dev proptest -p meute-core`. Ils se trouvent dans le même fichier, dans un module `proptests` :

```rust
proptest! {
    #[test]
    fn never_panics(input in ".{0,200}") {
        let _ = parse_quick_add(&input, &now());
        let _ = parse_due(&input, &now());
    }

    #[test]
    fn ok_title_is_non_empty_trimmed_single_spaced(input in "[a-zA-Z0-9@!>+:\- ]{0,80}") {
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
```

- [ ] **Étape 3 : implémenter `parse_quick_add` et `parse_due` en suivant le tableau ci-dessus.** Utiliser l'arithmétique `jiff` sur `Zoned`, qui gère correctement les changements d'heure.

- [ ] **Étape 4 : lancer les tests et vérifier qu'ils passent.**
  Commande : `cargo nextest run -p meute-core`.
  Attendu : tout passe.

- [ ] **Étape 5 : commiter.** `git commit -m "feat(core): saisie rapide et analyse des échéances"`

---

### Task 6 : ouverture de la base et migrations

**Fichiers :**
- Créer : `crates/meute-core/src/db/mod.rs`, `crates/meute-core/src/db/migrations.rs`
- Test : tests unitaires dans `migrations.rs`, et `crates/meute-core/tests/db_open.rs`

**Interfaces :**
- Produit :
  - `pub struct Db`, qui contient une connexion et une horloge ;
  - `Db::open(path: &Path, busy_timeout: Duration) -> Result<Db>`, qui crée le fichier, applique les pragmas, puis migre ;
  - `Db::open_in_memory() -> Result<Db>`, pour les tests ;
  - `Db::with_clock(self, clock: impl Fn() -> Timestamp + Send + Sync + 'static) -> Db`. L'horloge par défaut est `Timestamp::now` ;
  - `pub(crate) fn now(&self) -> Timestamp` ;
  - `pub fn schema_version(&self) -> Result<usize>` ;
  - les variantes `CoreError::Db(#[from] rusqlite::Error)` et `CoreError::Migration(String)`.
- Fonction interne : `fn migrate(conn: &mut Connection, db_path: Option<&Path>, migrations: &Migrations) -> Result<()>`. Si la version actuelle est supérieure à 0 et inférieure à la cible, et que la base est un fichier, elle exécute `VACUUM INTO '<db>.bak-<version actuelle>'` avant de migrer.

**Migration 1.** Elle ne contient que les tables nécessaires à ce plan. Les tables `sessions`, `session_events`, `metric_samples`, `quota_samples` et `saved_states` arriveront avec les plans 2, 3 et 6.

```sql
CREATE TABLE projects (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE COLLATE NOCASE,
  description TEXT NOT NULL DEFAULT '',
  instructions TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE TABLE repos (
  id INTEGER PRIMARY KEY,
  path TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  kind TEXT,
  discovered_at TEXT NOT NULL
);
CREATE TABLE project_repos (
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
  PRIMARY KEY (project_id, repo_id)
);
CREATE TABLE tasks (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL CHECK (length(trim(title)) > 0),
  description TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL CHECK (status IN ('todo','in_progress','blocked','review','done')),
  blocked_reason TEXT,
  priority TEXT NOT NULL CHECK (priority IN ('urgent','high','normal','low')),
  due_date TEXT,
  due_at TEXT,
  project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  repo_id INTEGER REFERENCES repos(id) ON DELETE SET NULL,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  completed_at TEXT,
  CHECK (due_date IS NULL OR due_at IS NULL),
  CHECK ((status = 'blocked') = (blocked_reason IS NOT NULL))
);
CREATE TABLE task_notes (
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  body TEXT NOT NULL,
  author TEXT NOT NULL, channel TEXT NOT NULL, session_id TEXT,
  created_at TEXT NOT NULL
);
-- Pas de clé étrangère : l'historique survit à la suppression de la tâche.
CREATE TABLE task_events (
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL,
  field TEXT NOT NULL, old_value TEXT, new_value TEXT,
  author TEXT NOT NULL, channel TEXT NOT NULL, session_id TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX task_events_task ON task_events(task_id);
```

- [ ] **Étape 1 : écrire les tests qui doivent échouer.**

```rust
// tests/db_open.rs
#[test]
fn open_creates_file_with_wal_and_latest_schema() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("sub/meute.db");
    let db = Db::open(&path, Duration::from_millis(5000)).unwrap();
    assert!(path.exists());
    assert_eq!(db.schema_version().unwrap(), 1);
    assert_eq!(db.pragma_string("journal_mode").unwrap(), "wal");
    assert_eq!(db.pragma_string("foreign_keys").unwrap(), "1");
}

#[test]
fn reopening_is_idempotent_and_makes_no_backup() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("meute.db");
    drop(Db::open(&path, Duration::from_secs(5)).unwrap());
    drop(Db::open(&path, Duration::from_secs(5)).unwrap());
    let backups = std::fs::read_dir(dir.path()).unwrap()
        .filter(|e| e.as_ref().unwrap().file_name().to_string_lossy().contains(".bak-")).count();
    assert_eq!(backups, 0);
}
```

  Dans `migrations.rs`, un test unitaire utilise deux migrations factices (`M::up("CREATE TABLE a(x)")`, puis `M::up("CREATE TABLE b(x)")`). Il applique la première sur un fichier, rouvre la base avec les deux, puis vérifie deux choses : `meute.db.bak-1` existe, et ce fichier contient la table `a` mais pas la table `b`.
  `pragma_string(&self, name: &str) -> Result<String>` est une méthode publique de `Db`. Elle servira aussi à `meute doctor` dans le plan 6.

- [ ] **Étape 2 : lancer les tests et constater l'échec.**
  Commande : `cargo nextest run -p meute-core db`.
  Attendu : erreur de compilation.

- [ ] **Étape 3 : implémenter `Db::open`, `open_in_memory`, `with_clock`, `schema_version`, `pragma_string` et `migrate`, avec la migration 1 ci-dessus.** Les pragmas `journal_mode = WAL`, `foreign_keys = ON` et `busy_timeout` sont appliqués à l'ouverture, avant la migration.

- [ ] **Étape 4 : lancer les tests et vérifier qu'ils passent.**
  Commande : `cargo nextest run -p meute-core`.
  Attendu : tout passe.

- [ ] **Étape 5 : commiter.** `git commit -m "feat(core): base SQLite, migrations et sauvegarde avant migration"`

---

### Task 7 : projets, création et lecture des tâches

**Fichiers :**
- Créer : `crates/meute-core/src/db/projects.rs`, `crates/meute-core/src/db/tasks.rs`
- Test : `crates/meute-core/tests/db_tasks.rs`

**Interfaces :**
- Consomme : `Db` (Task 6), et les types `Task`, `NewTask`, `Project` et `Actor` (Task 4).
- Produit (méthodes de `Db`) :
  - `create_project(&mut self, name: &str, description: &str) -> Result<Project>`. Un nom vide après `trim` donne `Invalid`. Un nom déjà pris, sans tenir compte de la casse, donne `Invalid("projet déjà existant : <nom>")` ;
  - `project_by_name(&self, name: &str) -> Result<Option<Project>>`, insensible à la casse ;
  - `list_projects(&self) -> Result<Vec<Project>>`, triée par nom ;
  - `create_task(&mut self, new: NewTask, actor: &Actor) -> Result<Task>`. La tâche est créée avec le statut `Todo` et la version 1, et un événement `field = "created"` est enregistré ;
  - `get_task(&self, id: TaskId) -> Result<Task>`. Une tâche absente donne `CoreError::NotFound { entity: "tâche", id: String }` ;
  - `list_tasks(&self, filter: &TaskFilter) -> Result<Vec<Task>>` ;
  - `history(&self, id: TaskId) -> Result<Vec<TaskEvent>>`, par ordre chronologique.
- Produit aussi :
  - `pub struct TaskFilter { pub include_done: bool, pub project: ProjectFilter, pub status: Option<&'static str> }`, avec `Default`. Le filtre `status` porte sur l'identifiant du statut ;
  - `pub enum ProjectFilter { Any, Project(ProjectId), Floating }`. `Floating` correspond aux tâches « volantes », sans projet (§ 9.5) ;
  - l'ordre de `list_tasks` est par identifiant croissant. Le tri métier est fait par le Task 9.

- [ ] **Étape 1 : écrire les tests qui doivent échouer.** La fonction utilitaire `test_db()` renvoie `Db::open_in_memory()?.with_clock(|| "2026-10-14T08:30:00Z".parse().unwrap())`.

```rust
fn user() -> Actor { Actor { author: Author::User, channel: Channel::Cli, session_id: None } }

#[test]
fn create_and_get_task_with_project() {
    let mut db = test_db();
    let p = db.create_project("meute", "").unwrap();
    let t = db.create_task(NewTask { title: "Écrire le plan".into(), description: String::new(),
        priority: Priority::High, due: None, project_id: Some(p.id) }, &user()).unwrap();
    assert_eq!((t.version, t.status.clone()), (1, TaskStatus::Todo));
    assert_eq!(t.project.as_ref().map(|r| r.name.as_str()), Some("meute"));
    assert_eq!(db.get_task(t.id).unwrap(), t);
    let h = db.history(t.id).unwrap();
    assert_eq!(h.len(), 1);
    assert_eq!((h[0].field.as_str(), h[0].author.clone(), h[0].channel.clone()), ("created", Author::User, Channel::Cli));
}

#[test]
fn project_names_are_case_insensitive_and_unique() {
    let mut db = test_db();
    db.create_project("Meute", "").unwrap();
    assert!(db.project_by_name("meute").unwrap().is_some());
    assert!(matches!(db.create_project("MEUTE", ""), Err(CoreError::Invalid(_))));
    assert!(matches!(db.create_project("  ", ""), Err(CoreError::Invalid(_))));
}

#[test]
fn list_filters_done_floating_and_project() {
    // jeu de données : t1 (projet A), t2 (volante), t3 (projet A, done via SQL direct)
    // include_done=false → [t1, t2] ; Floating → [t2] ; Project(A) + include_done → [t1, t3]
}

#[test]
fn get_missing_task_is_not_found() {
    let db = test_db();
    assert!(matches!(db.get_task(TaskId(99)), Err(CoreError::NotFound { .. })));
}
```

  Le corps de `list_filters_done_floating_and_project` crée exactement le jeu de données décrit en commentaire et vérifie les trois résultats annoncés, sous forme de listes d'identifiants.

- [ ] **Étape 2 : lancer les tests et constater l'échec.**
  Commande : `cargo nextest run -p meute-core db_tasks`.
  Attendu : erreur de compilation.

- [ ] **Étape 3 : implémenter les méthodes.**
  - Chaque écriture se fait dans une transaction.
  - `get_task` et `list_tasks` font un `LEFT JOIN projects` pour remplir `ProjectRef`.
  - La conversion entre ligne SQL et `Task` est regroupée dans une seule fonction, `fn row_to_task(row: &Row) -> rusqlite::Result<Task>`.

- [ ] **Étape 4 : lancer les tests et vérifier qu'ils passent.**
  Commande : `cargo nextest run -p meute-core`.
  Attendu : tout passe.

- [ ] **Étape 5 : commiter.** `git commit -m "feat(core): projets, création et lecture des tâches"`

---

### Task 8 : mise à jour avec contrôle de version, notes et suppression

**Fichiers :**
- Modifier : `crates/meute-core/src/db/tasks.rs`
- Test : `crates/meute-core/tests/db_tasks.rs`

**Interfaces :**
- Consomme : `Db` et les méthodes du Task 7, ainsi que `TaskPatch`.
- Produit (méthodes de `Db`) :
  - `update_task(&mut self, id: TaskId, expected_version: u32, patch: TaskPatch, actor: &Actor) -> Result<Task>` ;
  - `delete_task(&mut self, id: TaskId, expected_version: u32, actor: &Actor) -> Result<()>` ;
  - `add_note(&mut self, id: TaskId, body: &str, actor: &Actor) -> Result<Note>` ;
  - `notes(&self, id: TaskId) -> Result<Vec<Note>>`, par ordre chronologique ;
  - la variante `CoreError::Conflict { current: Box<Task> }`.

**Règles** (spécification § 9.1 et § 9.2) :
- **Version différente de `expected_version`** : on renvoie `Conflict { current }`. Rien n'est écrit, et aucun événement n'est enregistré.
- **Patch sans changement réel**, parce que chaque valeur est égale à l'existante : on renvoie la tâche inchangée, sans incrémenter la version ni enregistrer d'événement.
- **Patch qui change au moins un champ** : la version est incrémentée une seule fois et `updated_at` est mis à jour. Chaque champ modifié donne un `TaskEvent`. Les noms de champ sont `title`, `description`, `status`, `priority`, `due`, `project`. Les valeurs sont représentées par l'identifiant du statut ou de la priorité, l'échéance en texte, et le nom du projet.
- **Passage au statut `Done`** : `completed_at` vaut maintenant. Quand la tâche quitte `Done`, `completed_at` repasse à `NULL`.
- **Mise à jour atomique** : elle se fait par `UPDATE … WHERE id = ? AND version = ?`. Si aucune ligne n'est modifiée, on relit la tâche et on renvoie `Conflict`. C'est ce qui protège contre deux processus qui écrivent en même temps.
- **Notes** : elles sont ajoutées sans modifier la version de la tâche. Un corps vide après `trim` donne `Invalid`. Une tâche absente donne `NotFound`.
- **Suppression** : elle vérifie la version, supprime la tâche (les notes sont supprimées en cascade) et enregistre un événement `field = "deleted"`, avec le titre comme `old_value`.

- [ ] **Étape 1 : écrire les tests qui doivent échouer.**

```rust
#[test]
fn update_bumps_version_once_and_logs_each_field() {
    let (mut db, t) = db_with_task();
    let t2 = db.update_task(t.id, 1, TaskPatch { title: Some("Nouveau".into()),
        priority: Some(Priority::Urgent), ..Default::default() }, &user()).unwrap();
    assert_eq!(t2.version, 2);
    let fields: Vec<_> = db.history(t.id).unwrap().into_iter().map(|e| e.field).collect();
    assert_eq!(fields, ["created", "title", "priority"]);
}

#[test]
fn stale_version_is_rejected_with_current_state_and_no_event() {
    let (mut db, t) = db_with_task();
    db.update_task(t.id, 1, TaskPatch { title: Some("A".into()), ..Default::default() }, &user()).unwrap();
    let err = db.update_task(t.id, 1, TaskPatch { title: Some("B".into()), ..Default::default() }, &claude()).unwrap_err();
    match err { CoreError::Conflict { current } => { assert_eq!(current.title, "A"); assert_eq!(current.version, 2); }
                other => panic!("{other:?}") }
    assert_eq!(db.history(t.id).unwrap().len(), 2);
}

#[test]
fn noop_patch_changes_nothing() {
    let (mut db, t) = db_with_task();
    let same = db.update_task(t.id, 1, TaskPatch { title: Some(t.title.clone()), ..Default::default() }, &user()).unwrap();
    assert_eq!(same.version, 1);
    assert_eq!(db.history(t.id).unwrap().len(), 1);
}

#[test]
fn done_sets_and_clears_completed_at() {
    let (mut db, t) = db_with_task();
    let d = db.update_task(t.id, 1, TaskPatch { status: Some(TaskStatus::Done), ..Default::default() }, &user()).unwrap();
    assert!(d.completed_at.is_some());
    let r = db.update_task(t.id, 2, TaskPatch { status: Some(TaskStatus::Review), ..Default::default() }, &user()).unwrap();
    assert!(r.completed_at.is_none());
}

#[test]
fn notes_do_not_bump_version_and_keep_author() {
    let (mut db, t) = db_with_task();
    db.add_note(t.id, "Avancé sur la partie SQL", &claude()).unwrap();
    assert_eq!(db.get_task(t.id).unwrap().version, 1);
    let n = db.notes(t.id).unwrap();
    assert_eq!((n.len(), n[0].author.clone(), n[0].channel.clone()), (1, Author::Claude, Channel::Mcp));
    assert!(matches!(db.add_note(t.id, "  ", &user()), Err(CoreError::Invalid(_))));
}

#[test]
fn delete_checks_version_and_keeps_history() {
    let (mut db, t) = db_with_task();
    assert!(matches!(db.delete_task(t.id, 7, &user()), Err(CoreError::Conflict { .. })));
    db.delete_task(t.id, 1, &user()).unwrap();
    assert!(matches!(db.get_task(t.id), Err(CoreError::NotFound { .. })));
    assert_eq!(db.history(t.id).unwrap().last().unwrap().field, "deleted");
}
```

  `claude()` renvoie `Actor { author: Claude, channel: Mcp, session_id: Some("s-1") }`, et `db_with_task()` renvoie `test_db()` avec une tâche « Relire la PR » créée, en version 1.
  Un test supplémentaire, `two_connections_same_version_second_conflicts`, ouvre **deux** `Db` sur le même fichier temporaire. La première met à jour avec la version 1 et réussit. La seconde met à jour avec la version 1 et obtient `Conflict`. C'est le point de vigilance n° 3.

- [ ] **Étape 2 : lancer les tests et constater l'échec.**
  Commande : `cargo nextest run -p meute-core db_tasks`.
  Attendu : échec, les méthodes sont absentes.

- [ ] **Étape 3 : implémenter `update_task`, `delete_task`, `add_note` et `notes` selon les règles ci-dessus.**

- [ ] **Étape 4 : lancer les tests et vérifier qu'ils passent.**
  Commande : `cargo nextest run -p meute-core`.
  Attendu : tout passe.

- [ ] **Étape 5 : commiter.** `git commit -m "feat(core): mises à jour versionnées, notes et suppression"`

---

### Task 9 : regroupement par urgence, tri et affichage des échéances

**Fichiers :**
- Créer : `crates/meute-core/src/views.rs`
- Test : tests unitaires dans `views.rs`

**Interfaces :**
- Consomme : `Task`, `Due` et `Priority` (Task 4).
- Produit :
  - `pub enum Bucket { Overdue, Today, Upcoming, NoDue, DoneToday }`, avec `label()` qui renvoie `En retard`, `Aujourd'hui`, `À venir`, `Sans échéance` ou `Faites aujourd'hui` (§ 9.5) ;
  - `pub fn bucket_of(task: &Task, now: &Zoned) -> Option<Bucket>`, qui renvoie `None` pour une tâche terminée avant aujourd'hui ;
  - `pub fn sort_for_display(tasks: &mut [Task])` ;
  - `pub fn format_due(due: &Due, now: &Zoned) -> String` ;
  - `pub fn is_overdue(task: &Task, now: &Zoned) -> bool`.

**Règles :**
- **Tâche terminée** (`Done`) : `DoneToday` si `completed_at` tombe aujourd'hui dans le fuseau de `now`, `None` sinon.
- **Tâche ouverte avec une date `Date(d)`** : `Overdue` si `d` est avant aujourd'hui, `Today` si c'est aujourd'hui, `Upcoming` si c'est plus tard.
- **Tâche ouverte avec une heure `At(t)`** : `Overdue` si `t` est passé, `Today` si `t` tombe plus tard aujourd'hui, `Upcoming` sinon.
- **Tâche ouverte sans échéance** : `NoDue`.
- **Tri** : par échéance croissante, où une `Date` compte pour 23:59:59 ce jour-là et l'absence d'échéance vient en dernier. Puis par priorité (`Urgent` en premier), puis par identifiant.
- **Format de l'échéance**, en français :
  - `Date` : `aujourd'hui`, `demain`, sinon `lun. 19 oct.` ;
  - `At` : la même forme suivie de l'heure (`aujourd'hui 18:00`, `lun. 19 oct. 09:00`) ;
  - l'année est ajoutée seulement si elle diffère de celle de `now` (`mar. 5 janv. 2027`).

- [ ] **Étape 1 : écrire les tests qui doivent échouer.** `now` vaut `2026-10-14T10:30[Europe/Paris]`. On utilise une fonction `task(due, status, prio, id)` qui construit une `Task` en mémoire.

```rust
#[test]
fn buckets_follow_rules() {
    let n = now();
    assert_eq!(bucket_of(&task(Some(date("2026-10-13")), Todo, Normal, 1), &n), Some(Bucket::Overdue));
    assert_eq!(bucket_of(&task(Some(at("2026-10-14T09:00[Europe/Paris]")), Todo, Normal, 2), &n), Some(Bucket::Overdue));
    assert_eq!(bucket_of(&task(Some(date("2026-10-14")), Todo, Normal, 3), &n), Some(Bucket::Today));
    assert_eq!(bucket_of(&task(Some(at("2026-10-14T18:00[Europe/Paris]")), Todo, Normal, 4), &n), Some(Bucket::Today));
    assert_eq!(bucket_of(&task(Some(date("2026-10-15")), Todo, Normal, 5), &n), Some(Bucket::Upcoming));
    assert_eq!(bucket_of(&task(None, Todo, Normal, 6), &n), Some(Bucket::NoDue));
    assert_eq!(bucket_of(&done_at("2026-10-14T07:00Z"), &n), Some(Bucket::DoneToday));
    assert_eq!(bucket_of(&done_at("2026-10-13T07:00Z"), &n), None);
}

#[test]
fn sort_by_due_then_priority_then_id() {
    let mut v = vec![task(None, Todo, Urgent, 1), task(Some(date("2026-10-15")), Todo, Low, 2),
                     task(Some(date("2026-10-15")), Todo, High, 3), task(Some(at("2026-10-15T09:00[Europe/Paris]")), Todo, Low, 4)];
    sort_for_display(&mut v);
    assert_eq!(v.iter().map(|t| t.id.0).collect::<Vec<_>>(), [4, 3, 2, 1]);
}

#[test]
fn due_formatting_in_french() {
    let n = now();
    assert_eq!(format_due(&date("2026-10-14"), &n), "aujourd'hui");
    assert_eq!(format_due(&date("2026-10-15"), &n), "demain");
    assert_eq!(format_due(&date("2026-10-19"), &n), "lun. 19 oct.");
    assert_eq!(format_due(&at("2026-10-14T18:00[Europe/Paris]"), &n), "aujourd'hui 18:00");
    assert_eq!(format_due(&date("2027-01-05"), &n), "mar. 5 janv. 2027");
}
```

- [ ] **Étape 2 : lancer les tests et constater l'échec.**
  Commande : `cargo nextest run -p meute-core views`.
  Attendu : erreur de compilation.

- [ ] **Étape 3 : implémenter.** Les noms abrégés des jours et des mois en français sont dans deux tableaux constants. On n'utilise pas de bibliothèque de localisation.

- [ ] **Étape 4 : lancer les tests et vérifier qu'ils passent.**
  Commande : `cargo nextest run -p meute-core`.
  Attendu : tout passe.

- [ ] **Étape 5 : commiter.** `git commit -m "feat(core): regroupement par urgence, tri et format des échéances"`

---

### Task 10 : CLI — ajout, liste et affichage des tâches, projets

**Fichiers :**
- Créer : `crates/meute/src/cli/mod.rs` (définitions `clap`), `crates/meute/src/cli/task.rs`, `crates/meute/src/cli/project.rs`, `crates/meute/src/render.rs`, `crates/meute/src/app.rs`
- Modifier : `crates/meute/src/main.rs`
- Test : `crates/meute/tests/cli_tasks.rs`

**Interfaces :**
- Consomme : `Paths`, `ensure_config`, `load_config`, `Db`, `parse_quick_add`, `parse_due`, `views::*` et les types du domaine.
- Produit :
  - `struct App { db: Db, now: Zoned, actor: Actor }`, construit par `App::init() -> anyhow::Result<App>`. Cette fonction appelle `Paths::from_env`, `ensure_dirs`, `ensure_config` et `Db::open(…, 5000 ms)`. L'acteur vaut `User` / `Cli`, avec `session_id` tiré de `MEUTE_SESSION` si cette variable est définie ;
  - la variable d'environnement `MEUTE_NOW`, en RFC 3339 avec fuseau (par exemple `2026-10-14T10:30[Europe/Paris]`), remplace `now` **uniquement** si elle est définie. Elle sert aux tests de bout en bout et n'est pas documentée pour les utilisateurs.
- Commandes :

| Commande | Effet et sortie |
|---|---|
| `meute task add <saisie…> [--dry-run]` | Les arguments sont joints par des espaces, puis analysés par `parse_quick_add`. Un `@projet` inconnu provoque une erreur `projet inconnu : X (projets : a, b)`, et rien n'est créé. Avec `--dry-run`, la commande affiche le résultat analysé sans rien créer. Sinon, elle affiche `Créée : <ligne>` |
| `meute task list [--all] [--project NOM \| --floating] [--status ID] [--json]` | Les tâches sont triées par `sort_for_display`, avec une ligne par tâche. Avec `--json`, la commande produit un tableau JSON de `Task` |
| `meute task show <ID> [--json]` | Affiche l'en-tête `#N Titre`, puis les champs (statut, priorité, échéance, projet, version, dates), puis les notes sous la forme `[YYYY-MM-DD HH:MM] auteur : texte` |
| `meute project add <NOM> [--description D]` | Affiche `Projet créé : NOM` |
| `meute project list [--json]` | Affiche un nom par ligne |

  - **Format d'une ligne de tâche**, fonction `render::task_line(&Task, &Zoned) -> String` (§ 9.5) : `#12 » ! Titre @projet · demain`. Les éléments sont : l'identifiant, le symbole du statut, le marqueur de priorité s'il n'est pas vide, le titre, `@projet` s'il existe, puis `· ` suivi de **l'un** des éléments suivants, dans cet ordre de priorité :
    - `bloquée : <raison>` ;
    - `à relire` ;
    - l'échéance formatée, suivie de ` (en retard)` si `is_overdue`.
  - **Codes de sortie**, fonction `main` :
    - 0 en cas de succès ;
    - 1 pour une erreur générale ;
    - 2 pour une erreur d'utilisation (comportement de `clap`) ;
    - 3 pour `Conflict` ;
    - 4 pour `NotFound`.

    Le message d'erreur est écrit sur stderr, préfixé par `meute : `.

- [ ] **Étape 1 : écrire les tests qui doivent échouer.** Une fonction utilitaire `meute(tmp)` renvoie un `Command` qui pointe vers `XDG_CONFIG_HOME`, `XDG_DATA_HOME` et `XDG_STATE_HOME` dans `tmp`, avec `MEUTE_NOW=2026-10-14T10:30[Europe/Paris]`.

```rust
#[test]
fn add_then_list_shows_spec_line() {
    let tmp = tempfile::tempdir().unwrap();
    meute(&tmp).args(["project", "add", "meute"]).assert().success();
    meute(&tmp).args(["task", "add", "Relire", "la", "PR", "@meute", "!", ">demain"]).assert()
        .success().stdout("Créée : #1 · ! Relire la PR @meute · demain\n");
    meute(&tmp).args(["task", "list"]).assert().success()
        .stdout("#1 · ! Relire la PR @meute · demain\n");
}

#[test]
fn unknown_project_creates_nothing() {
    let tmp = tempfile::tempdir().unwrap();
    meute(&tmp).args(["project", "add", "meute"]).assert().success();
    meute(&tmp).args(["task", "add", "x", "@meuet"]).assert().code(1)
        .stderr(predicates::str::contains("projet inconnu : meuet (projets : meute)"));
    meute(&tmp).args(["task", "list", "--all", "--json"]).assert().success().stdout("[]\n");
}

#[test]
fn dry_run_creates_nothing() {
    let tmp = tempfile::tempdir().unwrap();
    meute(&tmp).args(["task", "add", "--dry-run", "Payer", "!!", ">ven-14h30"]).assert().success()
        .stdout(predicates::str::contains("Payer").and(predicates::str::contains("!!"))
            .and(predicates::str::contains("ven. 16 oct. 14:30")));
    meute(&tmp).args(["task", "list", "--json"]).assert().stdout("[]\n");
}

#[test]
fn show_missing_task_exits_4() {
    let tmp = tempfile::tempdir().unwrap();
    meute(&tmp).args(["task", "show", "42"]).assert().code(4);
}

#[test]
fn first_run_writes_default_config() {
    let tmp = tempfile::tempdir().unwrap();
    meute(&tmp).args(["task", "list"]).assert().success();
    assert!(tmp.path().join("config/meute/config.toml").exists());
}
```

  Les variables `XDG_*_HOME` pointent respectivement vers `tmp/config`, `tmp/data` et `tmp/state`.

- [ ] **Étape 2 : lancer les tests et constater l'échec.**
  Commande : `cargo nextest run -p meute cli_tasks`.
  Attendu : échec, les sous-commandes sont inconnues.

  On ajoute deux tests d'instantané `insta` (guide § 4), avec `cargo add --dev insta -p meute`. Chaque test crée des tâches variées : chaque statut, chaque priorité, avec et sans projet, une échéance en retard, aujourd'hui, demain et la semaine prochaine. Il fait ensuite `insta::assert_snapshot!` sur la sortie de la commande :
  - `snapshot_task_list_mixed` porte sur `meute task list --all` ;
  - `snapshot_task_show_with_notes` porte sur `meute task show 1` après deux notes.

  Au premier passage, `cargo insta review` montre l'instantané proposé. **On le compare ligne par ligne avec les formats de ce task et de la spécification § 9.5 avant de l'accepter.**

- [ ] **Étape 3 : implémenter les sous-commandes, `App` et `render::task_line`.** La conversion entre `CoreError` et code de sortie se fait par un `downcast_ref::<CoreError>()` sur l'erreur `anyhow`, dans `main`.

- [ ] **Étape 4 : lancer les tests et vérifier qu'ils passent.**
  Commande : `cargo nextest run`.
  Attendu : tout passe.

- [ ] **Étape 5 : commiter.** `git commit -m "feat(cli): ajout, liste et affichage des tâches, gestion des projets"`

---

### Task 11 : CLI — modification, statut, notes, suppression et configuration

**Fichiers :**
- Modifier : `crates/meute/src/cli/mod.rs`, `crates/meute/src/cli/task.rs`
- Créer : `crates/meute/src/cli/config.rs`
- Test : `crates/meute/tests/cli_tasks.rs`, `crates/meute/tests/cli_config.rs`

**Interfaces :**
- Consomme : `Db::update_task`, `delete_task`, `add_note` (Task 8), `config_get` et `config_set` (Task 3), ainsi que `App` (Task 10).
- Commandes :

| Commande | Effet |
|---|---|
| `meute task edit <ID> [--title T] [--description D] [--priority urgent\|high\|normal\|low] [--due JETON\|none] [--project NOM\|none] [--expected-version V]` | Construit un `TaskPatch`. `--due` est analysé par `parse_due`, et un jeton invalide provoque l'erreur `échéance invalide : X`. Affiche la ligne de la tâche après modification |
| `meute task status <ID> <todo\|in_progress\|blocked\|review\|done> [--reason R] [--expected-version V]` | Le statut `blocked` sans `--reason` provoque une erreur et un code 1 |
| `meute task note <ID> <texte…>` | Affiche `Note ajoutée à #N` |
| `meute task rm <ID> [--yes] [--expected-version V]` | Sans `--yes` et sur un terminal, demande `Supprimer #N « Titre » ? [o/N] `. Sans `--yes` et hors terminal, refuse avec `confirmation requise : relancez avec --yes` et le code 1. Sans `--expected-version`, la version relue juste avant est utilisée |
| `meute config path` | Affiche le chemin du fichier de configuration |
| `meute config get <clé>` / `meute config set <clé> <valeur>` | Délèguent à `config_get` et `config_set` |

  En cas de conflit, la commande sort avec le code 3, et stderr contient `modifiée entre-temps (version actuelle : N)` suivi de la ligne de la tâche dans son état actuel.

- [ ] **Étape 1 : écrire les tests qui doivent échouer.**

```rust
#[test]
fn status_blocked_requires_reason_then_shows_it() {
    let tmp = setup_with_task(); // crée #1 « Relire la PR »
    meute(&tmp).args(["task", "status", "1", "blocked"]).assert().code(1);
    meute(&tmp).args(["task", "status", "1", "blocked", "--reason", "attente revue"]).assert().success()
        .stdout("#1 ✕ Relire la PR · bloquée : attente revue\n");
}

#[test]
fn stale_expected_version_exits_3_with_current_state() {
    let tmp = setup_with_task();
    meute(&tmp).args(["task", "edit", "1", "--title", "A"]).assert().success();
    meute(&tmp).args(["task", "edit", "1", "--title", "B", "--expected-version", "1"]).assert().code(3)
        .stderr(predicates::str::contains("modifiée entre-temps (version actuelle : 2)")
            .and(predicates::str::contains("#1 · A")));
}

#[test]
fn rm_without_yes_off_tty_refuses() {
    let tmp = setup_with_task();
    meute(&tmp).args(["task", "rm", "1"]).assert().code(1)
        .stderr(predicates::str::contains("relancez avec --yes"));
    meute(&tmp).args(["task", "rm", "1", "--yes"]).assert().success();
    meute(&tmp).args(["task", "show", "1"]).assert().code(4);
}

#[test]
fn note_then_show_lists_it_with_author() {
    let tmp = setup_with_task();
    meute(&tmp).args(["task", "note", "1", "Commencé"]).assert().success().stdout("Note ajoutée à #1\n");
    meute(&tmp).args(["task", "show", "1"]).assert().success()
        .stdout(predicates::str::contains("user : Commencé"));
}

#[test]
fn edit_due_invalid_token_is_rejected() {
    let tmp = setup_with_task();
    meute(&tmp).args(["task", "edit", "1", "--due", "bientot"]).assert().code(1)
        .stderr(predicates::str::contains("échéance invalide : bientot"));
}
```

  Dans `cli_config.rs`, on teste trois choses :
  - `config set ui.board_width 72` suivi de `config get ui.board_width` affiche `72` ;
  - `config set ui.nope 1` sort avec le code 1 ;
  - `config path` affiche un chemin qui se termine par `meute/config.toml`.

- [ ] **Étape 2 : lancer les tests et constater l'échec.**
  Commande : `cargo nextest run -p meute`.
  Attendu : échec sur les nouvelles commandes.

  Un test d'instantané `snapshot_conflict_message` porte sur stderr après un conflit de version. Il se relit avant d'être accepté, comme au Task 10.

- [ ] **Étape 3 : implémenter les commandes.** La confirmation interactive utilise `std::io::IsTerminal` sur stdin.

- [ ] **Étape 4 : faire la vérification complète.**
  Commande : la vérification complète du guide § 9.
  Attendu : tous les tests passent, sans aucun avertissement, et `cargo deny` et `cargo machete` sont propres.

- [ ] **Étape 5 : commiter.** `git commit -m "feat(cli): modification, statut, notes, suppression et configuration"`

---

### Task 12 : tests de mutation, puis PR

**Fichiers :**
- Modifier : les fichiers de tests concernés par les mutations manquées
- Créer : `docs/dev/mutants/2026-plan-1.md`, le rapport de mutation joint à la PR

**Interfaces :**
- Consomme : tout le code des Tasks 1 à 11.
- Produit :
  - un rapport de mutation ;
  - la PR du plan 1.

- [ ] **Étape 1 : lancer les tests de mutation.**
  Commande : `cargo mutants --package meute-core --no-shuffle -- --hide-progress-bar` (guide § 4).
  Résultat : le décompte `caught` / `missed` / `unviable` / `timeout`. La liste des mutations manquées est dans `mutants.out/missed.txt`.

- [ ] **Étape 2 : traiter chaque mutation manquée en TDD.** Pour chacune, on écrit un test qui l'aurait détectée, on vérifie qu'il **échoue** sur le code muté (`cargo mutants --file <fichier> --re '<motif>'`, ou en appliquant la mutation à la main le temps de la vérification), puis qu'il passe sur le code réel. Si une mutation est équivalente au code d'origine (aucun comportement observable ne change), on la justifie en une phrase dans le rapport au lieu d'écrire un test.
  Attendu : aucune mutation manquée sans test ni justification dans `quick_add.rs`, `views.rs`, `db/tasks.rs` et `config.rs`.

- [ ] **Étape 3 : écrire le rapport.** `docs/dev/mutants/2026-plan-1.md` contient le décompte avant et après, la liste des tests ajoutés et les justifications. On ajoute `mutants.out*/` au `.gitignore`.

- [ ] **Étape 4 : faire la vérification complète (guide § 9).**
  Attendu : tout passe.

- [ ] **Étape 5 : commiter, pousser et ouvrir la PR.**

```bash
git commit -m "test: renforce les tests d'après cargo-mutants"
git push -u origin feat/plan-1-socle-taches
gh pr create --base main --assignee gaetinux --title "Plan 1 : socle et tâches" \
  --body "<résumé des 12 tasks, exceptions de lint avec leur raison, rapport de mutation, puis la ligne « 🤖 Generated with Claude Code », sans lien de session>"
```
