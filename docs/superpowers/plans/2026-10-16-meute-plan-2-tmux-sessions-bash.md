> **Plan Rust obsolète, conservé pour l'historique. Ne pas l'exécuter.** L'implémentation de référence se trouve sous le tag `rust-plan-2-wip` ; il est remplacé par le [plan 2 Python](2026-10-18-meute-plan-2-python-tmux-sessions-bash.md).

# meute — Plan 2 : tmux, dépôts et sessions Bash — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Objectif :** `meute` démarre son serveur tmux dédié et sa disposition (zone principale et tableau de bord minimal), découvre les dépôts, puis lance, affiche, réconcilie et arrête des sessions Bash, depuis la CLI comme depuis le tableau de bord.

**Architecture :** trois nouvelles crates sans dépendance entre elles (`meute-tmux` pilote tmux en appelant le binaire `tmux`, `meute-git` parcourt le système de fichiers, `meute-tui` dessine le tableau de bord avec ratatui) et une extension de `meute-core` : sessions, dépôts et règle de réconciliation. Le binaire `meute` assemble le tout. Il n'y a pas de service de fond : l'état vit dans tmux (les panneaux) et dans SQLite (les sessions), et chaque lecture les réconcilie. Le plan commence par les reports du plan 1 sur l'API de `meute-core`.

**Stack technique :**
- existante : `rusqlite`, `rusqlite_migration`, `serde`, `jiff`, `thiserror`, `clap`, `anyhow`, `toml_edit`, `insta`, `proptest`, `assert_cmd`, `tempfile` ;
- nouvelle : `uuid` (fonctionnalités `v4` et `serde`), `ratatui` (avec `ratatui::crossterm`, sans dépendance directe à `crossterm`) ;
- externe : `tmux` ≥ 3.2 (3.5a en local), installé dans la CI.

**Spécification :** `docs/superpowers/specs/2026-10-15-meute-design.md`, § 5.1 à 5.4, 6.1, 6.3 à 6.5, 10 et 16. Feuille de route : `docs/superpowers/plans/2026-10-15-meute-v1-roadmap.md` (section « Reports issus du plan 1 »).

**Guide de référence :** `docs/dev/developpement-assiste-par-ia.md`. Il fait partie des exigences de chaque tâche.

## Contraintes globales

**Hérité du plan 1 (inchangé)**
- Rust stable, édition 2024, `rust-version = "1.85"` ; lints du `[workspace.lints]`, `[lints] workspace = true` dans chaque nouvelle crate ; exceptions par `#[expect(lint, reason = "…")]` seulement, chacune citée dans la PR.
- Pas de `_ =>` sur nos enums, pas de `#[non_exhaustive]` interne, `///` sur tout le public de `meute-core`, fichiers de moins de 300 lignes (400 au maximum).
- Dépendances ajoutées uniquement avec `cargo add`, documentation de la version installée consultée avant usage.
- **MSRV** : le résolveur `resolver = "3"` choisit des versions compatibles avec Rust 1.85. `ratatui` 0.30 (Rust 1.88) et `uuid` 1.28 (Rust 1.89) sont donc écartés au profit de la dernière version compatible ; `cargo +1.85 check --workspace --all-targets` doit passer à chaque tâche qui ajoute une dépendance.
- Erreurs : `thiserror` dans les bibliothèques, `anyhow` dans le binaire. Code synchrone.
- Identifiants et commentaires en anglais ; textes affichés en français, copiés **mot pour mot** depuis ce plan quand il les fixe.
- Toute règle métier vit dans `meute-core`. `meute-tmux`, `meute-git` et `meute-tui` ne dépendent pas les unes des autres ; seule `meute-tui` dépend de `meute-core` (spécification § 4.3).

**TDD et tests**
- TDD strict : test écrit, échec constaté pour la bonne raison, code minimal, refactorisation au vert. La sortie de l'échec est citée dans le rapport de la tâche.
- On ne modifie, ne supprime ni ne désactive jamais un test existant pour le faire passer. **Seules exceptions autorisées par ce plan**, toutes deux mécaniques et signalées dans le message de commit et dans la PR :
  1. Task 2 : l'adaptation des appels à `TaskFilter.status` au nouveau type, sans toucher aux assertions ;
  2. Task 3 : la valeur attendue de `schema_version()` passe de `1` à `2` dans `crates/meute-core/tests/db_open.rs` et `crates/meute-core/src/db/mod.rs` (ces tests vérifient « le dernier schéma », qui change).
- **tmux en test** : uniquement sur un serveur jetable `tmux -L meute-test-<uuid>`, lancé avec `-f /dev/null` (ou la configuration générée sous test), et tué à la fin du test, y compris en cas d'échec (garde avec `Drop`). Jamais sur le serveur `meute` ni sur le tmux de l'utilisateur (spécification § 17).
- Les tests qui attendent un effet asynchrone de tmux interrogent l'état toutes les 100 ms avec une échéance de 10 s. Aucun `sleep` fixe.
- Vérification complète (guide § 9) à la fin de chaque tâche : `cargo fmt --check && cargo clippy --workspace --all-targets -- -D warnings && cargo nextest run --workspace && cargo deny check && cargo machete`.

**Conventions de ce plan**
- Socket tmux : `meute` par défaut, remplacé par la variable `MEUTE_TMUX_SOCKET` si elle est définie (utilisée par les tests du binaire).
- Noms tmux : session `meute`, fenêtre `main` (cible `=meute:main`), session `meute-bg` ; options de **pane** `@meute_id` (UUID de la session), `@meute_role` (`board` ou `welcome`), `remain-on-exit` ; option globale `@meute_status`.
- Le tableau de bord est à droite (`{right}`), la zone principale à gauche (`{left}`) ; la position est une décision ouverte (§ 15) qui n'est pas réglable dans ce plan.
- Configuration tmux générée : `<état>/tmux.conf` (`~/.local/state/meute/tmux.conf`), réécrite à chaque commande qui touche à tmux. Ce n'est pas un fichier de l'utilisateur.
- Git : branche `feat/plan-2-tmux-sessions-bash` créée depuis `main`, un commit par tâche, PR assignée à `gaetinux` à la fin, jamais de push sur `main`. Messages terminés par `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`, sans lien de session.

## Hors périmètre (reporté, inscrit dans la feuille de route à la Task 14)

- `M-n` / `M-N` et le compteur « à traiter » de la barre d'état : ils dépendent des états Claude (plans 3 et 4).
- Les actions sur les panneaux orphelins (adopter, fermer) : ce plan les **affiche** seulement (CLI et tableau de bord) ; les actions viennent avec le TUI complet (plan 4).
- Le formulaire de lancement `N`, la recommandation de worktree et le « dernier type utilisé » de `n` (plan 4) ; dans ce plan, `n` lance toujours Bash.
- La création automatique de projets et les worktrees (plan 6) ; les worktrees découverts ne sont pas enregistrés en base.
- § 16, « base indisponible ou verrouillée » : dans ce plan, le tableau de bord affiche l'erreur dans son pied de page ; la vue Sessions alimentée par tmux seul vient avec le TUI complet (plan 4).
- Les colonnes Claude de la table `sessions` (`native_id`, mode de permission, métriques…) : ajoutées par migration au plan 3.

## Points de vigilance

1. **tmux en échec ≠ serveur arrêté.** Si `list-panes` échoue parce que le serveur n'existe pas (« no server running », « error connecting to »), il n'y a aucun panneau et les sessions vivantes deviennent `Unreachable`. Toute autre erreur (tmux absent, sortie illisible) est remontée telle quelle et **aucune** session n'est modifiée. Tests aux Tasks 6 et 11.
2. **Panneau tué hors de meute.** `exit 7` dans une session Bash donne `Exited(7)` (le panneau reste, mort, grâce à `remain-on-exit`) ; `tmux kill-pane` donne `Unreachable`. Tests aux Tasks 4 et 11.
3. **Arrêt de la session affichée.** Tuer le panneau de la zone principale laisse le tableau de bord seul dans la fenêtre : meute recrée le panneau d'accueil et remet le tableau à sa largeur (§ 5.1). Test à la Task 12.
4. **Afficher la session déjà affichée.** Pas de `swap-pane` d'un panneau avec lui-même : seul le focus change. Test à la Task 12.
5. **Racines de dépôts absentes, illisibles, ou contenant des boucles de liens symboliques.** La découverte ignore ce qu'elle ne peut pas lire, ne suit pas les liens symboliques et ne lève jamais d'erreur. Test à la Task 8.

---

### Task 1 : utilitaires de test communs de `meute-core`

Report du plan 1 (« Avant les plans 2 à 6 — tests »). Refactorisation des tests seulement : aucun code de production, aucune assertion modifiée.

**Fichiers :**
- Créer : `crates/meute-core/tests/common/mod.rs`
- Modifier : `crates/meute-core/tests/db_tasks.rs`, `db_task_update.rs`, `db_errors_mutants.rs` (suppression de leurs copies locales des fonctions déplacées)

**Interfaces :**
- Produit (dans `tests/common/mod.rs`, avec `#![allow(dead_code, reason = "each test crate uses a subset of the helpers")]` comme `crates/meute/tests/support/mod.rs`) :
  - `pub fn user() -> Actor` (User / Cli / pas de session) et `pub fn claude() -> Actor` (reprendre exactement les valeurs de `db_task_update.rs`) ;
  - `pub fn test_db() -> Db` : base en mémoire avec l'horloge fixe actuellement utilisée par `db_task_update.rs` ;
  - `pub fn new_task(title: &str, project_id: Option<ProjectId>) -> NewTask`.
- Si deux fichiers définissent une même fonction avec des corps différents, on garde les deux sous des noms distincts (par exemple `test_db_unclocked`) plutôt que de changer le comportement d'un test.

- [ ] **Étape 1 : noter le nombre de tests.** `cargo nextest run -p meute-core 2>&1 | tail -3` ; noter le total.
- [ ] **Étape 2 : créer `tests/common/mod.rs`, y déplacer les fonctions, remplacer les copies par `mod common; use common::*;`.**
- [ ] **Étape 3 : vérifier.** `cargo nextest run -p meute-core` : même total qu'à l'étape 1, tout au vert ; `git diff --stat` ne montre que des fichiers sous `tests/` ; aucune ligne `assert` n'apparaît dans le diff.
- [ ] **Étape 4 : vérification complète, puis commit.** `git commit -m "test(core): regroupe les utilitaires de test dans tests/common"`

---

### Task 2 : refonte de l'API des tâches (report R16)

**Fichiers :**
- Modifier : `crates/meute-core/src/task/status.rs`, `task/mod.rs`, `task/types.rs`, `db/tasks.rs`
- Modifier : `crates/meute/src/cli/task.rs`
- Test : `crates/meute-core/src/task/tests.rs`, `crates/meute-core/tests/db_tasks.rs` (nouveaux tests)

**Interfaces :**
- Produit :
  - `pub enum StatusKind { Todo, InProgress, Blocked, Review, Done }` (`Debug, Clone, Copy, PartialEq, Eq, Hash`), exporté par `meute_core::task` ;
  - `StatusKind::id(self) -> &'static str` (mêmes identifiants que `TaskStatus::id`) et `StatusKind::from_id(id: &str) -> Result<StatusKind>` (erreur `CoreError::Invalid("statut inconnu : {id}")`, texte identique à l'actuel) ;
  - `TaskStatus::kind(&self) -> StatusKind` ;
  - `TaskFilter.status: Option<StatusKind>` (remplace `Option<&'static str>`) ;
  - `Due` sérialisé et désérialisé sous la forme `{"kind": "date", "value": "2026-10-20"}` / `{"kind": "at", "value": "<RFC 3339>"}` via `#[serde(tag = "kind", content = "value", rename_all = "snake_case")]` ; `Task::serialize` sérialise `self.due` directement et la structure `DueJson` disparaît.
- Règle déplacée dans le cœur : `Db::list_tasks` inclut les tâches faites quand `filter.status == Some(StatusKind::Done)`, quel que soit `include_done`.

- [ ] **Étape 1 : écrire les tests qui échouent.**

```rust
// src/task/tests.rs
#[test]
fn status_kind_ids_round_trip_and_match_task_status() {
    for kind in [StatusKind::Todo, StatusKind::InProgress, StatusKind::Blocked, StatusKind::Review, StatusKind::Done] {
        assert_eq!(StatusKind::from_id(kind.id()).unwrap(), kind);
    }
    assert_eq!(TaskStatus::Blocked { reason: "x".into() }.kind(), StatusKind::Blocked);
    assert_eq!(TaskStatus::Done.kind().id(), TaskStatus::Done.id());
    assert!(matches!(StatusKind::from_id("bloqué"), Err(CoreError::Invalid(m)) if m == "statut inconnu : bloqué"));
}

#[test]
fn due_serde_shape_matches_task_json() {
    let d = Due::Date(jiff::civil::date(2026, 10, 20));
    assert_eq!(serde_json::to_value(d).unwrap(), serde_json::json!({"kind": "date", "value": "2026-10-20"}));
    let at: jiff::Timestamp = "2026-10-20T12:00:00Z".parse().unwrap();
    assert_eq!(serde_json::to_value(Due::At(at)).unwrap(), serde_json::json!({"kind": "at", "value": "2026-10-20T12:00:00Z"}));
    for due in [d, Due::At(at)] {
        let back: Due = serde_json::from_value(serde_json::to_value(due).unwrap()).unwrap();
        assert_eq!(back, due);
    }
}

// tests/db_tasks.rs
#[test]
fn done_status_filter_implies_done_tasks() {
    // une tâche ouverte et une tâche faite ; filtre { status: Some(StatusKind::Done), include_done: false }
    // => seule la tâche faite est renvoyée
}
```

Le test JSON existant de `Task` (forme `{kind, value}` de `due`) doit continuer à passer sans modification.

- [ ] **Étape 2 : constater l'échec** (`cargo nextest run -p meute-core`) : erreurs de compilation sur `StatusKind`, puis, une fois le type ajouté, échec de `due_serde_shape_matches_task_json` (forme externe actuelle `{"Date": …}`).
- [ ] **Étape 3 : implémenter.** Adapter `db_tasks.rs:143` (`status: Some("done")` → `Some(StatusKind::Done)`), seule modification autorisée d'un test existant. Dans la CLI, `list` utilise `StatusKind::from_id` et ne calcule plus `include_done` pour `done` ; le `TaskStatus::from_id(id, Some("-"))` jetable disparaît.
- [ ] **Étape 4 : vérifier.** Tous les tests passent, y compris les instantanés de la CLI sans les réaccepter ; `grep -rn 'Some("-")' crates/` ne renvoie rien.
- [ ] **Étape 5 : vérification complète, puis commit.** `git commit -m "refactor(core): StatusKind, filtre done dans le cœur et forme serde de Due"`

---

### Task 3 : modèle de session et table `sessions`

**Fichiers :**
- Créer : `crates/meute-core/src/session/mod.rs`, `session/types.rs`, `session/tests.rs`
- Créer : `crates/meute-core/src/db/sql/002_sessions.sql`, `crates/meute-core/src/db/sessions.rs`
- Modifier : `crates/meute-core/src/lib.rs`, `db/mod.rs`, `db/migrations.rs`, `crates/meute-core/Cargo.toml` (`cargo add uuid -p meute-core -F v4,serde`)
- Test : `crates/meute-core/tests/db_sessions.rs`

**Interfaces :**
- Produit (`meute_core::session`) :
  - `pub struct SessionId(pub uuid::Uuid)` (`Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize`), `SessionId::new() -> SessionId` (v4), `SessionId::parse(s: &str) -> Result<SessionId>` (`CoreError::Invalid("identifiant de session invalide : {s}")`), `Display` en forme hyphénée, `SessionId::short(&self) -> String` (8 premiers caractères) ;
  - `pub enum AgentKind { Claude, Bash }`, `id()` (`claude`, `bash`), `from_id()` ;
  - `pub enum SessionState` : exactement les variantes du § 6.1 (`Running, SubagentRunning, Compacting, PermissionRequested, WaitingInput, Idle, Exited { code: Option<i32> }, Unreachable, MaybeStuck, Unknown`), sérialisé avec `#[serde(tag = "kind", rename_all = "snake_case")]` (`{"kind":"exited","code":2}`) ;
  - `SessionState::id(&self) -> &'static str` (`running`, `subagent_running`, `compacting`, `permission_requested`, `waiting_input`, `idle`, `exited`, `unreachable`, `maybe_stuck`, `unknown`), `SessionState::from_parts(id: &str, code: Option<i32>) -> Result<SessionState>`, `SessionState::is_live(&self) -> bool` (faux pour `Exited` et `Unreachable` seulement) ;
  - `SessionState::label(&self) -> String`, textes exacts : `en cours`, `sous-agent`, `compactage`, `permission`, `attend ta réponse`, `inactive`, `terminée ({code})` ou `terminée`, `injoignable`, `bloquée ?`, `inconnu ?` (principe 4 : les états supposés portent un « ? ») ;
  - `pub struct Session { id: SessionId, agent: AgentKind, title: String, project_id: Option<ProjectId>, repo_id: Option<RepoId>, task_id: Option<TaskId>, cwd: PathBuf, state: SessionState, last_activity_at: Timestamp, created_at: Timestamp, ended_at: Option<Timestamp> }` (`Serialize`) ;
  - `pub struct NewSession { id: SessionId, agent: AgentKind, title: String, cwd: PathBuf, project_id: Option<ProjectId>, repo_id: Option<RepoId>, task_id: Option<TaskId>, state: SessionState }` ;
  - `pub struct RepoId(pub i64)` dans un nouveau module `meute_core::repo` (rempli à la Task 9) ;
  - `pub struct SessionFilter { pub include_ended: bool }` (`Default`).
- Produit (`Db`) :
  - `create_session(&mut self, new: NewSession) -> Result<Session>` : titre vide refusé (`Invalid("le titre ne peut pas être vide")`), `cwd` non UTF-8 refusé (`Invalid("chemin non UTF-8 : …")`), `created_at = last_activity_at = now` ;
  - `get_session(&self, id: SessionId) -> Result<Session>` (`NotFound { entity: "session", id }`) ;
  - `find_session(&self, prefix: &str) -> Result<Session>` : identifiant complet, ou préfixe d'au moins 4 caractères désignant une seule session ; plusieurs → `Invalid("identifiant de session ambigu : {prefix}")`, aucune ou moins de 4 caractères → `NotFound { entity: "session", id: prefix }` ;
  - `list_sessions(&self, filter: SessionFilter) -> Result<Vec<Session>>`, triées par `created_at` puis `id` ; sans `include_ended`, seulement les états vivants ;
  - `set_session_state(&mut self, id: SessionId, state: SessionState) -> Result<Session>` : met `last_activity_at = now` ; met `ended_at = now` quand la session passe d'un état vivant à un état non vivant, et ne le touche pas sinon ;
  - `data_version(&self) -> Result<i64>` (`PRAGMA data_version`, pour le rafraîchissement du § 4.5).

Migration `002_sessions.sql` :

```sql
CREATE TABLE sessions (
  id TEXT PRIMARY KEY CHECK (length(id) = 36),
  agent TEXT NOT NULL CHECK (agent IN ('claude','bash')),
  title TEXT NOT NULL CHECK (length(trim(title)) > 0),
  project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  repo_id INTEGER REFERENCES repos(id) ON DELETE SET NULL,
  task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
  cwd TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('running','subagent_running','compacting',
    'permission_requested','waiting_input','idle','exited','unreachable','maybe_stuck','unknown')),
  exit_code INTEGER CHECK (exit_code IS NULL OR state = 'exited'),
  last_activity_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  ended_at TEXT
);
CREATE INDEX sessions_state ON sessions(state);
```

- [ ] **Étape 1 : écrire les tests qui échouent.** Dans `session/tests.rs` : aller-retour `id`/`from_parts` pour chaque variante, `is_live` pour chaque variante (liste explicite, pas de boucle qui teste la fonction contre elle-même), chaque `label`, forme JSON `{"kind":"exited","code":2}` et `{"kind":"running"}`, `SessionId::parse` sur une chaîne invalide. Dans `tests/db_sessions.rs` (avec `tests/common`) :
  - `create_then_get_round_trips_every_field` ;
  - `list_excludes_ended_unless_asked` ;
  - `ended_at_is_set_once_when_leaving_live_states` (Running → Exited{Some(2)} pose `ended_at` à t1 ; Exited → Unreachable à t2 garde t1) ;
  - `find_session_by_unique_prefix_ambiguous_and_short` (deux identifiants fixes `aaaa1111-…` et `aaaa2222-…` : `aaaa1` trouve le premier, `aaaa` est ambigu, `aaa` est introuvable) ;
  - `data_version_changes_after_a_write_from_another_connection` (deux `Db::open` sur le même fichier) ;
  - `migrating_a_v1_file_keeps_tasks_and_backs_it_up` : base v1 créée avec `rusqlite_migration` et la seule migration 1 (copier `001_init.sql` via `include_str!`), une tâche insérée ; `Db::open` donne `schema_version() == 2`, la tâche est intacte et `meute.db.bak-1` existe.
- [ ] **Étape 2 : constater l'échec** (compilation, puis assertions).
- [ ] **Étape 3 : implémenter.** Mettre à jour `schema_version() == 1` → `2` dans les deux tests listés aux contraintes globales (exception autorisée n° 2), et le dire dans le message de commit.
- [ ] **Étape 4 : vérifier.** `cargo nextest run -p meute-core` au vert ; `cargo +1.85 check --workspace --all-targets` au vert (`uuid` compatible).
- [ ] **Étape 5 : vérification complète, puis commit.** `git commit -m "feat(core): modèle de session et table sessions (migration 2)"`

---

### Task 4 : règle de réconciliation (§ 5.4)

**Fichiers :**
- Créer : `crates/meute-core/src/session/reconcile.rs` (et ses tests dans `session/reconcile/tests.rs` si le fichier dépasse 300 lignes)
- Modifier : `crates/meute-core/src/session/mod.rs`

**Interfaces :**
- Consomme : `Session`, `SessionId`, `SessionState`, `AgentKind` (Task 3).
- Produit :
  - `pub struct PaneObservation { pub meute_id: String, pub dead: bool, pub exit_code: Option<i32> }` : un panneau qui porte `@meute_id`, tel que vu par tmux ;
  - `pub struct Reconciliation { pub updates: Vec<(SessionId, SessionState)>, pub orphans: Vec<String> }` ;
  - `pub fn reconcile(sessions: &[Session], panes: &[PaneObservation]) -> Reconciliation` (pure).
- Règles, pour chaque session **vivante** :
  - aucun panneau avec son identifiant → `Unreachable` ;
  - panneau mort → `Exited { code: exit_code }` ;
  - panneau vivant, agent `Bash`, état différent de `Running` → `Running` (§ 6.3 : Bash vaut `Running` tant que son panneau vit) ;
  - panneau vivant, agent `Claude` → aucune mise à jour (l'état vient des hooks, plan 3).
- Les sessions non vivantes ne sont jamais mises à jour (pas de relance ni de résurrection implicite, principe 5).
- Orphelins : identifiants de panneau qui ne correspondent à **aucune** session de la liste (vivante ou non), y compris les identifiants qui ne sont pas des UUID ; sans doublon, dans l'ordre des panneaux.
- `updates` et `orphans` sont vides quand rien ne change (pas d'écriture inutile en base).

- [ ] **Étape 1 : écrire les tests qui échouent.** Un test par règle : `missing_pane_makes_live_session_unreachable`, `dead_pane_gives_exited_with_code` (code 7), `dead_pane_without_status_gives_exited_none`, `live_bash_pane_restores_running_from_unknown`, `running_bash_with_live_pane_needs_no_update`, `claude_session_with_live_pane_is_untouched`, `ended_sessions_are_never_updated` (Exited dont le panneau a disparu → aucune mise à jour), `pane_of_an_ended_session_is_not_an_orphan`, `unknown_and_malformed_ids_are_orphans_once` (`"pas-un-uuid"` présent deux fois → une seule entrée).
- [ ] **Étape 2 : constater l'échec.**
- [ ] **Étape 3 : implémenter `reconcile`.**
- [ ] **Étape 4 : vérifier, puis faire la vérification complète.**
- [ ] **Étape 5 : commit.** `git commit -m "feat(core): réconciliation des sessions avec les panneaux tmux"`

---

### Task 5 : crate `meute-tmux` — client, version et serveur de test

**Fichiers :**
- Créer : `crates/meute-tmux/Cargo.toml` (`[lints] workspace = true`, dépendance `thiserror`, dev-dépendance `uuid` avec `v4`), `src/lib.rs`, `src/client.rs`, `src/version.rs`, `src/error.rs`
- Créer : `crates/meute-tmux/CLAUDE.md` :
  « Tests uniquement sur un serveur tmux jetable (`tests/common::TestServer`, socket `meute-test-<uuid>`, configuration `/dev/null`), tué par `Drop`. Ne jamais appeler tmux sans `-L`, ni viser le socket `meute`. »
- Créer : `crates/meute-tmux/tests/common/mod.rs`, `tests/client.rs`
- Modifier : `.github/workflows/ci.yml` (job `check` : étape `sudo apt-get update && sudo apt-get install -y tmux` avant `cargo nextest run`)

**Interfaces :**
- Produit :
  - `pub struct Tmux { socket: String, config_file: Option<PathBuf> }`, `Tmux::new(socket: impl Into<String>, config_file: Option<PathBuf>) -> Tmux`, `socket(&self) -> &str`, `config_file(&self) -> Option<&Path>` ;
  - `Tmux::command(&self) -> std::process::Command` : `tmux -L <socket> [-f <config>]`, sans autre argument (réutilisé pour `attach` à la Task 13) ;
  - `Tmux::run(&self, args: &[&str]) -> Result<String, TmuxError>` : stdout sans le saut de ligne final ; statut non nul → `TmuxError::Command { args, stderr }` ;
  - `Tmux::is_running(&self) -> Result<bool, TmuxError>`, `has_session(&self, name: &str) -> Result<bool, TmuxError>` (cible exacte `=<name>`), `kill_server(&self) -> Result<(), TmuxError>` ;
  - `Tmux::check_version(&self) -> Result<Option<TmuxVersion>, TmuxError>` : exécute `tmux -V` ; binaire absent → `NotInstalled` ; version lue inférieure à 3.2 → `TooOld { found }` ; version illisible (`tmux master`, `tmux openbsd-7.6`) → `Ok(None)`, acceptée ;
  - `pub struct TmuxVersion { pub major: u32, pub minor: u32 }` (`PartialOrd, Ord`), `pub const MIN_VERSION: TmuxVersion = TmuxVersion { major: 3, minor: 2 }`, `pub fn parse_version(output: &str) -> Option<TmuxVersion>` ;
  - `pub enum TmuxError` (`thiserror`), messages exacts :
    - `NotInstalled` : `tmux introuvable : meute a besoin de tmux 3.2 ou plus récent (par exemple : sudo apt install tmux)` ;
    - `TooOld { found: String }` : `tmux {found} est trop ancien : meute a besoin de tmux 3.2 ou plus récent` ;
    - `Command { args: String, stderr: String }` : `tmux {args} a échoué : {stderr}` ;
    - `Io(#[from] std::io::Error)` : `erreur d'entrée/sortie avec tmux` ;
    - `Parse(String)` : `sortie de tmux illisible : {0}`.
  - `tests/common::TestServer` : `TestServer::start() -> TestServer` crée un serveur `meute-test-<uuid>` avec `-f /dev/null` et une session `test` (`new-session -d -s test -x 200 -y 50`) ; `tmux(&self) -> &Tmux` ; `Drop` appelle `kill_server` en ignorant l'erreur ; `pub fn wait_until(what: &str, f: impl FnMut() -> bool)` (100 ms, échéance 10 s, panique avec `what`).

- [ ] **Étape 1 : écrire les tests qui échouent.**
  - `parse_version` : `"tmux 3.5a"` → 3.5, `"tmux 3.2"` → 3.2, `"tmux next-3.6"` → 3.6, `"tmux 2.9a"` → 2.9, `"tmux master"` → `None`, `""` → `None` ; plus une propriété `proptest` : `parse_version` ne panique jamais sur une chaîne quelconque.
  - comparaison : `TmuxVersion{3,1} < MIN_VERSION`, `TmuxVersion{3,10} > TmuxVersion{3,2}`.
  - intégration (`tests/client.rs`) : `start_run_and_kill` (`has_session("test")` vrai, `has_session("tes")` faux, puis après `kill_server`, `is_running()` faux) ; `failed_command_reports_stderr` (`run(&["kill-pane", "-t", "%999"])` → `Command` dont `stderr` n'est pas vide) ; `never_started_socket_is_not_running`.
  - `missing_binary_is_not_installed` : test unitaire d'une fonction privée `classify_spawn_error(err: io::Error) -> TmuxError` (`NotFound` → `NotInstalled`), sans dépendre du `PATH` de la machine.
- [ ] **Étape 2 : constater l'échec.**
- [ ] **Étape 3 : implémenter.** `TMUX` n'est **pas** retiré de l'environnement des commandes (`-L` prévaut ; seul l'attachement imbriqué le retire, Task 13).
- [ ] **Étape 4 : vérifier.** `cargo nextest run -p meute-tmux` ; `tmux -L meute ls` affiche toujours la même chose qu'avant les tests (aucun serveur `meute` créé).
- [ ] **Étape 5 : vérification complète, puis commit.** `git commit -m "feat(tmux): client tmux sur serveur dédié et contrôle de version"`

---

### Task 6 : panneaux tmux

**Fichiers :**
- Créer : `crates/meute-tmux/src/pane.rs`
- Modifier : `crates/meute-tmux/src/lib.rs`
- Test : `crates/meute-tmux/tests/panes.rs`

**Interfaces :**
- Consomme : `Tmux`, `TmuxError`, `TestServer` (Task 5).
- Produit :
  - `pub struct PaneId(pub String)` (`"%12"`, `Debug, Clone, PartialEq, Eq, Hash`, `Display`) ;
  - `pub struct PaneInfo { pub id: PaneId, pub session: String, pub window: String, pub meute_id: Option<String>, pub role: Option<String>, pub dead: bool, pub dead_status: Option<i32>, pub width: u16 }` (`window` = nom de la fenêtre ; option vide → `None`) ;
  - `pub fn parse_pane_line(line: &str) -> Result<PaneInfo, TmuxError>` : champs séparés par des tabulations, dans l'ordre du format `#{pane_id}\t#{session_name}\t#{window_name}\t#{@meute_id}\t#{@meute_role}\t#{pane_dead}\t#{pane_dead_status}\t#{pane_width}` ;
  - `Tmux::list_panes(&self) -> Result<Vec<PaneInfo>, TmuxError>` : `list-panes -a -F <format>` ; serveur absent (stderr contenant `no server running` ou `error connecting to`) → `Ok(vec![])` ; toute autre erreur est remontée ;
  - `pub struct Spawn { pub session: String, pub cwd: PathBuf, pub command: Vec<String>, pub env: Vec<(String, String)>, pub pane_options: Vec<(String, String)> }` ;
  - `Tmux::spawn_window(&self, spawn: &Spawn) -> Result<PaneId, TmuxError>` : `new-window -d -P -F '#{pane_id}' -t =<session>: -c <cwd> -e K=V … -- <command…>` si la session existe, sinon `new-session -d -s <session> -P -F '#{pane_id}' -c … -e … -- …` ; puis `set-option -p -t <pane> <nom> <valeur>` pour chaque option, dans l'ordre ;
  - `Tmux::set_pane_option(&self, pane: &PaneId, name: &str, value: &str)`, `set_global_option(&self, name: &str, value: &str)`, `swap_panes(&self, src: &PaneId, dst: &PaneId)` (`swap-pane -d -s src -t dst`), `select_pane(&self, pane: &PaneId)`, `send_keys(&self, pane: &PaneId, keys: &[&str])`, `kill_pane(&self, pane: &PaneId)`, `switch_client_to(&self, pane: &PaneId)` ; toutes renvoient `Result<(), TmuxError>`.

- [ ] **Étape 1 : écrire les tests qui échouent.**
  - `parse_pane_line` : ligne complète d'un panneau mort (`"%3\tmeute-bg\tw\t<uuid>\t\t1\t7\t80"` → `dead`, `dead_status == Some(7)`, `role == None`) ; ligne d'un panneau vivant (statut vide → `None`) ; ligne à 7 champs → `Err(Parse)` ; largeur non numérique → `Err(Parse)`.
  - `list_panes_on_never_started_socket_is_empty`.
  - `spawn_creates_bg_session_then_windows` : deux `spawn_window` dans `bg` (`sh -c 'sleep 3600'`) → deux panneaux de session `bg`, avec `@meute_id` posé.
  - `spawn_passes_cwd_and_env` : commande `sh -c 'pwd > "$OUT"; echo "$MEUTE_SESSION" >> "$OUT"; sleep 3600'`, `OUT` dans un `tempdir` passé par `env` ; attendre le fichier ; il contient le `cwd` demandé puis la valeur.
  - `remain_on_exit_keeps_dead_pane_with_status` : `sh -c 'exit 3'` avec l'option `remain-on-exit on` → (attente) le panneau est `dead` avec `dead_status == Some(3)`.
  - `meute_id_follows_the_pane_through_swap` (constat du spike S4) : deux panneaux dans deux sessions, chacun avec son `@meute_id` ; après `swap_panes`, chaque identifiant est porté par le même `PaneId` qu'avant, mais dans l'autre session.
  - `kill_pane_removes_it`.
- [ ] **Étape 2 : constater l'échec.**
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérifier, puis faire la vérification complète.**
- [ ] **Étape 5 : commit.** `git commit -m "feat(tmux): panneaux, options de pane et échange"`

---

### Task 7 : disposition `meute` (§ 5.1 et 5.2)

**Fichiers :**
- Créer : `crates/meute-tmux/src/layout.rs`, `crates/meute-tmux/src/conf.rs`
- Modifier : `crates/meute-tmux/src/lib.rs`, `Cargo.toml` (dev-dépendance `insta`)
- Test : `crates/meute-tmux/tests/layout.rs`, instantané `tests/snapshots/layout__generated_config.snap`

**Interfaces :**
- Consomme : Tasks 5 et 6.
- Produit :
  - constantes `MAIN_SESSION = "meute"`, `MAIN_WINDOW = "main"`, `BG_SESSION = "meute-bg"`, `ID_OPTION = "@meute_id"`, `ROLE_OPTION = "@meute_role"`, `ROLE_BOARD = "board"`, `ROLE_WELCOME = "welcome"`, `STATUS_OPTION = "@meute_status"` ;
  - `pub struct Keys { pub focus_board: String, pub focus_main: String }` ;
  - `pub struct LayoutSpec { pub board_width: u16, pub narrow_threshold: u16, pub board_command: Vec<String>, pub welcome_command: Vec<String>, pub sync_command: Vec<String>, pub keys: Keys }` ;
  - `pub fn render_config(spec: &LayoutSpec) -> String` ;
  - `pub fn is_narrow(width: u16, threshold: u16) -> bool` (`width < threshold`) ;
  - `pub struct Layout { pub board: PaneId, pub main: Option<PaneId>, pub width: u16, pub zoomed: bool }` ;
  - `pub fn find_layout(tmux: &Tmux) -> Result<Option<Layout>, TmuxError>` : `None` si aucun panneau `@meute_role=board` vivant dans `meute:main` ; `main` = le premier autre panneau de cette fenêtre ; `width` et `zoomed` lus par `display-message -p -t =meute:main '#{window_width}\t#{window_zoomed_flag}'` ;
  - `pub fn ensure_layout(tmux: &Tmux, spec: &LayoutSpec) -> Result<Layout, TmuxError>`.

Contenu exact de la configuration générée (chemin de `sync_command` mis entre apostrophes pour `sh`, puis échappé pour une chaîne tmux entre guillemets : `\`, `"` et `$` précédés d'une barre oblique inverse) :

```
# Généré par meute : ce fichier est réécrit à chaque lancement, ne pas le modifier.
set -g status-left "[meute] "
set -g status-right "#{@meute_status}"
set -g status-right-length 80
bind -n M-p switch-client -t =meute:main \; select-pane -t =meute:main.{right}
bind -n M-o select-pane -t =meute:main.{left}
set-hook -g client-attached "run-shell -b \"'/chemin/meute' 'layout' 'sync'\""
set-hook -g client-resized "run-shell -b \"'/chemin/meute' 'layout' 'sync'\""
```

(`M-p` et `M-o` viennent de `spec.keys` ; `/chemin/meute` de `spec.sync_command`.) Si la forme d'échappement ci-dessus n'est pas acceptée par tmux 3.5a, l'implémenteur choisit la forme la plus simple qui l'est, le test « sourcé sans erreur » faisant foi, et la note dans son rapport.

Algorithme de `ensure_layout` :
1. si la session `meute` n'existe pas : `new-session -d -s meute -n main -x 200 -y 50 -- <welcome_command>` (rôle `welcome`), puis `split-window -h -l <board_width> -t <welcome> -- <board_command>` (rôle `board`), puis `select-pane` sur le tableau ;
2. sinon : pas de tableau vivant → `split-window -h -l <board_width> -t <main> -- <board_command>` (rôle `board`) ; pas de panneau principal → `split-window -h -b -t <board> -- <welcome_command>` (rôle `welcome`) ;
3. mode étroit : `is_narrow(width, threshold)` et non zoomé → `resize-pane -Z -t <board>` ; large et zoomé → `resize-pane -Z -t <board>` ; large → `resize-pane -t <board> -x <board_width>` ;
4. renvoyer `find_layout` (forcément `Some`).

- [ ] **Étape 1 : écrire les tests qui échouent.** Dans tous les tests de disposition, `board_command` et `welcome_command` valent `["sh", "-c", "sleep 3600"]` et le serveur de test n'a pas de session `meute` au départ.
  - `generated_config` : instantané `insta` de `render_config` avec `sync_command = ["/opt/meute/bin/meute", "layout", "sync"]`, relu ligne par ligne contre le bloc ci-dessus ;
  - `generated_config_is_accepted_by_tmux` : la configuration, avec un chemin contenant une espace et une apostrophe, écrite dans un fichier puis `source-file` sur le serveur de test → `Ok` ; `list-keys -T root` contient `M-p` et `M-o` ;
  - `is_narrow` : `(119, 120)` vrai, `(120, 120)` faux ;
  - `fresh_server_gets_board_and_welcome` : deux panneaux dans `meute:main`, rôles `board` et `welcome`, largeur du tableau 60, `zoomed` faux ;
  - `ensure_is_idempotent` : un second appel renvoie les mêmes `PaneId` et la fenêtre a toujours deux panneaux ;
  - `killed_main_pane_is_replaced_by_welcome` (point de vigilance 3) : `kill_pane(main)` → `ensure_layout` → deux panneaux, nouveau rôle `welcome`, tableau à 60 colonnes ;
  - `killed_board_is_recreated` ;
  - `narrow_window_zooms_board_and_wide_unzooms` : `resize-window -t =meute:main -x 100` → `ensure_layout` → `zoomed` ; `resize-window -x 200` → `ensure_layout` → non zoomé, tableau à 60.
- [ ] **Étape 2 : constater l'échec.**
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérifier ; relire l'instantané avec `cargo insta review`, jamais `accept` à l'aveugle.**
- [ ] **Étape 5 : vérification complète, puis commit.** `git commit -m "feat(tmux): disposition meute, configuration générée et mode étroit"`

---

### Task 8 : crate `meute-git` — découverte des dépôts (§ 10)

**Fichiers :**
- Créer : `crates/meute-git/Cargo.toml` (`[lints] workspace = true`, aucune dépendance ; dev-dépendances `tempfile`, `proptest` seulement si utile), `src/lib.rs`, `src/discover.rs`, `src/kind.rs`
- Test : `crates/meute-git/tests/discover.rs`

**Interfaces :**
- Produit :
  - `pub enum RepoKind { Rust, Angular, Node, FastApi, Python }`, `id(self) -> &'static str` (`rust`, `angular`, `node`, `fastapi`, `python`) ;
  - `pub fn detect_kind(dir: &Path) -> Option<RepoKind>`, première règle qui s'applique : `Cargo.toml` → Rust ; `angular.json` → Angular ; `package.json` → Node ; `pyproject.toml` ou `requirements.txt` dont le texte contient `fastapi` → FastApi ; `pyproject.toml`, `requirements.txt` ou `setup.py` → Python ; sinon `None` ;
  - `pub struct DiscoveredRepo { pub path: PathBuf, pub name: String, pub kind: Option<RepoKind>, pub worktrees: Vec<PathBuf> }` ;
  - `pub const DEFAULT_DEPTH: usize = 3;`
  - `pub fn discover(roots: &[PathBuf], max_depth: usize) -> Vec<DiscoveredRepo>` : triés par chemin, sans doublon ;
  - `pub fn expand_home(root: &str, home: Option<&Path>) -> PathBuf` (`~` et `~/…` seulement).
- Règles de parcours :
  - on examine la racine elle-même (profondeur 0) et ses sous-dossiers jusqu'à `max_depth` inclus ;
  - `.git` **dossier** → dépôt principal ; on ne descend pas dans un dépôt ;
  - `.git` **fichier** dont la ligne `gitdir: <chemin>` désigne `<…>/.git/worktrees/<nom>` (chemin absolu, ou relatif au dossier du worktree) → worktree, rattaché au dépôt dont le `.git` est `<…>/.git` ; il n'apparaît jamais comme dépôt ; un worktree dont le dépôt principal n'a pas été trouvé est ignoré ;
  - tout autre `.git` fichier (sous-module) → ignoré ;
  - dossiers cachés (nom commençant par `.`), `node_modules` et `target` non parcourus ;
  - liens symboliques jamais suivis ; dossiers illisibles, racines absentes et chemins non UTF-8 ignorés sans erreur ;
  - les chemins sont comparés après `canonicalize`.

- [ ] **Étape 1 : écrire les tests qui échouent** (arborescences créées dans un `tempdir`, `.git` simulés à la main, sans appeler `git`) :
  - `detect_kind` : un cas par règle, plus `pyproject.toml` contenant `fastapi` → FastApi et sans → Python, et `package.json` + `angular.json` → Angular ;
  - `finds_repos_up_to_depth_three` : dépôts à `r/a`, `r/x/b`, `r/x/y/c`, `r/x/y/z/d` → `a`, `b`, `c` seulement ;
  - `root_itself_can_be_a_repo` ;
  - `does_not_descend_into_repos` : `r/a/.git` et `r/a/sub/.git` → seulement `a` ;
  - `worktrees_attach_to_their_main_repo` : `r/meute/.git/worktrees/feat` et `r/meute.worktrees/feat/.git` (`gitdir: <abs>/r/meute/.git/worktrees/feat`) → un seul dépôt `meute` dont `worktrees` contient `r/meute.worktrees/feat` ; même test avec un `gitdir` relatif ;
  - `submodule_git_file_is_ignored` ;
  - `missing_root_and_symlink_loop_are_harmless` (point de vigilance 5) : racine absente → vide ; `r/loop -> r` et un dépôt `r/a` → `a` une seule fois, sans blocage ;
  - `hidden_node_modules_and_target_are_skipped` ;
  - `expand_home` : `"~"`, `"~/git"`, `"/abs"`, `"~autre"` (inchangé), et `home == None` (inchangé).
- [ ] **Étape 2 : constater l'échec.**
- [ ] **Étape 3 : implémenter** avec `std::fs::read_dir` et `symlink_metadata`, sans dépendance.
- [ ] **Étape 4 : vérifier, puis faire la vérification complète.**
- [ ] **Étape 5 : commit.** `git commit -m "feat(git): découverte des dépôts et rattachement des worktrees"`

---

### Task 9 : dépôts en base et `meute repo list`

**Fichiers :**
- Créer : `crates/meute-core/src/repo.rs` (compléter le module créé à la Task 3), `crates/meute-core/src/db/repos.rs`
- Créer : `crates/meute/src/cli/repo.rs`, `crates/meute/src/repos.rs`
- Modifier : `crates/meute/src/cli/mod.rs`, `crates/meute/src/app.rs`, `crates/meute/Cargo.toml` (dépendance `meute-git`)
- Test : `crates/meute-core/tests/db_repos.rs`, `crates/meute/tests/cli_repos.rs`

**Interfaces :**
- Consomme : `RepoId` (Task 3), `discover`, `expand_home`, `DEFAULT_DEPTH`, `RepoKind::id` (Task 8).
- Produit :
  - `pub struct Repo { pub id: RepoId, pub path: PathBuf, pub name: String, pub kind: Option<String>, pub discovered_at: Timestamp }` (`Serialize`) et `pub struct NewRepo { pub path: PathBuf, pub name: String, pub kind: Option<String> }` ;
  - `Db::sync_repos(&mut self, found: &[NewRepo]) -> Result<Vec<Repo>>` : une transaction ; insère les nouveaux chemins (`discovered_at = now`), met à jour `name` et `kind` des chemins connus ; **ne supprime jamais** un dépôt absent (principe 5) ; renvoie `list_repos()` ;
  - `Db::list_repos(&self) -> Result<Vec<Repo>>`, triés par nom (sans casse) puis chemin ;
  - `App` gagne `pub config: Config` et `pub paths: Paths` (conservés par `App::init`, qui les lit déjà) ;
  - `crate::repos::scan(app: &mut App) -> anyhow::Result<Vec<Repo>>` : `expand_home` de chaque `config.repos.roots` avec `$HOME`, `discover(…, DEFAULT_DEPTH)`, conversion en `NewRepo`, `sync_repos` ;
  - CLI `meute repo list [--json]` : lance `scan`, puis une ligne par dépôt `{name}  {kind ou -}  {chemin, avec $HOME remplacé par ~}` ; `--json` : le tableau de `Repo`.

- [ ] **Étape 1 : écrire les tests qui échouent.**
  - core : `sync_inserts_then_updates_without_deleting` (synchroniser `a`, `b` ; puis `a` avec un autre `kind` seul → deux dépôts, `a` mis à jour, `discovered_at` de `a` inchangé, `b` toujours là) ; `list_is_sorted_by_name_case_insensitively`.
  - CLI (`assert_cmd`, `HOME` et `XDG_*` dans un `tempdir`, configuration `repos.roots = ["<tmp>/git"]` posée par `meute config set`) : `repo_list_scans_configured_roots` (deux dépôts simulés `api` avec `Cargo.toml` et `front` avec `package.json` → sortie exacte `api  rust  ~/git/api` puis `front  node  ~/git/front`) ; `repo_list_json_is_an_array_of_repos`.
- [ ] **Étape 2 : constater l'échec.**
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérifier, puis faire la vérification complète.**
- [ ] **Étape 5 : commit.** `git commit -m "feat: dépôts découverts enregistrés en base et meute repo list"`

---

### Task 10 : crate `meute-tui` — tableau de bord minimal

**Fichiers :**
- Créer : `crates/meute-tui/Cargo.toml` (`[lints] workspace = true`, dépendances `meute-core` et `ratatui` par `cargo add`, dev-dépendance `insta`), `src/lib.rs`, `src/board.rs` (état et touches), `src/render.rs`, `src/run.rs`
- Test : `crates/meute-tui/src/board/tests.rs`, `crates/meute-tui/tests/render.rs` et ses instantanés

**Interfaces :**
- Consomme : `Session`, `SessionId`, `SessionState::{label, is_live}`, `Repo`, `RepoId` (Tasks 3 et 9).
- Produit :
  - `pub struct SessionRow { pub session: Session, pub has_pane: bool, pub displayed: bool }` ;
  - `pub struct BoardData { pub sessions: Vec<SessionRow>, pub repos: Vec<Repo>, pub orphans: Vec<String>, pub home: Option<PathBuf> }` ;
  - `pub enum BoardAction { Show(SessionId), LaunchBash { cwd: PathBuf, repo_id: Option<RepoId> }, Stop(SessionId) }` ;
  - `pub struct Board`, `Board::new(data: BoardData) -> Board`, `set_data(&mut self, data: BoardData)` (conserve la ligne sélectionnée par identité de session ou de dépôt ; sinon borne l'index), `on_key(&mut self, key: KeyEvent) -> Option<BoardAction>`, `set_error(&mut self, message: String)`, `render(&self, frame: &mut Frame)` ;
  - `pub trait BoardBackend { fn load(&mut self) -> Result<Option<BoardData>, String>; fn perform(&mut self, action: BoardAction) -> Result<(), String>; }` (`load` renvoie `None` si rien n'a changé) ;
  - `pub fn run_board(backend: &mut dyn BoardBackend) -> std::io::Result<()>` : `ratatui::init()` / `ratatui::restore()` (restauration aussi en cas d'erreur), boucle : attente d'un événement 250 ms au plus, `load`, touche → `on_key` → `perform` ; une erreur de `load` ou `perform` est affichée par `set_error` ; `Ctrl+C` quitte.
- Contenu affiché (textes exacts) :
  - ligne de titre : `meute` ;
  - section `Sessions` : les sessions vivantes, puis les sessions terminées dont le panneau existe encore (`has_pane`) ; une ligne par session : `▶` si `displayed`, le titre, `state.label()`, le `cwd` avec `home` remplacé par `~` ; sans session : `Aucune session. Choisissez un dépôt et appuyez sur n.` ;
  - section `Dépôts` : `{name}` suivi de ` ({kind})` si le type est connu ;
  - section `Orphelins`, seulement s'il y en a : un identifiant par ligne ;
  - pied : `↑↓ choisir · Entrée afficher · n nouveau Bash · x arrêter` ; en confirmation : `Arrêter « {titre} » ? o : oui · autre touche : non` ; après une erreur : `Erreur : {message}` jusqu'à la touche suivante.
- Touches : `↑`/`k` et `↓`/`j` parcourent une liste unique (sessions puis dépôts) ; `Entrée` sur une session → `Show`, sur un dépôt → `LaunchBash` du dépôt ; `n` sur un dépôt → `LaunchBash` du dépôt, sur une session → `LaunchBash { cwd: session.cwd, repo_id: session.repo_id }` ; `x` sur une session → confirmation, puis `o` → `Stop`, toute autre touche annule sans action.

- [ ] **Étape 1 : écrire les tests qui échouent.**
  - touches : `enter_on_session_shows_it`, `enter_and_n_on_repo_launch_bash_there`, `n_on_session_launches_in_its_cwd`, `x_then_o_stops`, `x_then_other_key_cancels`, `x_on_repo_does_nothing`, `navigation_is_bounded`, `selection_survives_reordering` (la session sélectionnée passe de la 1ʳᵉ à la 2ᵉ position après `set_data` et reste sélectionnée) ;
  - rendu (`TestBackend` + `insta`, spécification § 17) : `board_60_columns` (deux sessions dont une affichée et une `terminée (2)` avec panneau, deux dépôts, un orphelin) ; `board_100_columns` (même données, mode étroit en plein écran) ; `board_empty` ; `board_confirming_stop` ; `board_with_error`. Les données de test utilisent des `SessionId` et des dates fixes.
- [ ] **Étape 2 : constater l'échec.**
- [ ] **Étape 3 : implémenter.** `run_board` n'est pas testé automatiquement (terminal réel) : il reste mince, toute la logique est dans `Board`.
- [ ] **Étape 4 : vérifier ; relire chaque instantané ligne par ligne contre la liste « Contenu affiché ».** `cargo +1.85 check --workspace --all-targets` au vert (version de `ratatui`).
- [ ] **Étape 5 : vérification complète, puis commit.** `git commit -m "feat(tui): tableau de bord minimal des sessions et des dépôts"`

---

### Task 11 : environnement tmux du binaire, lancement Bash, `session new` et `session list`

**Fichiers :**
- Créer : `crates/meute/src/tmux_env.rs`, `crates/meute/src/sessions/mod.rs`, `sessions/launch.rs`, `sessions/refresh.rs`, `crates/meute/src/cli/session.rs`
- Modifier : `crates/meute-core/src/config/mod.rs` (section `[keys]`), `crates/meute/src/cli/mod.rs`, `crates/meute/Cargo.toml` (dépendances `meute-tmux` et `meute-tui`)
- Créer : `crates/meute/CLAUDE.md` : « Les tests qui touchent à tmux définissent `MEUTE_TMUX_SOCKET=meute-test-<uuid>` et `SHELL=/bin/sh`, et tuent ce serveur à la fin (garde de `tests/support`). »
- Test : `crates/meute-core/src/config/tests.rs`, `crates/meute/tests/cli_sessions.rs`, `crates/meute/tests/support/mod.rs` (nouvelles fonctions)

**Interfaces :**
- Consomme : Tasks 3, 4, 6, 7 et 9.
- Produit :
  - configuration : `pub struct KeysConfig { pub focus_board: String, pub focus_main: String }` (défauts `M-p`, `M-o`) dans `Config.keys` ; `DEFAULT_CONFIG` gagne, après `[ui]` :

    ```toml
    [keys]
    # Raccourcis globaux, sans préfixe tmux (M- = Alt).
    focus_board = "M-p"
    focus_main = "M-o"
    ```

  - `pub struct TmuxEnv { pub tmux: Tmux, pub spec: LayoutSpec }` et `TmuxEnv::open(app: &App) -> anyhow::Result<TmuxEnv>` : socket depuis `MEUTE_TMUX_SOCKET` (défaut `meute`), `tmux.check_version()?`, `LayoutSpec` construite depuis `config.ui` et `config.keys` avec `board_command = [exe, "board"]`, `welcome_command = [exe, "welcome"]`, `sync_command = [exe, "layout", "sync"]` (`exe = std::env::current_exe()`), puis écriture de `render_config` dans `<state_dir>/tmux.conf`, passé à `Tmux::new` ;
  - `pub struct LaunchBash { pub cwd: PathBuf, pub title: Option<String>, pub repo_id: Option<RepoId> }` ;
  - `sessions::launch_bash(app: &mut App, env: &TmuxEnv, req: LaunchBash) -> anyhow::Result<Session>` : `cwd` doit être un dossier existant, sinon `dossier introuvable : {cwd}` **avant** toute écriture ; titre par défaut : nom du dossier ; `SessionId::new()` ; `spawn_window` dans `meute-bg` avec la commande `[$SHELL]` (`/bin/sh` si `SHELL` est absente), l'environnement `MEUTE_SESSION=<id>` et les options de pane `@meute_id=<id>` puis `remain-on-exit=on` ; puis `create_session` à l'état `Running` ; si l'écriture en base échoue, le panneau est tué et l'erreur remontée ;
  - `pub struct Snapshot { pub sessions: Vec<SessionRow>, pub orphans: Vec<String> }` (`SessionRow` de `meute-tui`) ;
  - `sessions::refresh(app: &mut App, env: &TmuxEnv) -> anyhow::Result<Snapshot>` : `let panes = env.tmux.list_panes()?;` (une erreur arrête tout avant la moindre écriture : point de vigilance 1), puis `sessions::apply_refresh(app: &mut App, panes: &[PaneInfo]) -> anyhow::Result<Snapshot>` : observations des panneaux qui portent `@meute_id`, `list_sessions(include_ended: true)`, `reconcile`, `set_session_state` pour chaque mise à jour, puis lignes : sessions vivantes et sessions dont un panneau existe ; `displayed` vrai si le panneau est dans la session `meute` ;
  - CLI `meute session new [--cwd <dossier>] [--title <titre>] [--kind bash]` (`--kind` n'accepte que `bash` dans ce plan, valeur par défaut ; `--cwd` vaut par défaut le dossier courant) ; sortie : `Lancée : {short_id} {titre} ({cwd})` ;
  - CLI `meute session list [--all] [--json]` : `refresh`, puis une ligne par session `{short_id}  {titre}  {state.label()}  {cwd avec ~}` (`--all` : aussi les sessions terminées sans panneau), puis une ligne `orphelin : {id}` par orphelin ; `--json` : `{"sessions": [Session…], "orphans": […]}`.

- [ ] **Étape 1 : écrire les tests qui échouent.**
  - config : `default_config_has_keys_section` (`config_get("keys.focus_board") == "M-p"`) ; l'instantané ou le test existant du fichier par défaut, s'il échoue parce que `[keys]` a été ajouté, est signalé et non réaccepté en silence (c'est un changement voulu, à relire).
  - `tests/support` : `pub struct TmuxGuard` (socket `meute-test-<uuid>`, `kill-server` au `Drop`), `pub fn meute_tmux(tmp, guard) -> Command` (comme `meute` avec en plus `MEUTE_TMUX_SOCKET` et `SHELL=/bin/sh`).
  - `cli_sessions.rs` :
    - `new_launches_bash_in_bg_with_identity` : `session new --cwd <tmp>/w --title essai` → succès ; `tmux -L <socket> list-panes -a -F '#{session_name} #{@meute_id} #{pane_current_path}'` contient `meute-bg <id> <tmp>/w` ; `session list --json` contient une session `bash`, `running`, titre `essai` ;
    - `new_with_missing_cwd_fails_and_writes_nothing` (message `dossier introuvable : …`, aucune session en base, aucun serveur démarré) ;
    - `exited_shell_is_reported_with_its_code` (point de vigilance 2) : `send-keys -t <pane> 'exit 7' Enter`, attente du panneau mort, `session list` affiche `terminée (7)` ;
    - `killed_pane_is_unreachable` (point de vigilance 2) ;
    - `list_without_server_marks_sessions_unreachable` (point de vigilance 1) : sessions créées directement en base avec des identifiants fixes, aucun serveur → instantané `insta` de `session list` (toutes `injoignable`) ;
    - `orphan_pane_is_listed` : panneau créé à la main dans `meute-bg` avec un `@meute_id` inconnu → ligne `orphelin : <id>`.
  - tests unitaires de `apply_refresh` dans `sessions/refresh.rs` (base en mémoire, `PaneInfo` construits à la main) : `panel_in_meute_session_is_displayed`, `ended_session_with_dead_pane_is_listed`, `ended_session_without_pane_is_hidden`. Le cas « tmux en échec » est garanti par la structure (`?` avant `apply_refresh`) et par le test de classement des erreurs de la Task 6.
- [ ] **Étape 2 : constater l'échec.**
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérifier ; `tmux -L meute ls` n'a pas changé.**
- [ ] **Étape 5 : vérification complète, puis commit.** `git commit -m "feat: sessions Bash dans meute-bg, réconciliation et meute session new/list"`

---

### Task 12 : afficher et arrêter une session (§ 5.1, 6.5)

**Fichiers :**
- Créer : `crates/meute/src/sessions/show.rs`, `crates/meute/src/sessions/stop.rs`
- Modifier : `crates/meute/src/cli/session.rs`, `crates/meute/src/sessions/mod.rs`
- Test : `crates/meute/tests/cli_session_show_stop.rs`

**Interfaces :**
- Consomme : `TmuxEnv`, `refresh` (Task 11), `find_layout`, `ensure_layout`, `ROLE_WELCOME`, `STATUS_OPTION` (Task 7).
- Produit :
  - `sessions::show(app: &mut App, env: &TmuxEnv, id: SessionId) -> anyhow::Result<()>` :
    1. `find_layout` ; absente → erreur `meute n'est pas ouvert : lancez « meute » d'abord` ;
    2. panneau portant l'identifiant ; absent → `session injoignable : {titre}` ;
    3. disposition zoomée (mode étroit, § 5.2) → `switch_client_to(panneau)` et fin ;
    4. panneau déjà dans la zone principale → `select_pane` seulement (point de vigilance 4) ;
    5. sinon `swap_panes(panneau, main)` ; si l'ancien panneau principal avait le rôle `welcome`, il est tué ; puis `select_pane(panneau)` et `set_global_option(STATUS_OPTION, "▶ {titre}")` ;
  - `sessions::stop(app: &mut App, env: &TmuxEnv, id: SessionId, grace: Duration) -> anyhow::Result<Session>` : si le panneau est vivant, `send_keys(["C-c"])` puis attente (100 ms) qu'il meure ou disparaisse, `grace` au plus ; s'il existe encore, `kill_pane` ; une session vivante passe à `Exited { code }` (code du panneau mort, sinon `None`) ; une session déjà terminée garde son état ; si une disposition existe, `ensure_layout` la répare (point de vigilance 3) ;
  - `pub const STOP_GRACE: Duration = Duration::from_secs(5);` (§ 6.5) ;
  - CLI `meute session show <id>` (identifiant ou préfixe, via `find_session`) ;
  - CLI `meute session stop <id> [--yes]` : sans `--yes`, question `Arrêter la session « {titre} » ? [o/N] ` sur stderr et lecture d'une ligne ; `o`, `oui`, `y` ou `yes` (sans casse) confirment, toute autre réponse affiche `Annulé.` et sort avec le code 0 ; après l'arrêt : `Arrêtée : {short_id} {titre}`.

- [ ] **Étape 1 : écrire les tests qui échouent.** Chaque test crée la disposition avec `meute_tmux::ensure_layout` sur le socket de test, avec `board_command` et `welcome_command` à `["sh", "-c", "sleep 3600"]` (le vrai tableau n'existe qu'à la Task 13).
  - `show_swaps_session_into_main_and_drops_welcome` : après `session show`, le panneau principal de `meute:main` porte l'identifiant ; plus aucun panneau `welcome` sur le serveur ; `@meute_status` vaut `▶ {titre}` ;
  - `show_second_session_sends_first_back_to_bg` : A puis B → B en principal, A dans `meute-bg`, le panneau de A inchangé ;
  - `show_displayed_session_is_a_no_op_swap` : `show` A deux fois → succès, mêmes panneaux qu'après le premier appel ;
  - `show_without_layout_fails_with_hint` ;
  - `stop_with_yes_kills_and_marks_exited` : `SHELL` vaut un script `exec sleep 3600` (meurt sur `C-c`) → arrêt en moins de 5 s, état `terminée`, panneau absent ;
  - `stop_displayed_session_restores_welcome` (point de vigilance 3) : A affichée, `stop A --yes` → `meute:main` a de nouveau deux panneaux, dont un `welcome`, tableau à 60 colonnes ;
  - `stop_without_confirmation_cancels` : stdin `n\n` → `Annulé.`, la session est toujours `en cours` ;
  - test unitaire dans `stop.rs` : un shell qui ignore `SIGINT` (`sh -c "trap '' INT; sleep 3600"`) est tué après une `grace` de 200 ms et la session passe à `Exited { code: None }`.
- [ ] **Étape 2 : constater l'échec.**
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérifier, puis faire la vérification complète.**
- [ ] **Étape 5 : commit.** `git commit -m "feat: afficher et arrêter une session (swap-pane, C-c puis kill)"`

---

### Task 13 : `meute`, `meute layout sync`, `meute welcome` et `meute board`

**Fichiers :**
- Créer : `crates/meute/src/cli/layout.rs`, `crates/meute/src/attach.rs`, `crates/meute/src/board.rs`, `crates/meute/src/welcome.rs`
- Modifier : `crates/meute/src/cli/mod.rs`, `crates/meute/src/main.rs` (`error_chain` déplacée dans un module partagé, `crates/meute/src/errors.rs`, pour être réutilisée par `board.rs`)
- Test : `crates/meute/tests/cli_layout.rs`, `crates/meute/tests/board_e2e.rs`

**Interfaces :**
- Consomme : tout ce qui précède.
- Produit :
  - `meute layout sync` (commande cachée, `#[command(hide = true)]`) : `TmuxEnv::open` ; si le serveur tourne, `source-file <tmux.conf>` ; puis `ensure_layout` ;
  - `meute` sans sous-commande : `layout sync`, puis attachement ; si `TMUX` est définie, avertissement sur stderr, texte exact :
    `Avertissement : meute s'ouvre dans votre tmux actuel. Si celui-ci utilise déjà {focus_board} ou {focus_main}, changez-les dans la section [keys] de {chemin de config.toml}.` ;
  - `attach::attach_command(env: &TmuxEnv, nested: bool) -> std::process::Command` : `env.tmux.command()` + `attach-session -t =meute:main`, avec `env_remove("TMUX")` si `nested` (§ 5.3) ; l'appelant l'exécute avec les entrées-sorties héritées et transforme un statut non nul en erreur `l'attachement à tmux a échoué` ;
  - `meute welcome` (cachée) : affiche `welcome::text(keys)` puis attend indéfiniment (`std::thread::park` en boucle) ; texte exact :

    ```
    meute

    Choisissez une session dans le tableau de bord et appuyez sur Entrée.
    {focus_board} : tableau de bord · {focus_main} : zone principale
    ```

  - `meute board` : `repos::scan` une fois au démarrage, puis `run_board` avec un `BoardBackend` du binaire :
    - `load` : relit tout (`refresh` + `list_repos`) au premier appel, puis quand `data_version` a changé ou que 2 s se sont écoulées depuis la dernière lecture de tmux (§ 4.5), sinon `None` ;
    - `perform` : `Show` → `show` ; `LaunchBash` → `launch_bash` puis `show` de la nouvelle session ; `Stop` → `stop` avec `STOP_GRACE` ; les erreurs sont converties en texte (`error_chain` de `main.rs`).

- [ ] **Étape 1 : écrire les tests qui échouent.**
  - unitaires : `attach_command_targets_main_window` (arguments `-L <socket> -f <conf> attach-session -t =meute:main`) ; `nested_attach_removes_tmux_variable` (`get_envs()` contient `("TMUX", None)`) ; `welcome_text_uses_configured_keys`.
  - `cli_layout.rs` : `layout_sync_creates_board_and_welcome` (panneaux `board` et `welcome` dans `meute:main`, la commande du panneau de tableau est `meute board`, vérifiée par `#{pane_start_command}`) ; `layout_sync_is_idempotent` ; `layout_sync_zooms_when_narrow` (`resize-window -x 100`, puis `layout sync` → `window_zoomed_flag` vaut 1) ; `generated_conf_is_written_to_state_dir`.
  - `board_e2e.rs` (le vrai tableau dans le vrai panneau) : `layout sync`, puis `session new --cwd <tmp>/w --title essai` ; attendre que `capture-pane -p -t <board>` contienne `essai` ; `send-keys -t <board> Enter` ; attendre que le panneau principal porte l'identifiant de la session et qu'il n'existe plus de panneau `welcome`.
- [ ] **Étape 2 : constater l'échec.**
- [ ] **Étape 3 : implémenter.** `meute` sans argument ne retournait rien au plan 1 : aucun test existant ne l'appelle (`cli_basics.rs` teste `--version`) ; si un test existant échoue, s'arrêter et le signaler.
- [ ] **Étape 4 : vérifier, puis essai manuel** (à noter dans le rapport, avec le résultat de chaque point) : `cargo run --bin meute` dans un terminal de 200 colonnes → disposition, tableau à droite ; `n` sur un dépôt → nouvelle session Bash affichée ; `M-p` / `M-o` changent le focus ; `x` puis `o` arrête la session et le panneau d'accueil revient ; `prefix d` détache, `meute` rattache et tout est là (critère n° 3) ; terminal réduit sous 120 colonnes → tableau en plein écran. Puis `tmux -L meute kill-server`.
- [ ] **Étape 5 : vérification complète, puis commit.** `git commit -m "feat: commande meute, disposition au lancement et tableau de bord branché"`

---

### Task 14 : tests de mutation, feuille de route et PR

**Fichiers :**
- Créer : `docs/dev/mutants/2026-plan-2.md`
- Modifier : les fichiers de tests concernés ; `docs/superpowers/plans/2026-10-15-meute-v1-roadmap.md`

**Interfaces :**
- Consomme : tout le plan.
- Produit : le rapport de mutation, la mise à jour de la feuille de route, la PR du plan 2.

- [ ] **Étape 1 : lancer les tests de mutation** sur le code nouveau ou modifié : `git diff main...HEAD > /tmp/plan2.diff && cargo mutants --in-diff /tmp/plan2.diff --package meute-core --package meute-tmux --package meute-git --package meute-tui --no-shuffle -j 4 --test-tool nextest`. Noter `caught` / `missed` / `unviable` / `timeout`.
- [ ] **Étape 2 : traiter chaque mutation manquée en TDD**, comme au plan 1 : test qui échoue sur le code muté puis passe sur le code réel, dans un fichier `tests/*_mutants.rs` ; ou une phrase de justification si la mutation est équivalente. Aucun test existant modifié.
- [ ] **Étape 3 : écrire le rapport** `docs/dev/mutants/2026-plan-2.md` (même forme que celui du plan 1).
- [ ] **Étape 4 : mettre à jour la feuille de route.** Ajouter une section « Reports issus du plan 2 » avec la liste « Hors périmètre » de ce plan ; noter que `meute session new --kind` vaudra `claude` par défaut au plan 3 ; retirer de « Reports issus du plan 1 » les deux points traités (API R16 et `tests/common`), en gardant le critère d'entrée du plan 3 (ouverture concurrente de la base).
- [ ] **Étape 5 : vérification complète**, plus `cargo +1.85 check --workspace --all-targets` et `bash .claude/hooks/tests/run.sh`.
- [ ] **Étape 6 : commiter, pousser, ouvrir la PR.**

```bash
git commit -m "test: renforce les tests du plan 2 d'après cargo-mutants"
git push -u origin feat/plan-2-tmux-sessions-bash
gh pr create --base main --assignee gaetinux --title "Plan 2 : tmux, dépôts et sessions Bash" \
  --body "<résumé des 14 tasks, les deux modifications de tests autorisées, les exceptions de lint, les versions bridées par la MSRV, le rapport de mutation, l'essai manuel de la Task 13, puis « 🤖 Generated with Claude Code », sans lien de session>"
```
