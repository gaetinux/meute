# meute — Plan 2 Python : tmux, dépôts et sessions Bash — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Objectif :** `meute` démarre son serveur tmux dédié et sa disposition (zone principale et tableau de bord minimal), découvre les dépôts, puis lance, affiche, réconcilie et arrête des sessions Bash, depuis la CLI comme depuis le tableau de bord.

**Architecture :** `meute.core` gagne le modèle de session, la table `sessions` (migration 2), les dépôts en base, la règle de réconciliation (pure) et le modèle de vue du tableau de bord. Trois packages indépendants entre eux s'y ajoutent : `meute.tmux` pilote le binaire `tmux` par `subprocess`, `meute.git` parcourt le système de fichiers, `meute.tui` dessine le tableau de bord avec Textual à partir du modèle de vue du cœur. `meute.cli` assemble le tout : il lit tmux, appelle `reconcile`, écrit en base. Il n'y a pas de service de fond : l'état vit dans tmux (les panneaux) et dans SQLite (les sessions), et chaque lecture les réconcilie.

**Stack technique :** existante : Python 3.13, uv, Typer, `tomlkit`, pytest, pytest-xdist, `hypothesis`, `syrupy`, `mutmut` ; nouvelle : `textual` (Task 9), `pytest-textual-snapshot` en dev (Task 9) ; stdlib `subprocess`, `uuid`, `os.scandir` ; externe : `tmux` ≥ 3.2 (3.5a en local, déjà installé dans la CI).

**Spécification :** `docs/superpowers/specs/2026-10-15-meute-design.md`, § 4.2, 4.3, 4.5, 5.1 à 5.4, 6.1, 6.3 à 6.5, 10, 16 et 17. Conception de la migration : `docs/superpowers/specs/2026-10-16-migration-python-design.md` (§ 3, 5.1, 5.2). Guide : `docs/dev/developpement-assiste-par-ia.md`, qui fait partie des exigences. Feuille de route : `docs/superpowers/plans/2026-10-15-meute-v1-roadmap.md`.

**Référence de comportement :** le plan Rust `docs/superpowers/plans/2026-10-16-meute-plan-2-tmux-sessions-bash.md` et son code sous le tag `rust-plan-2-wip` (`git show rust-plan-2-wip:<chemin>`). Ses Tasks 1 et 2 (utilitaires de test, refonte de l'API des tâches) sont déjà faites par le plan 1 Python ; ses Tasks 3 à 9 sont implémentées en Rust, la Task 10 (tableau ratatui) est inachevée, les Tasks 11 à 14 n'existent pas. Chaque tâche cite les fichiers Rust qu'elle remplace : on les lit pour le comportement, **sans les traduire mécaniquement**. Leçons déjà tirées du code Rust et reprises ici : les cibles `select-pane` de la configuration générée sont entre apostrophes (`'=meute:main.{right}'`), et `ensure_layout` répare aussi un tableau mort et une fenêtre `main` disparue.

**Prérequis :** le plan 1 Python est mergé (PR #7). Branche de ce plan : `feat/plan-2-python`, créée depuis `main`.

## Contraintes globales

**Hérité du plan 1 Python (inchangé)**
- `meute.core`, `meute.tmux` et `meute.git` n'importent que la stdlib et leur propre package (garde `test_packages_import_only_the_stdlib_and_their_allowed_meute_packages`, contrats import-linter de `pyproject.toml`). `meute.tui` n'importe que `meute.core` et `textual`. Seul `meute.cli` assemble. Les `__init__.py` ne contiennent qu'une docstring ; on importe toujours le sous-module précis.
- Données : `@dataclass(frozen=True, slots=True, kw_only=True)` ; variante porteuse de données = dataclass gelée dans une union, variante sans donnée = dataclass gelée vide, énumération simple = `enum.Enum` ; identifiants en `NewType`. Jamais de `case _:` sauf `case _: assert_never(x)`.
- Docstrings (Google) sur tout élément public de `meute.core`. Fichiers de moins de 300 lignes.
- Erreurs : hiérarchie `MeuteError` dans le cœur ; `meute.tmux` a sa propre hiérarchie `TmuxError(Exception)` (il ne peut pas importer le cœur) ; `OSError` et `sqlite3.Error` remontent tels quels. Pas d'`assert` hors des tests, pas d'`except Exception`.
- Exceptions aux lints : une règle précise et ` — raison` (guide § 3), listées dans la PR. Les appels `subprocess.run([...])` sans `shell=True` portent `# noqa: S603` (et `S607` pour le nom `tmux` résolu par le `PATH`) avec une raison.
- Dépendances uniquement avec `uv add` (`--dev` pour les tests), puis lecture de la documentation de la version installée (context7) avant d'utiliser l'API.
- Horodatages : ceux du plan 1 (`to_db`, `from_db` de `meute/core/instants.py`, horloge `db.now()`).

**Interface** : en anglais. Les textes affichés sont ceux de ce plan, copiés **mot pour mot**.

**tmux en test** (spécification § 17)
- Uniquement sur un serveur jetable `tmux -L meute-test-<uuid4 hex>`, tué à la fin du test, y compris en cas d'échec (fixture qui fait toujours `kill-server`). Jamais sur le serveur `meute` ni sur le tmux de l'utilisateur. Le serveur de test démarre avec `-f /dev/null` ou avec la configuration générée sous test.
- Les tests de la CLI passent par la fixture `sandbox`, qui définit **toujours** `MEUTE_TMUX_SOCKET` (Task 10) : aucune commande lancée par un test ne peut viser le socket `meute`.
- Un test qui attend un effet de tmux interroge l'état toutes les 100 ms avec une échéance de 10 s (`wait_until`, Task 3). Aucun `sleep` fixe.

**Conventions tmux de ce plan**
- Socket `meute` par défaut, remplacé par `MEUTE_TMUX_SOCKET` si elle est définie et non vide.
- Session `meute`, fenêtre `main` (cible `=meute:main`), session `meute-bg` ; options de **pane** `@meute_id` (UUID de la session), `@meute_role` (`board` ou `welcome`), `remain-on-exit` ; option globale `@meute_status`. Aucune option `@meute_*` sur une fenêtre (§ 5.1).
- Tableau de bord à droite (`{right}`), zone principale à gauche (`{left}`) ; la position (§ 15) n'est pas réglable dans ce plan.
- meute se relance lui-même par `[sys.executable, "-m", "meute", …]` (tableau de bord, accueil, hooks tmux) : c'est juste avec `uv tool install` comme en développement.
- Configuration tmux générée : `<état>/tmux.conf` (`~/.local/state/meute/tmux.conf`), réécrite à chaque commande qui touche à tmux. Ce n'est pas un fichier de l'utilisateur.

**Qualité et workflow**
- Dans les blocs de tests, un test dont le corps est un commentaire est à écrire tel qu'il est décrit, avec ces valeurs ; les signatures et imports évidents sont omis.
- TDD strict (guide § 1). Ne jamais modifier, supprimer ni désactiver un test existant pour le faire passer. **Seules exceptions autorisées par ce plan**, signalées dans le message de commit et dans la PR :
  1. Task 1 : la version de schéma attendue passe de `1` à `2` dans `tests/test_db_open.py` (trois assertions : `test_open_creates_file_with_wal_and_latest_schema`, le test `in_memory` et `test_reopening_is_idempotent_and_makes_no_backup`), car ces tests vérifient « le dernier schéma » ;
  2. Task 10 : la fixture `sandbox` de `tests/conftest.py` gagne un socket tmux de test ; aucune assertion n'est touchée.
- Instantanés `syrupy` (`.ambr`) et `pytest-textual-snapshot` (SVG) relus ligne par ligne contre ce plan avant acceptation ; jamais `--snapshot-update` à l'aveugle.
- Chaque tâche se termine par : `bash scripts/verify.sh` au vert, `/simplify`, et `/security-review` pour les tâches marquées **[sécurité]** (sous-processus, fichiers, SQL). Puis un commit, message en anglais, terminé par `Co-Authored-By: Claude …`, sans ligne `Claude-Session` ni lien de session.
- Une PR à la fin, assignée à `gaetinux`, jamais de push sur `main`.

## Hors périmètre (reporté, inscrit dans la feuille de route à la Task 14)

- `M-n` / `M-N` et le compteur « needs attention » de la barre d'état : ils dépendent des états Claude (plans 3 et 4).
- Les actions sur les panneaux orphelins (adopter, fermer) : ce plan les **affiche** seulement ; les actions viennent avec le TUI complet (plan 4).
- Le formulaire `N`, la recommandation de worktree et le « dernier type utilisé » de `n` (plan 4) ; ici, `n` lance toujours Bash.
- La création automatique de projets et les worktrees (plan 6) ; les worktrees découverts ne sont pas enregistrés en base.
- § 16, « base indisponible ou verrouillée » : le tableau de bord affiche l'erreur dans son pied de page ; la vue Sessions alimentée par tmux seul vient au plan 4.
- Les colonnes Claude de `sessions` (`native_id`, mode de permission, métriques…) : migration du plan 3.
- Le retrait des caractères de contrôle des titres affichés (report du plan 1) : avant les plans hooks et MCP, comme prévu.

## Points de vigilance (Review Focus)

Entrées que la spécification implique sans les tester, les plus susceptibles de gêner l'auteur. Les points de vigilance du plan Rust (tmux en échec ≠ serveur arrêté, panneau tué hors de meute, arrêt de la session affichée, afficher la session déjà affichée) restent des tests ordinaires des Tasks 4, 11 et 12.

1. **Crochets dans un titre, un dossier ou un nom de dépôt.** Textual interprète `[bold]` ou `[/]` comme du balisage : un titre `[wip] fix [/]` ferait planter le tableau ou changerait son style. Tout texte venant des données est affiché littéralement. Test au Task 9 (`test_brackets_in_data_are_shown_literally`).
2. **Préfixe de session contenant `%` ou `_`.** Avec `LIKE`, `meute session show %` désignerait n'importe quelle session. La recherche par préfixe compare `substr(id, 1, n)`, sans motif. Test au Task 1 (`test_find_session_prefix_is_not_a_pattern`).
3. **tmux en échec ≠ serveur arrêté.** Serveur absent (« no server running », « error connecting to ») : aucun panneau, les sessions vivantes deviennent `Unreachable`. Toute autre erreur (tmux absent, sortie illisible) remonte telle quelle et **aucune** session n'est modifiée. Tests aux Tasks 4 et 11.
4. **Racines de dépôts absentes, illisibles, boucles de liens symboliques, noms non UTF-8.** La découverte ignore ce qu'elle ne peut pas lire, ne suit pas les liens symboliques et ne lève jamais d'erreur ; un nom non UTF-8 ne doit pas faire échouer l'écriture en base. Test au Task 6.
5. **Raccourcis de `[keys]` qui ne sont pas des touches.** Ils sont recopiés dans la configuration tmux générée : `focus_board = "M-p \; kill-server"` injecterait une commande, `""` casserait le fichier. La validation n'accepte que `[A-Za-z0-9-]{1,20}`. Test au Task 10.

---

### Task 1 : modèle de session et table `sessions` [sécurité]

**Fichiers :**
- Créer : `src/meute/core/session_state.py`, `src/meute/core/session.py`, `src/meute/core/db/sql/002_sessions.sql`, `src/meute/core/db/sessions.py`
- Modifier : `src/meute/core/db/connection.py` (`data_version`), `src/meute/core/errors.py` (docstring de `NotFound` : « A task, a project or a session does not exist. »), `tests/test_db_open.py` (exception autorisée n° 1)
- Test : `tests/test_session_state.py`, `tests/test_session_model.py`, `tests/test_db_sessions.py`

**Remplace :** `crates/meute-core/src/session/{types,tests}.rs`, `crates/meute-core/src/db/sessions.rs`, `crates/meute-core/tests/db_sessions.rs`, `002_sessions.sql`.

**Interfaces :**
- Produit, dans `session_state.py` : dataclasses gelées vides `Running`, `SubagentRunning`, `Compacting`, `PermissionRequested`, `WaitingInput`, `Idle`, `Unreachable`, `MaybeStuck`, `Unknown`, et `Exited(code: int | None)` ; `SessionState` = leur union (spécification § 6.1) ; puis :
  - `state_id(state: SessionState) -> str` : `running`, `subagent_running`, `compacting`, `permission_requested`, `waiting_input`, `idle`, `exited`, `unreachable`, `maybe_stuck`, `unknown` ;
  - `state_from_parts(state: str, code: int | None) -> SessionState` : `InvalidInput("unknown session state: <state>")` ; `code` n'est lu que pour `exited` ;
  - `is_live(state: SessionState) -> bool` : faux pour `Exited` et `Unreachable` seulement ;
  - `state_label(state: SessionState) -> str`, textes exacts : `running`, `subagent`, `compacting`, `permission`, `waiting for your reply`, `idle`, `exited (7)` ou `exited`, `unreachable`, `stuck?`, `unknown?` (principe 4 : les états supposés portent un « ? ») ;
  - `state_to_json(state: SessionState) -> JsonObject` : `{"kind": "exited", "code": 2}`, `{"kind": "running"}`.
- Produit, dans `session.py` :
  - `SessionId = NewType("SessionId", str)` (UUID en forme hyphénée minuscule), `new_session_id() -> SessionId` (`uuid4`), `parse_session_id(text: str) -> SessionId` (`InvalidInput("invalid session id: <text>")`, accepte les majuscules et renvoie la forme canonique), `short_id(session_id: SessionId) -> str` (8 premiers caractères) ;
  - `class AgentKind(Enum)` : `CLAUDE = "claude"`, `BASH = "bash"` ;
  - `Session(id, agent, title, project_id: ProjectId | None, repo_id: RepoId | None, task_id: TaskId | None, cwd: Path, state, last_activity_at: datetime, created_at: datetime, ended_at: datetime | None)` ;
  - `NewSession(id, agent, title, cwd: Path, state, project_id=None, repo_id=None, task_id=None)` ;
  - `session_to_json(session: Session) -> JsonObject` : clés `id`, `agent`, `title`, `project_id`, `repo_id`, `task_id`, `cwd`, `state` (forme de `state_to_json`), `last_activity_at`, `created_at`, `ended_at` (instants par `format_instant`, comme `task_to_json`).
- Produit, dans `db/sessions.py` :
  - `create_session(db: Database, new: NewSession) -> Session` : titre nettoyé des espaces, vide → `InvalidInput("title cannot be empty")` ; `cwd` non encodable en UTF-8 (`str(cwd).encode("utf-8")` lève) → `InvalidInput("path is not valid UTF-8: <repr>")` ; `created_at = last_activity_at = db.now()` ;
  - `get_session(db: Database, session_id: SessionId) -> Session` (`NotFound("session", id)`) ;
  - `find_session(db: Database, prefix: str) -> Session` : identifiant complet, ou préfixe d'au moins 4 caractères (comparé en minuscules par `substr(id, 1, length)`, jamais par `LIKE`) désignant une seule session ; plusieurs → `InvalidInput("ambiguous session id: <prefix>")` ; aucune, ou moins de 4 caractères → `NotFound("session", prefix)` ;
  - `list_sessions(db: Database, *, include_ended: bool = False) -> list[Session]`, triées par `created_at` puis `id` ; sans `include_ended`, seulement les états vivants ;
  - `set_session_state(db: Database, session_id: SessionId, state: SessionState) -> Session` : `last_activity_at = now` ; `ended_at = now` quand la session passe d'un état vivant à un état non vivant, inchangé sinon ; `NotFound` si elle n'existe pas.
- Produit, dans `connection.py` : `Database.data_version(self) -> int` (`PRAGMA data_version`, pour le rafraîchissement du § 4.5).

Migration `002_sessions.sql`, texte exact :

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

- [ ] **Étape 1 : écrire les tests qui échouent.**

```python
# tests/test_session_state.py
ALL_STATES = [Running(), SubagentRunning(), Compacting(), PermissionRequested(), WaitingInput(),
              Idle(), Exited(code=7), Exited(code=None), Unreachable(), MaybeStuck(), Unknown()]

@pytest.mark.parametrize("state", ALL_STATES)
def test_state_round_trips_through_its_parts(state):
    code = state.code if isinstance(state, Exited) else None
    assert state_from_parts(state_id(state), code) == state

@pytest.mark.parametrize(("state", "live"), [  # liste explicite, pas is_live contre lui-même
    (Running(), True), (SubagentRunning(), True), (Compacting(), True),
    (PermissionRequested(), True), (WaitingInput(), True), (Idle(), True),
    (MaybeStuck(), True), (Unknown(), True), (Exited(code=0), False), (Unreachable(), False)])
def test_is_live(state, live): ...

@pytest.mark.parametrize(("state", "label"), [
    (Running(), "running"), (SubagentRunning(), "subagent"), (Compacting(), "compacting"),
    (PermissionRequested(), "permission"), (WaitingInput(), "waiting for your reply"),
    (Idle(), "idle"), (Exited(code=7), "exited (7)"), (Exited(code=None), "exited"),
    (Unreachable(), "unreachable"), (MaybeStuck(), "stuck?"), (Unknown(), "unknown?")])
def test_state_label(state, label): ...

def test_state_json_shape():
    assert state_to_json(Exited(code=2)) == {"kind": "exited", "code": 2}
    assert state_to_json(Running()) == {"kind": "running"}

def test_unknown_state_id_is_rejected():
    with pytest.raises(InvalidInput, match="^unknown session state: asleep$"):
        state_from_parts("asleep", None)

# tests/test_session_model.py
def test_parse_session_id_canonicalises_and_rejects():
    assert parse_session_id("AAAA1111-0000-4000-8000-000000000000") == "aaaa1111-0000-4000-8000-000000000000"
    with pytest.raises(InvalidInput, match="^invalid session id: nope$"):
        parse_session_id("nope")

def test_short_id_and_new_id():
    assert short_id(SessionId("aaaa1111-0000-4000-8000-000000000000")) == "aaaa1111"
    first, second = new_session_id(), new_session_id()
    assert parse_session_id(first) == first
    assert first != second

def test_session_json_has_every_field(): ...  # session construite à la main, dict complet attendu

# tests/test_db_sessions.py (fixtures db et file_db de conftest)
def test_create_then_get_round_trips_every_field(db): ...  # project, repo et task réels en base
def test_create_strips_title_and_refuses_empty(db): ...    # "  " -> InvalidInput("title cannot be empty")
def test_create_refuses_non_utf8_cwd(db): ...              # Path(os.fsdecode(b"/tmp/\xff"))
def test_list_excludes_ended_unless_asked(db): ...
def test_ended_at_is_set_once_when_leaving_live_states(db): ...
    # horloge modifiable : Running -> Exited(2) à t1 pose ended_at = t1 ;
    # Exited -> Unreachable à t2 garde t1 ; last_activity_at vaut t2
def test_set_state_of_missing_session_is_not_found(db): ...
def test_find_session_by_unique_prefix_ambiguous_and_short(db): ...
    # aaaa1111-… et aaaa2222-… : "aaaa1" et "AAAA1" trouvent le premier, "aaaa" est ambigu,
    # "aaa" -> NotFound, l'identifiant complet trouve sa session
def test_find_session_prefix_is_not_a_pattern(db): ...      # "%%%%", "____", "aaa%" -> NotFound
def test_data_version_changes_after_a_write_from_another_connection(tmp_path): ...
def test_migrating_a_v1_file_keeps_tasks_and_backs_it_up(tmp_path): ...
    # fichier migré avec migrate(conn, path, MIGRATIONS[:1]), une tâche insérée ;
    # Database.open -> schema_version() == 2, la tâche est intacte, meute.db.bak-1 existe
```

- [ ] **Étape 2 : constater l'échec** (`uv run pytest tests/test_session_state.py tests/test_session_model.py tests/test_db_sessions.py`) : `ModuleNotFoundError`, puis les assertions.
- [ ] **Étape 3 : implémenter.** Puis exception autorisée n° 1 : dans `tests/test_db_open.py`, la version attendue `1` devient `2` dans les trois assertions listées aux contraintes globales, et rien d'autre ; le dire dans le message de commit. Ajouter les trois nouveaux fichiers de tests à `pytest_add_cli_args_test_selection` de `[tool.mutmut]`.
- [ ] **Étape 4 : vérifier.** `bash scripts/verify.sh` au vert ; `git diff main -- tests/test_db_open.py` ne montre que les trois `1` → `2`.
- [ ] **Étape 5 : `/simplify`, `/security-review`, commit.** `git commit -m "feat(core): session model and sessions table (migration 2)"`

---

### Task 2 : règle de réconciliation (§ 5.4)

**Fichiers :**
- Créer : `src/meute/core/reconcile.py`
- Test : `tests/test_reconcile.py`

**Remplace :** `crates/meute-core/src/session/reconcile.rs` et ses tests.

**Interfaces :**
- Consomme : `Session`, `SessionId`, `AgentKind`, les états et `is_live` (Task 1).
- Produit :
  - `PaneObservation(meute_id: str, dead: bool, exit_code: int | None)` : un panneau qui porte `@meute_id`, tel que vu par tmux ;
  - `Reconciliation(updates: tuple[tuple[SessionId, SessionState], ...], orphans: tuple[str, ...])` ;
  - `reconcile(sessions: Sequence[Session], panes: Sequence[PaneObservation]) -> Reconciliation` (pure).
- Règles, pour chaque session **vivante** :
  - aucun panneau avec son identifiant → `Unreachable()` ;
  - panneau mort → `Exited(code=exit_code)` ;
  - panneau vivant, agent `BASH`, état différent de `Running()` → `Running()` (§ 6.3) ;
  - panneau vivant, agent `CLAUDE` → aucune mise à jour (l'état viendra des hooks, plan 3).
- Les sessions non vivantes ne sont jamais mises à jour (pas de résurrection implicite, principe 5).
- Orphelins : identifiants de panneau qui ne correspondent à **aucune** session de la liste (vivante ou non), y compris ceux qui ne sont pas des UUID ; sans doublon, dans l'ordre des panneaux.
- `updates` est dans l'ordre de `sessions` ; `updates` et `orphans` sont vides quand rien ne change.

- [ ] **Étape 1 : écrire les tests qui échouent.** Un test par règle : `test_missing_pane_makes_live_session_unreachable`, `test_dead_pane_gives_exited_with_code` (code 7), `test_dead_pane_without_status_gives_exited_none`, `test_live_bash_pane_restores_running_from_unknown`, `test_running_bash_with_live_pane_needs_no_update`, `test_claude_session_with_live_pane_is_untouched`, `test_ended_sessions_are_never_updated` (`Exited` dont le panneau a disparu → aucune mise à jour), `test_pane_of_an_ended_session_is_not_an_orphan`, `test_unknown_and_malformed_ids_are_orphans_once` (`"not-a-uuid"` présent deux fois → une seule entrée). Plus une propriété `hypothesis` `test_reconcile_invariants` : pour des sessions et des panneaux quelconques (identifiants tirés d'un petit ensemble pour provoquer des correspondances), chaque identifiant mis à jour est celui d'une session vivante, `orphans` n'a pas de doublon et ne contient aucun identifiant de session.
- [ ] **Étape 2 : constater l'échec.**
- [ ] **Étape 3 : implémenter `reconcile`.** Ajouter `tests/test_reconcile.py` à la sélection de mutmut.
- [ ] **Étape 4 : vérification complète.**
- [ ] **Étape 5 : `/simplify`, commit.** `git commit -m "feat(core): reconcile sessions with tmux panes"`

---

### Task 3 : package `meute.tmux` — client, version et serveur de test [sécurité]

**Fichiers :**
- Créer : `src/meute/tmux/errors.py`, `src/meute/tmux/parse.py`, `src/meute/tmux/client.py`, `src/meute/tmux/CLAUDE.md`
- Créer : `tests/tmux_support.py` ; modifier `tests/conftest.py` (fixture `tmux_server`) et `tests/support.py` (`wait_until`)
- Test : `tests/test_tmux_version.py`, `tests/test_tmux_client.py`

**Remplace :** `crates/meute-tmux/src/{client,version,error}.rs`, `crates/meute-tmux/tests/{client.rs,common/mod.rs}`.

Texte exact de `src/meute/tmux/CLAUDE.md` :

```markdown
# meute.tmux

Tests only on a throw-away tmux server (`tmux_server` fixture, socket `meute-test-<uuid>`,
configuration `/dev/null`), always killed at the end. Never call tmux without `-L`, and never
target the `meute` socket.
```

**Interfaces :**
- Produit, dans `errors.py` : `class TmuxError(Exception)`, et ses sous-classes, `str()` exacts :
  - `NotInstalled()` : `tmux not found: meute needs tmux 3.2 or later (for example: sudo apt install tmux)` ;
  - `TooOld(found: str)` : `tmux {found} is too old: meute needs tmux 3.2 or later` (attribut `found`, sans le préfixe `tmux`) ;
  - `CommandFailed(args: Sequence[str], stderr: str)` : `tmux {args joints par une espace} failed: {stderr}` (attributs `args: tuple[str, ...]`, `stderr`) ;
  - `UnreadableOutput(detail: str)` : `unreadable tmux output: {detail}`.
- Produit, dans `parse.py` : `TmuxVersion(major: int, minor: int)` (dataclass gelée, `order=True`), `MIN_VERSION = TmuxVersion(major=3, minor=2)`, `parse_version(output: str) -> TmuxVersion | None` (premier `<chiffres>.<chiffres>` du texte, après `tmux ` ; `None` si aucun).
- Produit, dans `client.py` :
  - `Tmux(socket: str, config_file: Path | None = None)` (dataclass gelée) ;
  - `Tmux.base_args(self) -> list[str]` : `["tmux", "-L", socket]`, puis `["-f", str(config_file)]` si défini (réutilisé pour l'attachement, Task 13) ;
  - `Tmux.run(self, *args: str) -> str` : `subprocess.run(base_args + args, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)` ; stdout sans le saut de ligne final ; statut non nul → `CommandFailed(args, stderr sans espaces finaux)` ; `FileNotFoundError` au lancement → `NotInstalled` ; toute autre `OSError` remonte ;
  - `is_no_server(error: CommandFailed) -> bool` : `stderr` contient `no server running` ou `error connecting to` ;
  - `Tmux.is_running(self) -> bool` (`list-sessions` ; pas de serveur → `False`, autre erreur remontée), `Tmux.has_session(self, name: str) -> bool` (cible exacte `=<name>` ; `CommandFailed` → `False`), `Tmux.kill_server(self) -> None` ;
  - `check_version() -> TmuxVersion | None` (fonction du module) : `tmux -V` ; binaire absent → `NotInstalled` ; version lue < 3.2 → `TooOld` ; illisible (`tmux master`, `tmux openbsd-7.6`) → `None`, accepté.
- Produit, pour les tests : `tests/tmux_support.py` : `TestServer(tmux: Tmux)` avec `TestServer.start() -> TestServer` (socket `meute-test-<uuid4().hex>`, `config_file=Path("/dev/null")`, `new-session -d -s test -x 200 -y 50`) et `stop()` (`kill-server`, erreur ignorée) ; fixture `tmux_server` (dans `conftest.py`) qui démarre puis arrête toujours ; `wait_until(what: str, predicate: Callable[[], bool], *, timeout: float = 10.0) -> None` dans `support.py` (100 ms entre deux essais, `AssertionError(f"timed out waiting for {what}")`).

- [ ] **Étape 1 : écrire les tests qui échouent.**
  - `parse_version` (paramétré) : `"tmux 3.5a"` → 3.5, `"tmux 3.2"` → 3.2, `"tmux next-3.6"` → 3.6, `"tmux 2.9a"` → 2.9, `"tmux 3.10"` → 3.10, `"tmux master"` → `None`, `""` → `None` ; propriété `hypothesis` : `parse_version` ne lève jamais sur un texte quelconque.
  - comparaison : `TmuxVersion(major=3, minor=1) < MIN_VERSION`, `TmuxVersion(major=3, minor=10) > TmuxVersion(major=3, minor=2)`.
  - `test_too_old_version_message` : `str(TooOld("2.9a")) == "tmux 2.9a is too old: meute needs tmux 3.2 or later"`, et le classement de `"tmux 2.9a"` par une fonction privée `_classify_version(output)` lève ce `TooOld`.
  - `test_missing_binary_is_not_installed` : `Tmux(socket=…).run("ls")` avec `PATH` vidé par `monkeypatch.setenv("PATH", "")` → `NotInstalled`.
  - intégration : `test_start_run_and_kill` (`has_session("test")` vrai, `has_session("tes")` faux ; après `kill_server`, `is_running()` faux) ; `test_failed_command_reports_stderr` (`run("kill-pane", "-t", "%999")` → `CommandFailed` dont `stderr` n'est pas vide et dont `str()` commence par `tmux kill-pane -t %999 failed: `) ; `test_never_started_socket_is_not_running`.
- [ ] **Étape 2 : constater l'échec.**
- [ ] **Étape 3 : implémenter.** `TMUX` n'est **pas** retiré de l'environnement des commandes (`-L` prévaut ; seul l'attachement imbriqué le retire, Task 13).
- [ ] **Étape 4 : vérifier.** `bash scripts/verify.sh` ; `tmux -L meute ls` affiche la même chose qu'avant les tests (aucun serveur `meute` créé).
- [ ] **Étape 5 : `/simplify`, `/security-review`, commit.** `git commit -m "feat(tmux): tmux client on a dedicated server and version check"`

---

### Task 4 : panneaux tmux [sécurité]

**Fichiers :**
- Créer : `src/meute/tmux/panes.py`
- Modifier : `src/meute/tmux/parse.py` (`parse_pane_line`)
- Test : `tests/test_tmux_parse.py`, `tests/test_tmux_panes.py`

**Remplace :** `crates/meute-tmux/src/pane.rs`, `crates/meute-tmux/tests/panes.rs`.

**Interfaces :**
- Consomme : `Tmux`, `is_no_server`, les erreurs, `tmux_server`, `wait_until` (Task 3).
- Produit, dans `parse.py` :
  - `PaneId = NewType("PaneId", str)` (`"%12"`) ;
  - `PaneInfo(id: PaneId, session: str, window: str, meute_id: str | None, role: str | None, dead: bool, dead_status: int | None, width: int)` (option vide → `None`) ;
  - `PANE_FORMAT = "#{pane_id}\t#{session_name}\t#{window_name}\t#{@meute_id}\t#{@meute_role}\t#{pane_dead}\t#{pane_dead_status}\t#{pane_width}"` ;
  - `parse_pane_line(line: str) -> PaneInfo` : exactement 8 champs séparés par des tabulations, sinon `UnreadableOutput` ; statut ou largeur non numérique → `UnreadableOutput`.
- Produit, dans `panes.py` (fonctions qui prennent `tmux: Tmux` en premier argument) :
  - `list_panes(tmux) -> list[PaneInfo]` : `list-panes -a -F PANE_FORMAT` ; serveur absent (`is_no_server`) → `[]` ; toute autre erreur remonte ;
  - `Spawn(session: str, cwd: Path, command: tuple[str, ...], env: tuple[tuple[str, str], ...] = (), pane_options: tuple[tuple[str, str], ...] = ())` ;
  - `spawn_window(tmux, spawn: Spawn) -> PaneId` : si la session existe, `new-window -d -t =<session>: -P -F '#{pane_id}' -c <cwd> -e K=V … -- <command…>`, sinon `new-session -d -s <session> -P -F … -c … -e … -- …` ; puis `set-option -p -t <pane> <nom> <valeur>` pour chaque option, dans l'ordre ;
  - `set_pane_option(tmux, pane, name, value)`, `set_global_option(tmux, name, value)`, `swap_panes(tmux, src, dst)` (`swap-pane -d -s src -t dst`), `select_pane(tmux, pane)`, `send_keys(tmux, pane, *keys)`, `kill_pane(tmux, pane)`, `switch_client_to(tmux, pane)` ; toutes renvoient `None`.

- [ ] **Étape 1 : écrire les tests qui échouent.**
  - `parse_pane_line` : panneau mort `"%3\tmeute-bg\tw\t<uuid>\t\t1\t7\t80"` → `dead`, `dead_status == 7`, `role is None` ; panneau vivant (statut vide → `None`) ; ligne à 7 champs → `UnreadableOutput` ; largeur `"wide"` → `UnreadableOutput`.
  - `test_list_panes_on_never_started_socket_is_empty`.
  - `test_list_panes_other_errors_propagate` : `PATH` vidé par `monkeypatch` → `NotInstalled`, pas une liste vide ; et `is_no_server` est faux pour `CommandFailed(("x",), "unknown command: x")`.
  - `test_spawn_creates_bg_session_then_windows` : deux `spawn_window` dans `bg` (`sh -c 'sleep 3600'`) → deux panneaux de session `bg`, chacun avec son `@meute_id`.
  - `test_spawn_passes_cwd_and_env` : commande `sh -c 'pwd > "$OUT"; echo "$MEUTE_SESSION" >> "$OUT"; sleep 3600'`, `OUT` passé par `env`, `cwd` contenant une espace ; attendre le fichier ; il contient le `cwd` puis la valeur.
  - `test_remain_on_exit_keeps_dead_pane_with_status` : `sh -c 'exit 3'` avec `remain-on-exit on` → (attente) `dead` et `dead_status == 3`.
  - `test_meute_id_follows_the_pane_through_swap` (spike S4) : deux panneaux dans deux sessions, chacun avec son `@meute_id` ; après `swap_panes`, chaque identifiant est porté par le même `PaneId` qu'avant, mais dans l'autre session.
  - `test_kill_pane_removes_it`.
- [ ] **Étape 2 : constater l'échec.**
- [ ] **Étape 3 : implémenter.** Ajouter `tests/test_tmux_parse.py` et `tests/test_tmux_version.py` à la sélection de mutmut (Task 14 y ajoute `parse.py`).
- [ ] **Étape 4 : vérification complète.**
- [ ] **Étape 5 : `/simplify`, `/security-review`, commit.** `git commit -m "feat(tmux): panes, pane options and swapping"`

---

### Task 5 : disposition `meute` et configuration générée (§ 5.1 et 5.2) [sécurité]

**Fichiers :**
- Créer : `src/meute/tmux/names.py`, `src/meute/tmux/conf.py`, `src/meute/tmux/layout.py`
- Test : `tests/test_tmux_conf.py`, `tests/test_tmux_layout.py`, instantané `tests/__snapshots__/test_tmux_conf.ambr`

**Remplace :** `crates/meute-tmux/src/{conf,layout}.rs`, `crates/meute-tmux/tests/layout.rs` et son instantané.

**Interfaces :**
- Consomme : Tasks 3 et 4.
- Produit, dans `names.py` : `MAIN_SESSION = "meute"`, `MAIN_WINDOW = "main"`, `BG_SESSION = "meute-bg"`, `ID_OPTION = "@meute_id"`, `ROLE_OPTION = "@meute_role"`, `ROLE_BOARD = "board"`, `ROLE_WELCOME = "welcome"`, `STATUS_OPTION = "@meute_status"`.
- Produit, dans `conf.py` : `Keys(focus_board: str, focus_main: str)`, `LayoutSpec(board_width: int, narrow_threshold: int, board_command: tuple[str, ...], welcome_command: tuple[str, ...], sync_command: tuple[str, ...], keys: Keys)`, `render_config(spec: LayoutSpec) -> str`.
- Produit, dans `layout.py` : `is_narrow(width: int, threshold: int) -> bool` (`width < threshold`) ; `Layout(board: PaneId, main: PaneId | None, width: int, zoomed: bool)` ; `find_layout(tmux) -> Layout | None` (`None` sans panneau `@meute_role=board` vivant dans `meute:main` ; `main` = le premier autre panneau, non `board`, de cette fenêtre ; `width` et `zoomed` lus par `display-message -p -t =meute:main '#{window_width}\t#{window_zoomed_flag}'`, sortie illisible → `UnreadableOutput`) ; `ensure_layout(tmux, spec) -> Layout`.

Contenu exact de la configuration générée pour `sync_command = ("/opt/meute/bin/python", "-m", "meute", "layout", "sync")` et les touches `M-p` / `M-o`. Chaque mot de `sync_command` est mis entre apostrophes pour `sh` (`'` devient `'\''`), puis le texte est échappé deux fois pour une chaîne tmux entre guillemets (`\`, `"` et `$` précédés d'une barre oblique inverse), car tmux l'analyse au chargement du fichier puis à l'exécution du hook :

```
# Generated by meute: rewritten at every launch, do not edit.
set -g status-left "[meute] "
set -g status-right "#{@meute_status}"
set -g status-right-length 80
bind -n M-p switch-client -t =meute:main \; select-pane -t '=meute:main.{right}'
bind -n M-o select-pane -t '=meute:main.{left}'
set-hook -g client-attached "run-shell -b \"'/opt/meute/bin/python' '-m' 'meute' 'layout' 'sync'\""
set-hook -g client-resized "run-shell -b \"'/opt/meute/bin/python' '-m' 'meute' 'layout' 'sync'\""
```

Algorithme de `ensure_layout` (repris du code Rust, qui répare aussi un tableau mort et une fenêtre disparue) :
1. session `meute` absente : `new-session -d -s meute -n main -x 200 -y 50 -P -F '#{pane_id}' -- <welcome_command>` (rôle `welcome`), puis `split-window -h -l <board_width> -t <welcome> -P -F … -- <board_command>` (rôle `board`), puis `select-pane` sur le tableau ;
2. session présente, réparation de `meute:main` :
   - tableau vivant : on le garde ;
   - sinon, s'il y a un panneau principal : `split-window -h -l <board_width> -t <main> -- <board_command>` (rôle `board`) ;
   - sinon, s'il reste un panneau (tableau mort) : même `split-window` depuis ce panneau ;
   - sinon (fenêtre `main` disparue) : `new-window -d -t =meute: -n main -- <welcome_command>` (rôle `welcome`), puis le `split-window` du tableau ;
   - pas de panneau principal : `split-window -h -b -t <board> -- <welcome_command>` (rôle `welcome`) ;
   - les panneaux `board` morts sont tués ;
3. mode étroit : si `is_narrow(width, threshold)` diffère de `zoomed` → `resize-pane -Z -t <board>` ; si la fenêtre est large → `resize-pane -t <board> -x <board_width>` ;
4. renvoyer `find_layout` ; `None` à ce stade → `UnreadableOutput("no dashboard in meute:main")`.

- [ ] **Étape 1 : écrire les tests qui échouent.** Dans les tests de disposition, `board_command` et `welcome_command` valent `("sh", "-c", "sleep 3600")` et le serveur de test n'a pas de session `meute` au départ.
  - `test_generated_config` : instantané `syrupy` de `render_config`, relu ligne par ligne contre le bloc ci-dessus ;
  - `test_shell_quoting` : unitaires des deux fonctions privées d'échappement (`'a b'`, `l'appli` → `'l'\''appli'`, `a\b"c$d` → `a\\b\"c\$d`) ;
  - `test_generated_config_is_accepted_by_tmux` : configuration dont le chemin de `sync_command` contient une espace et une apostrophe, écrite dans un fichier puis `source-file` sur le serveur de test → succès ; `list-keys -T root` contient `M-p` et `M-o` ; `show-hooks -g` contient `client-attached` ;
  - `test_is_narrow` : `(119, 120)` vrai, `(120, 120)` faux ;
  - `test_fresh_server_gets_board_and_welcome` : deux panneaux dans `meute:main`, rôles `board` et `welcome`, tableau de 60 colonnes, non zoomé ;
  - `test_ensure_is_idempotent` : un second appel renvoie les mêmes `PaneId`, la fenêtre a toujours deux panneaux ;
  - `test_killed_main_pane_is_replaced_by_welcome` : `kill_pane(main)` → `ensure_layout` → deux panneaux, nouveau `welcome`, tableau à 60 ;
  - `test_killed_board_is_recreated` ;
  - `test_dead_board_is_replaced` : tableau lancé avec `remain-on-exit on` et `sh -c 'exit 0'`, mort → `ensure_layout` → un tableau vivant, plus aucun tableau mort ;
  - `test_missing_main_window_is_recreated` : `kill-window -t =meute:main` après avoir créé une seconde fenêtre dans `meute` (pour que la session survive) → `ensure_layout` → disposition complète ;
  - `test_narrow_window_zooms_board_and_wide_unzooms` : `resize-window -t =meute:main -x 100` → `zoomed` ; `-x 200` → non zoomé, tableau à 60.
- [ ] **Étape 2 : constater l'échec.**
- [ ] **Étape 3 : implémenter.** Ajouter `tests/test_tmux_conf.py` à la sélection de mutmut.
- [ ] **Étape 4 : vérifier ; relire l'instantané.**
- [ ] **Étape 5 : `/simplify`, `/security-review`, commit.** `git commit -m "feat(tmux): meute layout, generated configuration and narrow mode"`

---

### Task 6 : package `meute.git` — découverte des dépôts (§ 10) [sécurité]

**Fichiers :**
- Créer : `src/meute/git/kind.py`, `src/meute/git/discover.py`
- Test : `tests/test_git_kind.py`, `tests/test_git_discover.py`

**Remplace :** `crates/meute-git/src/{kind,discover}.rs`, `crates/meute-git/tests/discover.rs`.

**Interfaces :**
- Produit, dans `kind.py` : `class RepoKind(Enum)` : `RUST = "rust"`, `ANGULAR = "angular"`, `NODE = "node"`, `FASTAPI = "fastapi"`, `PYTHON = "python"` ; `detect_kind(folder: Path) -> RepoKind | None`, première règle qui s'applique : `Cargo.toml` → RUST ; `angular.json` → ANGULAR ; `package.json` → NODE ; `pyproject.toml` ou `requirements.txt` dont le texte, en minuscules, contient `fastapi` → FASTAPI ; `pyproject.toml`, `requirements.txt` ou `setup.py` → PYTHON ; sinon `None`. Un fichier illisible compte comme présent mais sans texte.
- Produit, dans `discover.py` : `DiscoveredRepo(path: Path, name: str, kind: RepoKind | None, worktrees: tuple[Path, ...])` ; `DEFAULT_DEPTH = 3` ; `discover(roots: Sequence[Path], max_depth: int = DEFAULT_DEPTH) -> list[DiscoveredRepo]` (triés par chemin, sans doublon) ; `expand_home(root: str, home: Path | None) -> Path` (`~` et `~/…` seulement).
- Règles de parcours :
  - on examine la racine elle-même (profondeur 0) et ses sous-dossiers jusqu'à `max_depth` inclus ;
  - `.git` **dossier** → dépôt principal ; on ne descend pas dans un dépôt ;
  - `.git` **fichier** dont la ligne `gitdir: <chemin>` désigne `<…>/.git/worktrees/<nom>` (absolu, ou relatif au dossier du worktree) → worktree, rattaché au dépôt dont le `.git` est `<…>/.git` ; il n'est jamais un dépôt ; un worktree dont le dépôt principal n'a pas été trouvé est ignoré ;
  - tout autre `.git` fichier (sous-module) → ignoré ;
  - dossiers cachés (nom commençant par `.`), `node_modules`, `target` et `.venv` non parcourus ;
  - liens symboliques jamais suivis (`os.scandir`, `is_dir(follow_symlinks=False)`) ; dossiers illisibles, racines absentes et noms non encodables en UTF-8 ignorés sans erreur ;
  - chemins comparés après `Path.resolve()`.

- [ ] **Étape 1 : écrire les tests qui échouent** (arborescences dans `tmp_path`, `.git` simulés à la main, sans appeler `git`) :
  - `detect_kind` (paramétré) : un cas par règle, `pyproject.toml` avec `FastAPI` → FASTAPI et sans → PYTHON, `package.json` + `angular.json` → ANGULAR, dossier vide → `None` ;
  - `test_finds_repos_up_to_depth_three` : dépôts à `r/a`, `r/x/b`, `r/x/y/c`, `r/x/y/z/d` → `a`, `b`, `c` seulement ;
  - `test_root_itself_can_be_a_repo` ;
  - `test_does_not_descend_into_repos` : `r/a/.git` et `r/a/sub/.git` → seulement `a` ;
  - `test_worktrees_attach_to_their_main_repo` : `r/meute/.git/worktrees/feat` et `r/meute.worktrees/feat/.git` (`gitdir: <abs>/r/meute/.git/worktrees/feat`) → un seul dépôt `meute`, `worktrees == (r/meute.worktrees/feat,)` ; même test avec un `gitdir` relatif ;
  - `test_orphan_worktree_and_submodule_are_ignored` ;
  - `test_missing_root_symlink_loop_and_unreadable_folder_are_harmless` (point de vigilance 4) : racine absente → `[]` ; `r/loop -> r` et un dépôt `r/a` → `a` une seule fois ; dossier `r/locked` en `chmod 000` → ignoré (permissions restaurées en fin de test) ;
  - `test_non_utf8_names_are_skipped` : dossier `os.fsdecode(b"r/\xff")` contenant un `.git` → absent du résultat, les autres dépôts présents ;
  - `test_hidden_node_modules_target_and_venv_are_skipped` ;
  - `expand_home` (paramétré) : `"~"`, `"~/git"`, `"/abs"`, `"~other"` (inchangé), `home is None` (inchangé).
- [ ] **Étape 2 : constater l'échec.**
- [ ] **Étape 3 : implémenter.** Ajouter les deux fichiers de tests à la sélection de mutmut.
- [ ] **Étape 4 : vérification complète.**
- [ ] **Étape 5 : `/simplify`, `/security-review`, commit.** `git commit -m "feat(git): repository discovery and worktree attachment"`

---

### Task 7 : dépôts en base et `meute repo list` [sécurité]

**Fichiers :**
- Créer : `src/meute/core/repo.py`, `src/meute/core/db/repos.py`, `src/meute/cli/repo_scan.py`, `src/meute/cli/repo_commands.py`
- Modifier : `src/meute/core/paths.py` (`display_path`), `src/meute/cli/__init__.py` (enregistrement de `repo`)
- Test : `tests/test_db_repos.py`, `tests/test_paths.py` (nouveau test), `tests/test_cli_repos.py`

**Remplace :** `crates/meute-core/src/{repo.rs,db/repos.rs}`, `crates/meute-core/tests/db_repos.rs`, `crates/meute/src/{repos.rs,cli/repo.rs}`, `crates/meute/tests/cli_repos.rs`. La table `repos` existe déjà (migration 1).

**Interfaces :**
- Consomme : `RepoId` (`meute/core/project.py`), `discover`, `expand_home`, `RepoKind` (Task 6), `CliContext` (`meute/cli/context.py`).
- Produit :
  - `Repo(id: RepoId, path: Path, name: str, kind: str | None, discovered_at: datetime)`, `NewRepo(path: Path, name: str, kind: str | None)`, `repo_to_json(repo: Repo) -> JsonObject` (clés `id`, `path`, `name`, `kind`, `discovered_at`) ;
  - `sync_repos(db: Database, found: Sequence[NewRepo]) -> list[Repo]` : une transaction ; insère les nouveaux chemins (`discovered_at = now`), met à jour `name` et `kind` des chemins connus ; **ne supprime jamais** un dépôt absent (principe 5) ; renvoie `list_repos(db)` ;
  - `list_repos(db: Database) -> list[Repo]`, triés par `name.casefold()` puis chemin ;
  - `display_path(path: Path, home: Path | None) -> str` : `~` ou `~/…` quand `path` est `home` ou en dessous, sinon le chemin tel quel ;
  - `scan_repos(ctx: CliContext) -> list[Repo]` (dans `repo_scan.py`) : `expand_home` de chaque `ctx.config.repos.roots` avec `Path.home()`, `discover`, conversion en `NewRepo` (`kind.value`), `sync_repos` ;
  - CLI `meute repo list [--json]` : `scan_repos`, puis une ligne par dépôt `{name}  {kind ou -}  {display_path}` ; `--json` : le tableau des `repo_to_json`.

- [ ] **Étape 1 : écrire les tests qui échouent.**
  - core : `test_sync_inserts_then_updates_without_deleting` (synchroniser `a`, `b` ; puis `a` seul avec un autre `kind` → deux dépôts, `a` mis à jour, son `discovered_at` inchangé, `b` toujours là) ; `test_list_is_sorted_by_name_case_insensitively` (`beta`, `Alpha`, `Écho`, `alpha2` → `Alpha`, `alpha2`, `beta`, `Écho`) ; `test_display_path` (paramétré : `home`, sous `home`, ailleurs, `home is None`, un dossier frère `home2`).
  - CLI (`sandbox`, `repos.roots` posé par `meute config set repos.roots '["<tmp>/home/git"]'`) : `test_repo_list_scans_configured_roots` (dépôts simulés `api` avec `Cargo.toml` et `front` avec `package.json` → sortie exacte `api  rust  ~/git/api\nfront  node  ~/git/front\n`) ; `test_repo_list_json_is_an_array_of_repos` ; `test_repo_list_with_missing_root_is_empty`.
- [ ] **Étape 2 : constater l'échec.**
- [ ] **Étape 3 : implémenter.** Ajouter `tests/test_db_repos.py` à la sélection de mutmut.
- [ ] **Étape 4 : vérification complète.**
- [ ] **Étape 5 : `/simplify`, `/security-review`, commit.** `git commit -m "feat: discovered repositories stored in the database and meute repo list"`

---

### Task 8 : modèle de vue du tableau de bord (`meute.core.board_view`)

Premier niveau du TUI (conception de la migration § 5.2) : tout ce que le tableau affiche et décide, sans Textual.

**Fichiers :**
- Créer : `src/meute/core/board_view.py`
- Test : `tests/test_board_view.py`, instantané `tests/__snapshots__/test_board_view.ambr`

**Remplace :** la partie données et textes de `crates/meute-tui/src/{board,render}.rs` (inachevés) et de leurs tests.

**Interfaces :**
- Consomme : `Session`, `SessionId`, `state_label` (Task 1), `Repo`, `RepoId`, `display_path` (Task 7).
- Produit :
  - `SessionRow(session: Session, has_pane: bool, displayed: bool)` ;
  - `BoardData(sessions: tuple[SessionRow, ...], repos: tuple[Repo, ...], orphans: tuple[str, ...], home: Path | None)` ;
  - actions : `ShowSession(session_id: SessionId)`, `LaunchBash(cwd: Path, repo_id: RepoId | None)`, `StopSession(session_id: SessionId)`, `BoardAction` = leur union ;
  - entrées sélectionnables : `SessionEntry(row: SessionRow)`, `RepoEntry(repo: Repo)`, `BoardEntry` = leur union ; `board_entries(data: BoardData) -> tuple[BoardEntry, ...]` (sessions dans l'ordre reçu, puis dépôts) ; `entry_key(entry: BoardEntry) -> str` (`session:<id>`, `repo:<id>`, pour garder la sélection quand les données changent) ;
  - `enter_action(entry: BoardEntry) -> ShowSession | LaunchBash` (session → `ShowSession` ; dépôt → `LaunchBash(repo.path, repo.id)`) ; `new_action(entry: BoardEntry) -> LaunchBash` (dépôt → le dépôt ; session → `LaunchBash(session.cwd, session.repo_id)`) ; `stop_target(entry: BoardEntry) -> Session | None` (dépôt → `None`) ;
  - `session_line(row: SessionRow, home: Path | None) -> str` : `▶ ` si `displayed`, sinon deux espaces, puis `{title}  {state_label}  {display_path(cwd)}` ;
  - `repo_line(repo: Repo) -> str` : `{name}` suivi de ` ({kind})` si le type est connu ;
  - textes exacts : `BOARD_TITLE = "meute"`, `SESSIONS_HEADING = "Sessions"`, `REPOS_HEADING = "Repositories"`, `ORPHANS_HEADING = "Orphans"`, `NO_SESSIONS = "No sessions. Pick a repository and press n."`, `FOOTER = "↑↓ select · Enter show · n new Bash · x stop"`, `confirm_stop_text(title: str) -> str` = `Stop "{title}"? y: yes · any other key: no`, `error_text(message: str) -> str` = `Error: {message}` ;
  - `board_lines(data: BoardData) -> list[str]` : titre, ligne vide, `Sessions`, les lignes de session (ou `NO_SESSIONS`), ligne vide, `Repositories`, les lignes de dépôt, puis, seulement s'il y a des orphelins, une ligne vide, `Orphans` et un identifiant par ligne. C'est la forme texte que le TUI reproduit ; elle sert aux instantanés.

- [ ] **Étape 1 : écrire les tests qui échouent.** Données fixes (`SessionId` et dates en dur) : deux sessions dont une affichée et une `Exited(code=2)` avec panneau, deux dépôts (un avec `rust`, un sans type), un orphelin, `home=Path("/home/me")`.
  - `test_board_lines` (instantané) et `test_board_lines_empty` (instantané : aucune session, aucun dépôt, aucun orphelin) ; relire chaque ligne contre la liste ci-dessus ;
  - `test_entries_are_sessions_then_repos`, `test_entry_keys_are_stable_and_distinct` ;
  - `test_enter_on_session_shows_and_on_repo_launches_there`, `test_new_on_session_launches_in_its_cwd_and_repo`, `test_stop_target_is_none_for_a_repo` ;
  - `test_confirm_and_error_texts`.
- [ ] **Étape 2 : constater l'échec.**
- [ ] **Étape 3 : implémenter.** Ajouter `tests/test_board_view.py` à la sélection de mutmut.
- [ ] **Étape 4 : vérification complète ; relire les instantanés.**
- [ ] **Étape 5 : `/simplify`, commit.** `git commit -m "feat(core): dashboard view model"`

---

### Task 9 : tableau de bord Textual (`meute.tui.board`)

**Fichiers :**
- Modifier : `pyproject.toml` et `uv.lock` (`uv add textual`, `uv add --dev pytest-textual-snapshot`), `CLAUDE.md` et `docs/dev/developpement-assiste-par-ia.md` § 4 (« `pytest-textual-snapshot` installé », phrase « sera ajouté par le plan qui en a besoin » retirée)
- Créer : `src/meute/tui/board.py`
- Test : `tests/test_tui_board.py`, instantanés SVG sous `tests/__snapshots__/test_tui_board/`

**Interfaces :**
- Consomme : tout `meute.core.board_view` (Task 8), `MeuteError`.
- Produit :
  - `class BoardBackend(Protocol)` : `load(self) -> BoardData | None` (`None` : rien n'a changé) et `perform(self, action: BoardAction) -> None` ; les deux lèvent `MeuteError` en cas d'échec ;
  - `class BoardApp(App[None])`, `BoardApp(backend: BoardBackend, *, poll_seconds: float = 0.5)` : au montage, `load()` puis un `set_interval(poll_seconds, …)` qui rappelle `load()` et remplace les données si elle renvoie des données ;
  - affichage : `BOARD_TITLE`, puis les sections dans l'ordre de `board_lines`, l'entrée sélectionnée mise en évidence, puis le pied (`FOOTER`, ou `confirm_stop_text`, ou `error_text`) ;
  - touches : `up`/`k` et `down`/`j` parcourent `board_entries`, bornées aux extrémités ; `enter` → `perform(enter_action)` ; `n` → `perform(new_action)` ; `x` sur une session → confirmation, puis `y` → `perform(StopSession)`, toute autre touche annule sans action ; `x` sur un dépôt ne fait rien ; quitter garde la touche par défaut de Textual (`ctrl+q`) ;
  - quand les données changent, la sélection suit `entry_key` ; si l'entrée a disparu, l'index est borné ;
  - une `MeuteError` de `load` ou `perform` s'affiche par `error_text(str(error))` jusqu'à la touche suivante ;
  - tout texte venant des données est affiché sans balisage (`markup=False` ou `rich.text.Text`), point de vigilance 1.
- Typage : Textual expose des `Any` ; une exception ciblée (`# pyright: ignore[reportAny] — raison`) est permise là où l'API l'impose, jamais un mode abaissé.

- [ ] **Étape 1 : écrire les tests qui échouent.** Un `FakeBackend` enregistre les actions et renvoie des `BoardData` fixes (celles de la Task 8). Les tests de comportement restent synchrones : `asyncio.run(scenario())`, où `scenario` utilise `app.run_test(size=(60, 30))` et `pilot.press(...)`.
  - comportement (niveau 2) : `test_enter_on_session_shows_it`, `test_enter_and_n_on_repo_launch_bash_there`, `test_n_on_session_launches_in_its_cwd`, `test_x_then_y_stops`, `test_x_then_other_key_cancels`, `test_x_on_repo_does_nothing`, `test_navigation_is_bounded`, `test_selection_survives_reordering` (la session sélectionnée passe de la 1ʳᵉ à la 2ᵉ position au rechargement et reste sélectionnée), `test_backend_error_is_shown_until_next_key`, `test_brackets_in_data_are_shown_literally` (titre `[wip] fix [/]` et dépôt `[bold]x` : aucun plantage, le texte exact apparaît à l'écran).
  - rendu (niveau 3, `snap_compare`) : `test_board_60_columns`, `test_board_100_columns`, `test_board_empty`, `test_board_confirming_stop`, `test_board_with_error`.
- [ ] **Étape 2 : constater l'échec.**
- [ ] **Étape 3 : `uv add textual`, `uv add --dev pytest-textual-snapshot` ; lire la documentation de la version installée (context7) ; implémenter.**
- [ ] **Étape 4 : vérifier.** Ouvrir le rapport HTML des instantanés et relire chaque rendu contre `board_lines` ; `bash scripts/verify.sh` (licences et `deptry` compris) ; le test `importtime` d'`ingest` passe toujours (Textual n'est pas chargé).
- [ ] **Étape 5 : `/simplify`, commit.** `git commit -m "feat(tui): minimal dashboard of sessions and repositories"`

---

### Task 10 : environnement tmux de la CLI, lancement Bash et `meute session new` [sécurité]

**Fichiers :**
- Modifier : `src/meute/core/config.py` (section `[keys]`), `tests/conftest.py` (exception autorisée n° 2), `src/meute/cli/__init__.py` (enregistrement de `session`, `TmuxError` traduite)
- Créer : `src/meute/cli/tmux_env.py`, `src/meute/cli/session_launch.py`, `src/meute/cli/session_commands.py`, `src/meute/cli/CLAUDE.md`
- Test : `tests/test_config.py` (nouveaux tests), `tests/test_cli_session_new.py`

Texte exact de `src/meute/cli/CLAUDE.md` :

```markdown
# meute.cli

CLI tests that touch tmux run through the `sandbox` fixture, which always sets
`MEUTE_TMUX_SOCKET=meute-test-<uuid>` and kills that server at the end.
```

**Interfaces :**
- Consomme : Tasks 1, 4, 5 ; `CliContext`, `open_context` (`meute/cli/context.py`).
- Produit, dans `config.py` : `KeysConfig(focus_board: str = "M-p", focus_main: str = "M-o")`, champ `Config.keys` ; validation `[A-Za-z0-9-]{1,20}`, message `keys.focus_board: expected a tmux key such as M-p` (idem `focus_main`) ; `DEFAULT_CONFIG` gagne, après la section `[ui]` et avant `[quotas]` :

  ```toml
  [keys]
  # Global shortcuts, without the tmux prefix (M- = Alt).
  focus_board = "M-p"
  focus_main = "M-o"
  ```

- Produit, dans `tmux_env.py` :
  - `meute_command() -> tuple[str, ...]` : `(sys.executable, "-m", "meute")` ;
  - `TmuxEnv(tmux: Tmux, spec: LayoutSpec, config_file: Path)` ;
  - `open_tmux_env(ctx: CliContext, environ: Mapping[str, str]) -> TmuxEnv` : `check_version()` ; socket `MEUTE_TMUX_SOCKET` (vide ou absente → `meute`) ; `LayoutSpec` depuis `ctx.config.ui` et `ctx.config.keys`, avec `board_command = meute_command() + ("board",)`, `welcome_command = … + ("welcome",)`, `sync_command = … + ("layout", "sync")` ; écriture atomique (`write_atomic`) de `render_config` dans `<state_dir>/tmux.conf`, passé à `Tmux` ;
- Produit, dans `session_launch.py` :
  - `BashLaunch(cwd: Path, title: str | None = None, repo_id: RepoId | None = None)` ;
  - `launch_bash(ctx: CliContext, env: TmuxEnv, request: BashLaunch, environ: Mapping[str, str]) -> Session` : `cwd.resolve()` doit être un dossier existant, sinon `InvalidInput("folder not found: <cwd>")` **avant** toute écriture et tout appel à tmux ; titre par défaut : nom du dossier ; `new_session_id()` ; `spawn_window` dans `BG_SESSION` avec la commande `(environ["SHELL"],)` (`/bin/sh` si absente ou vide), l'environnement `MEUTE_SESSION=<id>` et les options de pane `@meute_id=<id>` puis `remain-on-exit=on` ; puis `create_session` à l'état `Running()` ; si l'écriture en base échoue, le panneau est tué et l'erreur remonte.
- Produit, CLI : `meute session new [--cwd <dossier>] [--title <titre>] [--kind bash]` (`--cwd` : dossier courant par défaut ; `--kind` : `bash` par défaut, `claude` → `InvalidInput("only bash sessions are available for now")`) ; sortie : `Launched: {short_id} {title} ({display_path(cwd)})`. `run()` traduit une `TmuxError` en `meute: <message>` et code 1.
- Produit, pour les tests (exception autorisée n° 2) : `Sandbox` gagne `tmux_socket: str` (`meute-test-<uuid4().hex>`), toujours passé en `MEUTE_TMUX_SOCKET` avec `SHELL=/bin/sh` (une variable de `env=` les remplace) ; `Sandbox.tmux() -> Tmux` ; la fixture `sandbox` devient génératrice et tue ce serveur à la fin.

- [ ] **Étape 1 : écrire les tests qui échouent.**
  - config : `test_default_config_has_keys_section` (`config_get(path, "keys.focus_board") == "M-p"` sur le fichier écrit par `ensure_config`) ; `test_keys_must_be_tmux_keys` (paramétré : `"M-p \\; kill-server"`, `""`, `"M p"`, `"a" * 21` → `InvalidInput` au message exact) ; `test_keys_accept_letters_digits_and_dashes` (`"M-N"`, `"F5"`, `"C-M-x"`).
  - `test_cli_session_new.py` :
    - `test_new_launches_bash_in_bg_with_identity` : `session new --cwd <tmp>/w --title trial` → code 0, sortie `Launched: <8 car.> trial (<chemin>)` ; `list-panes -a -F '#{session_name} #{@meute_id} #{pane_current_path}'` sur le socket du bac à sable contient `meute-bg <id> <tmp>/w` ; en base, une session `bash`, `Running()`, titre `trial` ;
    - `test_title_defaults_to_the_folder_name` ;
    - `test_missing_cwd_fails_and_writes_nothing` (`meute: folder not found: …`, code 1, aucune session en base, `Sandbox.tmux().is_running()` faux) ; même attente pour un `--cwd` qui est un fichier ;
    - `test_claude_kind_is_refused` ;
    - `test_missing_tmux_is_reported` : `PATH` réduit au dossier de `sys.executable` → `meute: tmux not found: meute needs tmux 3.2 or later (for example: sudo apt install tmux)`, code 1 ;
    - `test_generated_conf_is_written_to_state_dir` : après `session new`, `<state>/meute/tmux.conf` commence par `# Generated by meute`.
- [ ] **Étape 2 : constater l'échec.**
- [ ] **Étape 3 : implémenter**, dont l'exception autorisée n° 2 (fixture seulement, aucune assertion touchée) ; le dire dans le message de commit.
- [ ] **Étape 4 : vérifier.** `bash scripts/verify.sh` ; `tmux -L meute ls` n'a pas changé.
- [ ] **Étape 5 : `/simplify`, `/security-review`, commit.** `git commit -m "feat: bash sessions in meute-bg and meute session new"`

---

### Task 11 : réconciliation branchée et `meute session list` [sécurité]

**Fichiers :**
- Créer : `src/meute/cli/session_refresh.py`
- Modifier : `src/meute/cli/session_commands.py`
- Test : `tests/test_session_refresh.py`, `tests/test_cli_session_list.py`, instantané `tests/__snapshots__/test_cli_session_list.ambr`

**Interfaces :**
- Consomme : `reconcile`, `PaneObservation` (Task 2), `list_panes`, `PaneInfo` (Task 4), `MAIN_SESSION` (Task 5), `SessionRow` (Task 8), `TmuxEnv` (Task 10).
- Produit :
  - `Snapshot(sessions: tuple[SessionRow, ...], orphans: tuple[str, ...])` ;
  - `refresh(ctx: CliContext, env: TmuxEnv) -> Snapshot` : `panes = list_panes(env.tmux)` d'abord (une erreur arrête tout avant la moindre écriture : point de vigilance 3), puis `apply_refresh(ctx.db, panes)` ;
  - `apply_refresh(db: Database, panes: Sequence[PaneInfo]) -> Snapshot` : observations des panneaux qui portent `@meute_id`, `list_sessions(include_ended=True)`, `reconcile`, `set_session_state` pour chaque mise à jour, puis lignes : sessions vivantes et sessions dont un panneau existe encore, dans l'ordre de `list_sessions` ; `has_pane` si un panneau porte l'identifiant ; `displayed` si ce panneau est dans la session `meute` ;
  - CLI `meute session list [--all] [--json]` : `refresh`, puis une ligne par session `{short_id}  {title}  {state_label}  {display_path(cwd)}` (`--all` : aussi les sessions terminées sans panneau), puis une ligne `orphan: {id}` par orphelin ; `--json` : `{"sessions": [session_to_json…], "orphans": […]}`.

- [ ] **Étape 1 : écrire les tests qui échouent.**
  - `tests/test_session_refresh.py` (base en mémoire, `PaneInfo` construits à la main) : `test_pane_in_meute_session_is_displayed`, `test_ended_session_with_dead_pane_is_listed`, `test_ended_session_without_pane_is_hidden`, `test_reconciled_states_are_written`, `test_refresh_writes_nothing_when_tmux_fails` (`env.tmux` vers un binaire absent par `PATH` vide → `NotInstalled`, les sessions vivantes en base restent `Running`).
  - `tests/test_cli_session_list.py` :
    - `test_exited_shell_is_reported_with_its_code` : `session new`, puis `send-keys -t <pane> 'exit 7' Enter`, attente du panneau mort, `session list` affiche `exited (7)` ;
    - `test_killed_pane_is_unreachable` ;
    - `test_list_without_server_marks_sessions_unreachable` : sessions créées directement en base avec des identifiants fixes, aucun serveur → instantané de `session list` (toutes `unreachable`) ;
    - `test_orphan_pane_is_listed` : panneau créé à la main dans `meute-bg` avec un `@meute_id` inconnu → ligne `orphan: <id>` ;
    - `test_list_json_shape` et `test_all_includes_ended_sessions`.
- [ ] **Étape 2 : constater l'échec.**
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète ; relire l'instantané.**
- [ ] **Étape 5 : `/simplify`, `/security-review`, commit.** `git commit -m "feat: reconcile sessions on read and meute session list"`

---

### Task 12 : afficher et arrêter une session (§ 5.1, 6.5) [sécurité]

**Fichiers :**
- Créer : `src/meute/cli/session_show.py`, `src/meute/cli/session_stop.py`
- Modifier : `src/meute/cli/session_commands.py`
- Test : `tests/test_cli_session_show_stop.py`, `tests/test_session_stop.py`

**Interfaces :**
- Consomme : `TmuxEnv` (Task 10), `refresh` (Task 11), `find_layout`, `ensure_layout`, `ROLE_WELCOME`, `STATUS_OPTION` (Task 5), `find_session` (Task 1).
- Produit :
  - `show_session(ctx: CliContext, env: TmuxEnv, session_id: SessionId) -> None` :
    1. `find_layout` ; absente → `InvalidInput('meute is not open: run "meute" first')` ;
    2. panneau portant l'identifiant ; absent → `InvalidInput("session unreachable: <title>")` ;
    3. disposition zoomée (mode étroit, § 5.2) → `switch_client_to(panneau)` et fin ;
    4. panneau déjà dans la zone principale → `select_pane` seulement (pas de `swap-pane` d'un panneau avec lui-même) ;
    5. sinon `swap_panes(panneau, main)` ; si l'ancien panneau principal avait le rôle `welcome`, il est tué ; puis `select_pane(panneau)` et `set_global_option(STATUS_OPTION, "▶ <title>")` ;
  - `STOP_GRACE_SECONDS = 5.0` (§ 6.5) ;
  - `stop_session(ctx: CliContext, env: TmuxEnv, session_id: SessionId, *, grace: float = STOP_GRACE_SECONDS) -> Session` : si le panneau est vivant, `send_keys(pane, "C-c")` puis, toutes les 100 ms, vérifier s'il est mort ou disparu, `grace` au plus ; s'il est encore vivant, `kill_pane` ; une session vivante passe à `Exited(code=<code du panneau mort, sinon None>)` ; une session déjà terminée garde son état ; un panneau mort restant est tué ; si une disposition existe, `ensure_layout` la répare (arrêt de la session affichée) ;
  - CLI `meute session show <id>` et `meute session stop <id> [--yes]` (identifiant ou préfixe, via `find_session`) ; sans `--yes`, question `Stop session "<title>"? [y/N] ` sur stderr et lecture d'une ligne ; `y` ou `yes` (sans casse, espaces retirés) confirment, toute autre réponse affiche `Cancelled.` et sort avec le code 0 ; après l'arrêt : `Stopped: {short_id} {title}`.

- [ ] **Étape 1 : écrire les tests qui échouent.** Chaque test de la CLI crée la disposition avec `ensure_layout` sur le socket du bac à sable, `board_command` et `welcome_command` à `("sh", "-c", "sleep 3600")` (le vrai tableau n'est branché qu'à la Task 13).
  - `test_show_swaps_session_into_main_and_drops_welcome` : le panneau principal de `meute:main` porte l'identifiant ; plus aucun panneau `welcome` ; `show-options -gv @meute_status` vaut `▶ <title>` ;
  - `test_show_second_session_sends_first_back_to_bg` : A puis B → B en principal, A dans `meute-bg`, le `PaneId` de A inchangé ;
  - `test_show_displayed_session_only_selects_it` : `show` A deux fois → succès, mêmes panneaux qu'après le premier appel ;
  - `test_show_without_layout_fails_with_hint` ;
  - `test_show_by_prefix_and_ambiguous_prefix` ;
  - `test_stop_with_yes_kills_and_marks_exited` : `SHELL` = un script `exec sleep 3600` (meurt sur `C-c`) → arrêt en moins de 5 s, état `exited`, plus de panneau ;
  - `test_stop_displayed_session_restores_welcome` : A affichée, `stop A --yes` → `meute:main` a de nouveau deux panneaux, dont un `welcome`, tableau à 60 colonnes ;
  - `test_stop_without_confirmation_cancels` : stdin `n\n` → `Cancelled.`, la session est toujours `running` ;
  - `tests/test_session_stop.py` : un shell qui ignore `SIGINT` (`sh -c "trap '' INT; sleep 3600"`) est tué après une `grace` de 0,2 s, et la session passe à `Exited(code=None)`.
- [ ] **Étape 2 : constater l'échec.**
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète.**
- [ ] **Étape 5 : `/simplify`, `/security-review`, commit.** `git commit -m "feat: show and stop a session (swap-pane, C-c then kill)"`

---

### Task 13 : `meute`, `meute layout sync`, `meute welcome` et `meute board` [sécurité]

**Fichiers :**
- Créer : `src/meute/cli/layout_commands.py`, `src/meute/cli/attach.py`, `src/meute/cli/board_backend.py`, `src/meute/cli/welcome.py`
- Modifier : `src/meute/cli/__init__.py` (callback racine `invoke_without_command=True`, commandes `board`, `welcome` et `layout`)
- Test : `tests/test_attach.py`, `tests/test_welcome.py`, `tests/test_cli_layout.py`, `tests/test_board_backend.py`, `tests/test_board_e2e.py`

**Interfaces :**
- Consomme : tout ce qui précède.
- Produit :
  - `meute layout sync` (cachée, `hidden=True`) : `open_tmux_env` ; si le serveur tourne, `source-file <tmux.conf>` ; puis `ensure_layout` ;
  - `attach_command(env: TmuxEnv, environ: Mapping[str, str]) -> tuple[list[str], dict[str, str]]` : arguments `env.tmux.base_args() + ["attach-session", "-t", "=meute:main"]` et l'environnement à passer, sans `TMUX` (§ 5.3) ;
  - `meute` sans sous-commande : `layout sync`, puis `subprocess.run` de `attach_command` avec les entrées-sorties héritées ; statut non nul → `MeuteError("attaching to tmux failed")` ; si `TMUX` est définie, avertissement sur stderr avant l'attachement, texte exact :
    `Warning: meute opens inside your current tmux. If it already uses {focus_board} or {focus_main}, change them in the [keys] section of {config file path}.` ;
  - `meute welcome` (cachée) : affiche `welcome_text(keys)` puis attend indéfiniment (`signal.pause()` en boucle) ; `welcome_text(keys: KeysConfig) -> str`, texte exact :

    ```
    meute

    Pick a session in the dashboard and press Enter.
    {focus_board}: dashboard · {focus_main}: main area
    ```

  - `CliBoardBackend(ctx: CliContext, env: TmuxEnv, *, monotonic: Callable[[], float] = time.monotonic)`, qui implémente `BoardBackend` :
    - `load()` : relit tout (`refresh` + `list_repos`, `home = Path.home()`) au premier appel, puis quand `db.data_version()` a changé ou que 2 s se sont écoulées depuis la dernière lecture de tmux (§ 4.5) ; sinon `None` ;
    - `perform(action)` : `ShowSession` → `show_session` ; `LaunchBash` → `launch_bash` puis `show_session` de la nouvelle session ; `StopSession` → `stop_session` ; une `TmuxError`, `OSError` ou `sqlite3.Error` est convertie en `MeuteError(str(error))`, que le tableau affiche ;
  - `meute board` : `scan_repos` une fois, puis `BoardApp(CliBoardBackend(…)).run()`, la base restant ouverte pendant toute la vie du tableau.

- [ ] **Étape 1 : écrire les tests qui échouent.**
  - unitaires : `test_attach_command_targets_main_window` (`-L <socket> -f <conf> attach-session -t =meute:main`) ; `test_attach_command_removes_tmux_variable` ; `test_welcome_text_uses_configured_keys` ;
  - `test_board_backend.py` (serveur de test, horloge `monotonic` simulée) : `test_first_load_returns_data`, `test_unchanged_load_returns_none`, `test_load_after_two_seconds_rereads_tmux`, `test_load_after_a_write_from_another_connection_rereads`, `test_tmux_error_becomes_meute_error` ;
  - `test_cli_layout.py` : `test_layout_sync_creates_board_and_welcome` (rôles `board` et `welcome` dans `meute:main` ; `#{pane_start_command}` du tableau contient `-m meute board`) ; `test_layout_sync_is_idempotent` ; `test_layout_sync_zooms_when_narrow` (`resize-window -x 100`, puis `layout sync` → `window_zoomed_flag` vaut `1`) ; `test_bare_meute_builds_layout_then_fails_to_attach_without_terminal` (stdin non terminal : disposition créée, `meute: attaching to tmux failed`, code 1) ; `test_bare_meute_inside_tmux_warns` (`TMUX` défini : l'avertissement exact sur stderr) ;
  - `test_board_e2e.py` (le vrai tableau dans le vrai panneau) : `layout sync`, puis `session new --cwd <tmp>/w --title trial` ; attendre que `capture-pane -p -t <board>` contienne `trial` ; `send-keys -t <board> Enter` ; attendre que le panneau principal porte l'identifiant de la session et qu'il n'existe plus de panneau `welcome`.
- [ ] **Étape 2 : constater l'échec.**
- [ ] **Étape 3 : implémenter.** `meute` sans argument affichait jusqu'ici une erreur de Typer : si un test existant échoue à cause du nouveau callback, s'arrêter et le signaler.
- [ ] **Étape 4 : vérifier, puis essai manuel** (à noter dans le rapport, avec le résultat de chaque point) : `uv run meute` dans un terminal de 200 colonnes → disposition, tableau à droite ; `n` sur un dépôt → nouvelle session Bash affichée ; `M-p` / `M-o` changent le focus ; `x` puis `y` arrête la session et le panneau d'accueil revient ; `prefix d` détache, `uv run meute` rattache et tout est là (critère n° 3) ; terminal réduit sous 120 colonnes → tableau en plein écran, `Enter` bascule vers la session, `M-p` revient. Puis `tmux -L meute kill-server`. Si l'environnement de l'agent n'a pas de terminal interactif, l'essai est laissé à l'auteur et noté comme tel dans la PR.
- [ ] **Étape 5 : `/simplify`, `/security-review`, commit.** `git commit -m "feat: meute command, layout on launch and wired dashboard"`

---

### Task 14 : tests de mutation, feuille de route et PR

**Fichiers :**
- Créer : `docs/dev/mutants/2026-plan-2-python.md`
- Modifier : `pyproject.toml` (`[tool.mutmut]`), nouveaux fichiers `tests/test_mutants_*.py` au besoin, `docs/superpowers/plans/2026-10-15-meute-v1-roadmap.md`

- [ ] **Étape 1 : étendre mutmut.** `source_paths` = `src/meute/core/`, `src/meute/git/`, `src/meute/tmux/parse.py`, `src/meute/tmux/conf.py` ; vérifier que la sélection de tests contient ceux ajoutés par les Tasks 1 à 8.
- [ ] **Étape 2 : lancer** `uv run mutmut run`, puis `uv run mutmut results` ; noter tués, survivants, délais dépassés.
- [ ] **Étape 3 : traiter chaque survivant du code nouveau ou modifié en TDD**, comme au plan 1 : un test qui tue le mutant (dans un `tests/test_mutants_*.py`), ou une phrase de justification si le mutant est équivalent. Aucun test existant modifié.
- [ ] **Étape 4 : écrire le rapport** `docs/dev/mutants/2026-plan-2-python.md` (même forme que `2026-plan-1-python.md`).
- [ ] **Étape 5 : feuille de route.** Ligne du plan 2 : « fait en Python » avec le lien vers ce plan ; section « Reports issus du plan 2 » avec la liste « Hors périmètre » ; noter que `meute session new --kind` vaudra `claude` par défaut au plan 3 ; garder le critère d'entrée du plan 3 (ouverture concurrente de la base).
- [ ] **Étape 6 : vérification complète**, plus `HYPOTHESIS_PROFILE=ci bash scripts/verify.sh` et `bash .claude/hooks/tests/run.sh`.
- [ ] **Étape 7 : `/simplify` puis `/security-review` sur toute la branche, revue finale, corrections.**
- [ ] **Étape 8 : commiter, pousser, ouvrir la PR.**

```bash
git commit -m "test: strengthen plan 2 tests after mutmut"
git push -u origin feat/plan-2-python
gh pr create --base main --assignee gaetinux --title "Plan 2 (Python): tmux, repositories and Bash sessions" \
  --body "<résumé des 14 tasks, les deux modifications de tests autorisées, les exceptions de lint, le rapport de mutation, l'essai manuel de la Task 13, puis « 🤖 Generated with [Claude Code](https://claude.com/claude-code) », sans lien de session>"
```
