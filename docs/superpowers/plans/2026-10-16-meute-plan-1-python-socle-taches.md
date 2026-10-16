# meute — Plan 1 Python : socle et tâches — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Objectif :** livrer, en Python, une gestion de tâches et de projets complète en CLI, adossée à SQLite : configuration, base et migrations, saisie rapide, contrôle de concurrence par version, historique et notes.

**Architecture :** toute la logique métier vit dans `meute.core` (stdlib uniquement) : modèle, saisie rapide, accès SQLite et migrations, lecture de la configuration, chemins XDG, modèles de vue. `meute.cli` n'est qu'une couche Typer qui appelle `meute.core`, met en forme la sortie (texte ou `--json`) et seule à écrire le TOML (`tomlkit`). Le code est synchrone. L'outillage (paquet uv, ruff, basedpyright, import-linter, gardes, hooks, CI) existe déjà depuis la migration : ce plan ne le refait pas.

**Stack technique :** Python 3.13, uv ; stdlib (`sqlite3`, `tomllib`, `datetime`, `zoneinfo`, `json`) ; Typer (déjà installé), `tomlkit` (ajouté au Task 9) ; tests : pytest, pytest-xdist (installés), `hypothesis` (Task 3), `syrupy` (Task 8), `mutmut` (Task 10).

**Spécification :** `docs/superpowers/specs/2026-10-15-meute-design.md` (§ 4.2, 4.3, 9.1–9.3, 13, 16, 17). Conception de la migration : `docs/superpowers/specs/2026-10-16-migration-python-design.md` (§ 3–5, 7.1). Guide : `docs/dev/developpement-assiste-par-ia.md`, qui fait partie des exigences. Feuille de route : `docs/superpowers/plans/2026-10-15-meute-v1-roadmap.md`.

**Référence de comportement :** les tests Rust sous le tag `rust-plan-2-wip` (`git show rust-plan-2-wip:<chemin>`) et le rapport `docs/dev/mutants/2026-plan-1.md`. Chaque tâche cite les tests qu'elle remplace. On les lit pour le comportement attendu, **sans les traduire mécaniquement** : chaque test Python est écrit en TDD, avec les textes anglais fixés ici. Sont hors périmètre : `session/`, `db/sessions.rs`, `db/repos.rs`, `repo.rs`, `cli/repo.rs`, `repos.rs`, `002_sessions.sql` et leurs tests.

**Prérequis :** la PR de migration (`chore/python-migration`) est mergée. Branche de ce plan : `feat/plan-1-python`, créée depuis `main`.

## Contraintes globales

**Code**
- `meute.core` n'importe que la stdlib et `meute.core.*` (garde `test_stdlib_only_packages`). `src/meute/core/__init__.py` et `src/meute/core/db/__init__.py` ne contiennent qu'une docstring, sans aucun import ni réexport (garde `test_core_init_has_no_imports` pour le premier). On importe toujours le sous-module précis (`from meute.core.task import Task`).
- Seul `meute.cli` importe `typer` et `tomlkit` (contrats import-linter existants).
- Données : `@dataclass(frozen=True, slots=True, kw_only=True)` ; une valeur par défaut qui est une instance passe par `field(default_factory=…)` (ruff `RUF009`, `B008`). Une variante porteuse de données est une dataclass gelée dans une union ; une variante sans donnée est une dataclass gelée **vide** (`case Todo():`) ; une énumération simple est un `enum.Enum`. Identifiants : `NewType`. Jamais de `case _:` sauf `case _: assert_never(x)`.
- Docstrings (Google) sur tout élément public de `meute.core`.
- Erreurs : hiérarchie `MeuteError` de `meute/core/errors.py` (spécification § 16). `OSError` et `sqlite3.Error` remontent tels quels, sauf mention contraire. Pas d'`assert` hors des tests, pas d'`except Exception`.
- Toutes les `datetime` du cœur sont **conscientes** (aware). Un instant est normalisé en UTC ; une heure locale est interprétée dans le fuseau de `now` (`zoneinfo`).
- Fichiers de moins de 300 lignes ; on découpe avant.
- Exceptions aux lints : une règle précise et ` — raison` (guide § 3), listées dans la PR.
- Dépendances uniquement avec `uv add` (`--dev` pour les tests), puis lecture de la documentation de la version installée (context7) avant d'utiliser l'API.

**Données et fichiers** (spécification § 13)
- Configuration `~/.config/meute/config.toml`, base `~/.local/share/meute/meute.db`, état `~/.local/state/meute/`, avec `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_STATE_HOME` respectées.
- Une configuration existante n'est **jamais** écrasée ; une écriture de fichier est atomique (fichier temporaire dans le même dossier, puis `os.replace`).
- SQLite : `journal_mode=WAL`, `foreign_keys=ON`, `busy_timeout` de 5000 ms pour la CLI, connexion en `autocommit=True` avec des transactions explicites `BEGIN IMMEDIATE`. Avant de migrer une base existante, sauvegarde `meute.db.bak-<version actuelle>`.
- Horodatages stockés en texte UTC de largeur fixe `YYYY-MM-DDTHH:MM:SS.ffffffZ` (27 caractères) ; dates sans heure en `YYYY-MM-DD`.

**Interface** : en anglais. Les textes affichés sont ceux de ce plan, copiés de la spécification quand elle les fixe (« modified in the meantime », symboles `·` `»` `✕` `◎` `✓`, groupes overdue · today · upcoming · no due date · done today).

**Qualité et workflow**
- Dans les blocs de tests, un test dont le corps est un commentaire est à écrire tel qu'il est décrit, avec ces valeurs ; les signatures et imports évidents sont omis.
- TDD strict (guide § 1) : test, échec pour la bonne raison, code minimal, refactorisation. Ne jamais modifier, supprimer ni désactiver un test existant pour le faire passer ; s'arrêter et le signaler.
- Instantanés `syrupy` relus ligne par ligne contre ce plan avant acceptation ; jamais `--snapshot-update` à l'aveugle.
- Chaque tâche se termine par : `bash scripts/verify.sh` au vert, `/simplify`, et `/security-review` pour les tâches marquées **[sécurité]** (fichiers, SQL, entrées externes). Puis un commit, message en anglais, terminé par `Co-Authored-By: Claude …`, sans ligne `Claude-Session` ni lien de session.
- Une PR à la fin, assignée à `gaetinux`, jamais de push sur `main`.

## Points de vigilance (Review Focus)

Comportements que la spécification implique sans les tester, les plus susceptibles de gêner l'auteur (Europe/Paris, français, configuration éditée à la main). Les cas déjà couverts par le plan Rust (ponctuation et e-mails dans la saisie rapide, saisie réduite à des jetons, deux écritures concurrentes, projet inconnu, configuration éditée à la main) restent des tests ordinaires des Tasks 3, 6, 8 et 1.

1. **Changements d'heure.** `>+24h` ajoute 24 h réelles, `>+1d` garde l'heure murale ; une heure locale inexistante (`2026-03-29T02:30`) est décalée à 03:30, une heure ambiguë (`2026-10-25T02:30`) prend la première occurrence. L'arithmétique `datetime + timedelta` de Python est murale : piège. Tests au Task 3 (`test_dst_*`) et au Task 7.
2. **Casse des noms de projet hors ASCII.** `COLLATE NOCASE` de SQLite ne replie que l'ASCII : `Équipe` et `équipe` seraient deux projets. On stocke une clé `name_key = name.casefold()` unique. Test au Task 5 (`test_project_names_fold_non_ascii_case`).
3. **Migration ratée ou base plus récente que le code.** Une migration qui échoue est annulée entière (version inchangée, aucune table partielle) ; une base de version supérieure est refusée sans être touchée. Tests au Task 4.
4. **Valeurs de configuration typées à la main.** `True` est un `int` en Python : `board_width = true` doit être refusé ; `config set` ne doit pas permettre d'injecter une section par un saut de ligne. Tests aux Tasks 1 et 9.
5. **Variables XDG vides ou relatives.** `XDG_DATA_HOME=""` ou `XDG_DATA_HOME=data` sont ignorées (spécification XDG), sinon la base serait créée relativement au dossier courant. Test au Task 1.

---

### Task 1 : erreurs, chemins XDG et lecture de la configuration [sécurité]

**Fichiers :**
- Créer : `src/meute/core/errors.py`, `src/meute/core/paths.py`, `src/meute/core/config.py`, `src/meute/core/CLAUDE.md`
- Test : `tests/test_paths.py`, `tests/test_config.py`

**Remplace :** `crates/meute-core/src/config/tests.rs` (sauf les tests de `config_set`, déplacés au Task 9), `crates/meute-core/tests/config_io_mutants.rs` (partie lecture), tests de `crates/meute-core/src/paths.rs`.

**Interfaces :**
- Produit, dans `errors.py` :
  - `class MeuteError(Exception)` ;
  - `class InvalidInput(MeuteError)`, construite avec un message ;
  - `class ConfigError(MeuteError)`, attributs `path: Path` et `message: str`, `str()` = `invalid configuration ({path}): {message}`.
- Produit, dans `paths.py` : `Paths(config_file: Path, db_file: Path, state_dir: Path)`, avec `Paths.from_roots(*, config_home: Path, data_home: Path, state_home: Path) -> Paths`, `Paths.from_env(environ: Mapping[str, str], *, home: Path) -> Paths` et `ensure_dirs(self) -> None`.
- Produit, dans `config.py` :
  - `DEFAULT_CONFIG: str` (texte exact ci-dessous) et `PERMISSION_MODES: frozenset[str]` = `manual`, `acceptEdits`, `plan`, `auto`, `dontAsk`, `bypassPermissions` ;
  - `ReposConfig(roots: tuple[str, ...] = ("~/git",))`, `ClaudeConfig(permission_mode: str = "manual")`, `UiConfig(board_width: int = 60, narrow_threshold: int = 120)`, `QuotasConfig(peak_timezone: str = "America/New_York", peak_start_hour: int = 8, peak_end_hour: int = 14)`, `Config(repos, claude, ui, quotas)` avec ces défauts ;
  - `validate_config(data: Mapping[str, object]) -> Config` (lève `InvalidInput`) ;
  - `config_key(key: str) -> tuple[str, str]` : `"ui.board_width"` → `("ui", "board_width")`, `InvalidInput("unknown key: <key>")` si la clé n'est pas un champ de `Config` ;
  - `write_atomic(path: Path, text: str) -> None` (crée les dossiers parents) ;
  - `ensure_config(path: Path) -> bool` (`True` si créé), `load_config(path: Path) -> Config`, `config_get(path: Path, key: str) -> str`.

`DEFAULT_CONFIG`, texte exact (valeurs des § 3.1, 5.1, 5.2, 6.2, 7.4, 10 de la spécification) :

```toml
# meute configuration — edit by hand or with `meute config set`.

[repos]
# Folders where meute looks for Git repositories (depth 3).
roots = ["~/git"]

[claude]
# Permission mode of the Claude sessions launched by meute:
# manual, acceptEdits, plan, auto, dontAsk, bypassPermissions.
permission_mode = "manual"

[ui]
# Dashboard width, in columns.
board_width = 60
# Below this terminal width, the dashboard goes full screen.
narrow_threshold = 120

[quotas]
# Peak hours: weekdays, from peak_start_hour to peak_end_hour, in this time zone.
peak_timezone = "America/New_York"
peak_start_hour = 8
peak_end_hour = 14
```

**Règles :**
- `from_env` : une variable absente, vide ou relative est ignorée ; défauts `home/.config`, `home/.local/share`, `home/.local/state`.
- `validate_config` : sections et clés inconnues ignorées (un ancien binaire lit un fichier récent) ; clé absente → défaut. Types : `roots` liste de chaînes ; `permission_mode` dans `PERMISSION_MODES` ; `board_width` et `narrow_threshold` entiers (pas `bool`) ≥ 1 ; `peak_start_hour` et `peak_end_hour` entiers (pas `bool`) entre 0 et 24 ; `peak_timezone` accepté par `zoneinfo.ZoneInfo`. Message : `<section.clé>: <attendu>`, par exemple `ui.board_width: expected an integer >= 1`.
- `load_config` : fichier absent → `Config()` ; `tomllib.TOMLDecodeError` ou `InvalidInput` → `ConfigError(path, message)` (le message de `tomllib` contient `line N`) ; toute autre `OSError` remonte (un dossier n'est pas « absent »).
- `config_get` : valeur du fichier, sinon défaut ; chaîne telle quelle, entier en décimal, liste en JSON (`["~/git"]`).
- `CLAUDE.md` du cœur, 10 lignes au plus : stdlib uniquement, `__init__.py` sans import, docstrings Google, `datetime` conscientes, erreurs `MeuteError`.

- [ ] **Étape 1 : écrire les tests qui doivent échouer.**

```python
# tests/test_paths.py
H = Path("/h")

def test_from_roots_appends_meute_segments() -> None:
    p = Paths.from_roots(config_home=Path("/t/c"), data_home=Path("/t/d"), state_home=Path("/t/s"))
    assert p == Paths(config_file=Path("/t/c/meute/config.toml"),
                      db_file=Path("/t/d/meute/meute.db"), state_dir=Path("/t/s/meute"))

def test_from_env_uses_xdg_variables() -> None:
    env = {"XDG_CONFIG_HOME": "/x/c", "XDG_DATA_HOME": "/x/d", "XDG_STATE_HOME": "/x/s"}
    assert Paths.from_env(env, home=H) == Paths.from_roots(
        config_home=Path("/x/c"), data_home=Path("/x/d"), state_home=Path("/x/s"))

def test_from_env_defaults_under_home() -> None:
    p = Paths.from_env({}, home=H)
    assert (p.config_file, p.db_file, p.state_dir) == (
        H / ".config/meute/config.toml", H / ".local/share/meute/meute.db", H / ".local/state/meute")

@pytest.mark.parametrize("value", ["", "relative/dir"])
def test_from_env_ignores_empty_and_relative_values(value: str) -> None:
    env = dict.fromkeys(("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"), value)
    assert Paths.from_env(env, home=H) == Paths.from_env({}, home=H)

def test_ensure_dirs_creates_parent_directories(tmp_path: Path) -> None: ...
    # from_roots sur tmp_path/c, /d, /s ; après ensure_dirs, c/meute, d/meute et s/meute sont des dossiers
```

```python
# tests/test_config.py
def test_ensure_config_writes_default_once_and_never_overwrites(tmp_path: Path) -> None:
    path = tmp_path / "sub/config.toml"
    assert ensure_config(path)
    assert path.read_text(encoding="utf-8") == DEFAULT_CONFIG
    path.write_text("# mine\n[ui]\nboard_width = 80\n", encoding="utf-8")
    assert not ensure_config(path)
    assert path.read_text(encoding="utf-8") == "# mine\n[ui]\nboard_width = 80\n"

def test_default_config_loads_to_defaults(tmp_path: Path) -> None:
    path = tmp_path / "c.toml"; path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    assert load_config(path) == Config()
    assert Config().repos.roots == ("~/git",) and Config().claude.permission_mode == "manual"
    assert (Config().ui.board_width, Config().ui.narrow_threshold) == (60, 120)
    assert (Config().quotas.peak_timezone, Config().quotas.peak_start_hour,
            Config().quotas.peak_end_hour) == ("America/New_York", 8, 14)

def test_missing_and_unknown_keys(tmp_path: Path) -> None:
    # "[ui]\nboad_width = 1\nboard_width = 70\n[perso]\nx = 1\n" → board_width 70, narrow_threshold 120

def test_invalid_toml_reports_path_and_line_without_touching_file(tmp_path: Path) -> None:
    # "[ui]\nboard_width = = 3\n" → ConfigError ; str contient "config.toml" et "line 2" ; fichier intact

@pytest.mark.parametrize(("text", "key"), [
    ('[ui]\nboard_width = "large"\n', "ui.board_width"),
    ("[ui]\nboard_width = true\n", "ui.board_width"),        # bool n'est pas un entier
    ("[ui]\nnarrow_threshold = 0\n", "ui.narrow_threshold"),
    ("[quotas]\npeak_end_hour = 25\n", "quotas.peak_end_hour"),
    ('[quotas]\npeak_timezone = "Mars/Olympus"\n', "quotas.peak_timezone"),
    ('[claude]\npermission_mode = "yolo"\n', "claude.permission_mode"),
    ('[repos]\nroots = "~/git"\n', "repos.roots"),
])
def test_wrong_values_are_config_errors_naming_the_key(tmp_path: Path, text: str, key: str) -> None:
    # load_config lève ConfigError dont str() contient key

def test_config_get_returns_file_value_then_default(tmp_path: Path) -> None:
    # fichier "[ui]\nboard_width = 72\n" : "ui.board_width" → "72", "claude.permission_mode" → "manual",
    # "repos.roots" → '["~/git"]'

def test_config_get_rejects_unknown_key(tmp_path: Path) -> None:
    # "ui.nope", "nope", "ui" → InvalidInput("unknown key: …")

def test_absent_file_yields_defaults_everywhere(tmp_path: Path) -> None:
    # load_config(tmp_path / "absent.toml") == Config() ; config_get(…, "ui.board_width") == "60"

def test_unreadable_path_is_an_os_error_not_defaults(tmp_path: Path) -> None:
    # load_config(tmp_path) et config_get(tmp_path, "ui.board_width") lèvent OSError
```

- [ ] **Étape 2 : constater l'échec.** `uv run pytest tests/test_paths.py tests/test_config.py` → `ModuleNotFoundError: No module named 'meute.core.paths'` (puis `config`).
- [ ] **Étape 3 : implémenter** `errors.py`, `paths.py`, `config.py` et `src/meute/core/CLAUDE.md` selon les interfaces et règles ci-dessus. `write_atomic` : `tempfile.NamedTemporaryFile(dir=path.parent, delete=False)`, écriture, puis `os.replace` ; le fichier temporaire est supprimé en cas d'erreur.
- [ ] **Étape 4 : constater le succès.** Même commande → tout passe.
- [ ] **Étape 5 : `bash scripts/verify.sh`, `/simplify`, `/security-review`.**
- [ ] **Étape 6 : commiter.** `git commit -m "feat(core): errors, XDG paths and configuration reading"`

---

### Task 2 : types du domaine

**Fichiers :**
- Créer : `src/meute/core/json_types.py`, `src/meute/core/instants.py`, `src/meute/core/status.py`, `src/meute/core/actor.py`, `src/meute/core/project.py`, `src/meute/core/task.py`
- Créer : `tests/support.py` (utilitaires non-fixtures, importés comme `guards`)
- Test : `tests/test_instants.py`, `tests/test_status.py`, `tests/test_task_model.py`

**Remplace :** `crates/meute-core/src/task/tests.rs`, tests de `crates/meute-core/src/actor.rs` et de `crates/meute-core/src/db/time.rs`.

**Interfaces :**
- Consomme : `InvalidInput` (Task 1).
- Produit :
  - `json_types.py` : `type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]` et `type JsonObject = dict[str, JsonValue]`.
  - `instants.py` : `utc_now() -> datetime` ; `to_db(at: datetime) -> str` (UTC, 27 caractères, `ValueError` si naïf) ; `from_db(text: str) -> datetime` ; `format_instant(at: datetime) -> str` (JSON, `2026-10-15T08:00:00Z`, microsecondes seulement si non nulles) ; `parse_zoned(text: str) -> datetime` (`2026-10-14T10:30[Europe/Paris]` → `datetime` consciente dans ce fuseau ; `InvalidInput` sinon).
  - `status.py` :
    - `class StatusKind(Enum)` : `TODO = "todo"`, `IN_PROGRESS = "in_progress"`, `BLOCKED = "blocked"`, `REVIEW = "review"`, `DONE = "done"`, avec les propriétés `label` (`to do`, `in progress`, `blocked`, `in review`, `done`) et `symbol` (`·`, `»`, `✕`, `◎`, `✓`, spécification § 9.5) ;
    - `parse_status_kind(text: str) -> StatusKind`, `InvalidInput("unknown status: <text>")` ;
    - variantes `Todo()`, `InProgress()`, `Blocked(reason: str)`, `Review()`, `Done()` et `TaskStatus = Todo | InProgress | Blocked | Review | Done` (alias utilisable dans `isinstance`). `Blocked.__post_init__` lève `InvalidInput("a blocked task needs a non-empty reason")` si `reason` est vide ou n'est pas égale à `reason.strip()` ;
    - `status_kind(status: TaskStatus) -> StatusKind`, `is_open(status: TaskStatus) -> bool` (faux seulement pour `Done`), `status_from_kind(kind: StatusKind, reason: str | None = None) -> TaskStatus` (`reason` nettoyée par `strip` ; ignorée hors `BLOCKED` ; manquante ou blanche pour `BLOCKED` → l'erreur ci-dessus) ;
    - `class Priority(Enum)` : `URGENT = "urgent"`, `HIGH = "high"`, `NORMAL = "normal"`, `LOW = "low"`, propriétés `marker` (`!!`, `!`, `""`, `""`) et `rank` (0 à 3, `URGENT` d'abord) ; `parse_priority(text: str) -> Priority`, `InvalidInput("unknown priority: <text>")`.
  - `actor.py` : `Author(Enum)` (`USER = "user"`, `CLAUDE = "claude"`, `SYSTEM = "system"`), `Channel(Enum)` (`TUI = "tui"`, `CLI = "cli"`, `MCP = "mcp"`, `FORGE = "forge"`), `Actor(author: Author, channel: Channel, session_id: str | None = None)`.
  - `project.py` : `ProjectId = NewType("ProjectId", int)`, `RepoId = NewType("RepoId", int)`, `Project(id, name, description, instructions, created_at)`, `ProjectRef(id: ProjectId, name: str)`, `project_to_json(project: Project) -> JsonObject` (clés `id`, `name`, `description`, `instructions`, `created_at`).
  - `task.py` :
    - `TaskId = NewType("TaskId", int)` et `task_label(task_id: TaskId) -> str` (`#12`) ;
    - `DueDate(day: date)`, `DueAt(at: datetime)` (`ValueError` si naïf ; stocké en UTC), `Due = DueDate | DueAt` ; `due_to_json(due: Due) -> JsonObject` (`{"kind": "date", "value": "2026-10-20"}` ou `{"kind": "at", "value": "2026-10-20T12:00:00Z"}`) et `due_from_json(data: Mapping[str, object]) -> Due` (`InvalidInput` sur une autre forme) ;
    - `Task(id: TaskId, title: str, description: str, status: TaskStatus, priority: Priority, due: Due | None, project: ProjectRef | None, repo_id: RepoId | None, version: int, created_at: datetime, updated_at: datetime, completed_at: datetime | None)` ;
    - `NewTask(title: str, description: str = "", priority: Priority = Priority.NORMAL, due: Due | None = None, project_id: ProjectId | None = None)` ;
    - `class Keep(Enum): KEEP = "keep"` et `KEEP = Keep.KEEP` ; `TaskPatch(title: str | Keep = KEEP, description: str | Keep = KEEP, status: TaskStatus | Keep = KEEP, priority: Priority | Keep = KEEP, due: Due | None | Keep = KEEP, project_id: ProjectId | None | Keep = KEEP)` — `KEEP` laisse le champ inchangé, `None` efface ;
    - `Note(id: int, task_id: TaskId, body: str, author: Author, channel: Channel, session_id: str | None, created_at: datetime)` ;
    - `TaskEvent(task_id: TaskId, field: str, old_value: str | None, new_value: str | None, author: Author, channel: Channel, session_id: str | None, created_at: datetime)` ;
    - `task_to_json(task: Task) -> JsonObject` : clés `id`, `title`, `description`, `status` (valeur du `StatusKind`), `blocked_reason` (raison ou `None`), `priority`, `due` (`due_to_json` ou `None`), `project` (`{"id", "name"}` ou `None`), `repo_id`, `version`, `created_at`, `updated_at`, `completed_at` (`format_instant`) ; `note_to_json(note: Note) -> JsonObject` (champs de `Note`, `author` et `channel` en valeur).
  - `tests/support.py` : `NOW = parse_zoned("2026-10-14T10:30[Europe/Paris]")` (un mercredi), `date_due(text: str) -> DueDate`, `at_due(zoned: str) -> DueAt`.

- [ ] **Étape 1 : écrire les tests qui doivent échouer.**

```python
# tests/test_status.py
ALL = [Todo(), InProgress(), Blocked(reason="x"), Review(), Done()]

def test_kinds_labels_symbols_match_spec() -> None:
    kinds = [status_kind(s) for s in ALL]
    assert [k.value for k in kinds] == ["todo", "in_progress", "blocked", "review", "done"]
    assert "".join(k.symbol for k in kinds) == "·»✕◎✓"
    assert [k.label for k in kinds] == ["to do", "in progress", "blocked", "in review", "done"]
    assert [is_open(s) for s in ALL] == [True, True, True, True, False]

def test_parse_status_kind_round_trips_and_rejects_unknown() -> None:
    assert all(parse_status_kind(k.value) is k for k in StatusKind)
    with pytest.raises(InvalidInput, match="^unknown status: bloqué$"):
        parse_status_kind("bloqué")

def test_status_from_kind_trims_reason_and_requires_it_for_blocked() -> None:
    assert status_from_kind(StatusKind.BLOCKED, "  waiting for CI ") == Blocked(reason="waiting for CI")
    assert status_from_kind(StatusKind.REVIEW, "ignored") == Review()
    for reason in (None, "", "   "):
        with pytest.raises(InvalidInput, match="needs a non-empty reason"):
            status_from_kind(StatusKind.BLOCKED, reason)

@pytest.mark.parametrize("reason", ["", "  ", " x"])
def test_blocked_rejects_blank_or_untrimmed_reason(reason: str) -> None:
    with pytest.raises(InvalidInput):
        Blocked(reason=reason)

def test_priority_markers_rank_and_parsing() -> None:
    assert [p.marker for p in Priority] == ["!!", "!", "", ""]
    assert sorted([Priority.LOW, Priority.URGENT, Priority.NORMAL, Priority.HIGH], key=lambda p: p.rank) \
        == [Priority.URGENT, Priority.HIGH, Priority.NORMAL, Priority.LOW]
    assert all(parse_priority(p.value) is p for p in Priority)
    with pytest.raises(InvalidInput, match="^unknown priority: nope$"):
        parse_priority("nope")

def test_author_and_channel_values_are_lowercase() -> None:
    assert (Author.CLAUDE.value, Channel.FORGE.value, Channel.MCP.value) == ("claude", "forge", "mcp")
```

```python
# tests/test_task_model.py
def test_task_json_is_flat_with_tagged_due() -> None:
    ts = datetime(2026, 10, 15, 8, 0, tzinfo=UTC)
    task = Task(id=TaskId(3), title="t", description="", status=Blocked(reason="waiting for review"),
                priority=Priority.HIGH, due=date_due("2026-10-20"),
                project=ProjectRef(id=ProjectId(1), name="meute"), repo_id=None, version=2,
                created_at=ts, updated_at=ts, completed_at=None)
    assert task_to_json(task) == {
        "id": 3, "title": "t", "description": "", "status": "blocked",
        "blocked_reason": "waiting for review", "priority": "high",
        "due": {"kind": "date", "value": "2026-10-20"}, "project": {"id": 1, "name": "meute"},
        "repo_id": None, "version": 2, "created_at": "2026-10-15T08:00:00Z",
        "updated_at": "2026-10-15T08:00:00Z", "completed_at": None}

def test_due_json_round_trips_and_rejects_other_shapes() -> None:
    at = DueAt(at=datetime(2026, 10, 20, 12, 0, tzinfo=UTC))
    assert due_to_json(at) == {"kind": "at", "value": "2026-10-20T12:00:00Z"}
    for due in (date_due("2026-10-20"), at):
        assert due_from_json(due_to_json(due)) == due
    for bad in ({"kind": "week", "value": "x"}, {"kind": "date"}, {"kind": "date", "value": "2026-02-30"}):
        with pytest.raises(InvalidInput):
            due_from_json(bad)

def test_due_at_is_aware_and_normalised_to_utc() -> None:
    assert at_due("2026-10-14T18:00[Europe/Paris]").at == datetime(2026, 10, 14, 16, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="naive"):
        DueAt(at=datetime(2026, 10, 14, 18, 0))  # noqa: DTZ001 — the naive value is the point

def test_task_label_has_hash() -> None:
    assert task_label(TaskId(12)) == "#12"
```

```python
# tests/test_instants.py
def test_to_db_is_fixed_width_and_sorts_like_instants() -> None:
    # 08:30:00, 08:30:00.5, 08:30:01, 08:30:01.000001 (UTC) : chaînes de 27 caractères, déjà triées

def test_to_db_round_trips_microseconds_and_rejects_naive() -> None:
    # to_db(2026-10-14T08:30:00.123456Z) == "2026-10-14T08:30:00.123456Z" ; from_db(to_db(t)) == t ;
    # to_db d'une heure de Paris est convertie en UTC ; datetime naïve → ValueError

def test_format_instant_omits_zero_microseconds() -> None:
    # "2026-10-15T08:00:00Z" et "2026-10-15T08:00:00.500000Z"

def test_parse_zoned_reads_the_bracketed_zone() -> None:
    assert NOW.utcoffset() == timedelta(hours=2) and NOW.astimezone(UTC).hour == 8
    for bad in ("2026-10-14T10:30", "2026-10-14T10:30[Mars/Olympus]", "garbage[Europe/Paris]"):
        with pytest.raises(InvalidInput):
            parse_zoned(bad)
```

- [ ] **Étape 2 : constater l'échec.** `uv run pytest tests/test_status.py tests/test_task_model.py tests/test_instants.py` → `ModuleNotFoundError`.
- [ ] **Étape 3 : implémenter** les six modules et `tests/support.py`. Toute fonction sur `TaskStatus` ou un `Enum` du cœur est un `match` exhaustif sans `case _:`.
- [ ] **Étape 4 : constater le succès.**
- [ ] **Étape 5 : `bash scripts/verify.sh`, `/simplify`.**
- [ ] **Étape 6 : commiter.** `git commit -m "feat(core): domain types for tasks, projects and actors"`

---

### Task 3 : saisie rapide et échéances

**Fichiers :**
- Créer : `src/meute/core/due_parse.py`, `src/meute/core/quick_add.py`, `tests/conftest.py`
- Modifier : `pyproject.toml` et `uv.lock` (via `uv add --dev hypothesis`), `.github/workflows/ci.yml` (variable `HYPOTHESIS_PROFILE: ci` sur l'étape `bash scripts/verify.sh`)
- Test : `tests/test_due_parse.py`, `tests/test_quick_add.py`

**Remplace :** `crates/meute-core/src/quick_add/tests.rs`, `crates/meute-core/tests/quick_add_due_mutants.rs`.

**Interfaces :**
- Consomme : `Priority`, `DueDate`, `DueAt`, `Due`, `InvalidInput`, `parse_zoned` (Tasks 1–2), `NOW`, `date_due`, `at_due` (`tests/support.py`).
- Produit : `parse_due(token: str, now: datetime) -> Due | None` (jeton sans le `>` ; aussi utilisé par `meute task edit --due`) ; `QuickAdd(title: str, project: str | None, priority: Priority, due: Due | None)` ; `parse_quick_add(text: str, now: datetime) -> QuickAdd`.
- Produit, dans `tests/conftest.py` : les profils hypothesis `dev` (défaut, 100 exemples) et `ci` (1000 exemples), choisis par `HYPOTHESIS_PROFILE`.

**Règles** (spécification § 9.3 ; ce qu'elle ne fixe pas est tranché ici) :
- L'entrée est découpée par `str.split()`. Seul un jeton qui **commence** par `@`, `!` ou `>` est candidat ; les autres jetons et les candidats non reconnus restent dans le titre, dans l'ordre, séparés par une espace.
- `@nom` (nom non vide) : projet, le dernier l'emporte. `!` → `HIGH`, `!!` → `URGENT`, le dernier l'emporte, `NORMAL` sinon ; `!!!` reste dans le titre. `>X` → `parse_due(X)` ; `None` → le jeton reste dans le titre.
- Titre vide après extraction → `InvalidInput("empty title")`.
- `parse_due`, mots-clés insensibles à la casse, interprétés dans le fuseau de `now` :

| Jeton | Résultat |
|---|---|
| `tomorrow` | `DueDate(aujourd'hui + 1)` |
| `tonight` | `DueAt(aujourd'hui 18:00)`, même si l'heure est passée |
| `mon` `tue` `wed` `thu` `fri` `sat` `sun` | `DueDate` du prochain jour de ce nom, **strictement** après aujourd'hui |
| `<jour>-<H>am`, `<jour>-<H>pm`, `<jour>-<H>:<MM>am`, `<jour>-<H>:<MM>pm` | `DueAt` ce jour-là ; H de 1 à 12 (1 ou 2 chiffres), MM de `00` à `59` (2 chiffres) ; `12am` = 00:00, `12pm` = 12:00. Aucune autre forme d'heure (`mon-14:00`, `mon-9`) |
| `+Nh`, `+Nm` | `DueAt(now + N heures / minutes)` en temps **réel** (calcul en UTC) ; N de 1 à 9999 |
| `+Nd` | `DueAt` N jours plus tard à la même heure **murale** |
| `YYYY-MM-DD` | `DueDate` si la date existe |
| `YYYY-MM-DDTHH:MM` | `DueAt` (heure locale) si elle existe ; séparateur `T` obligatoire |

- Les chiffres sont des chiffres ASCII (`s.isascii() and s.isdigit()`) : `str.isdigit()` seul accepte `²` et `٣`.
- Une heure locale est construite avec `datetime.combine(jour, heure, tzinfo=now.tzinfo)` puis convertie en UTC : une heure inexistante (saut de printemps) est ainsi décalée d'une heure, une heure ambiguë prend la première occurrence (`fold=0`).

- [ ] **Étape 1 : écrire les tests qui doivent échouer.** `NOW` est le mercredi 2026-10-14 à 10:30, Europe/Paris.

```python
# tests/test_due_parse.py
P = "[Europe/Paris]"

@pytest.mark.parametrize(("token", "expected"), [
    ("tomorrow", date_due("2026-10-15")), ("tonight", at_due(f"2026-10-14T18:00{P}")),
    ("mon", date_due("2026-10-19")), ("wed", date_due("2026-10-21")),
    ("mon-9am", at_due(f"2026-10-19T09:00{P}")), ("mon-2pm", at_due(f"2026-10-19T14:00{P}")),
    ("fri-2:30pm", at_due(f"2026-10-16T14:30{P}")), ("+2h", at_due(f"2026-10-14T12:30{P}")),
    ("+30m", at_due(f"2026-10-14T11:00{P}")), ("+3d", at_due(f"2026-10-17T10:30{P}")),
    ("2026-10-20", date_due("2026-10-20")), ("2026-10-20T14:00", at_due(f"2026-10-20T14:00{P}")),
    ("Tomorrow", date_due("2026-10-15")), ("MON-9AM", at_due(f"2026-10-19T09:00{P}")),
])
def test_due_forms_from_spec(token: str, expected: Due) -> None:
    assert parse_due(token, NOW) == expected

@pytest.mark.parametrize(("name", "day"), [("mon", "2026-10-19"), ("tue", "2026-10-20"),
    ("wed", "2026-10-21"), ("thu", "2026-10-15"), ("fri", "2026-10-16"), ("sat", "2026-10-17"),
    ("sun", "2026-10-18")])
def test_every_weekday_name_is_strictly_after_today(name: str, day: str) -> None:
    assert parse_due(name, NOW) == date_due(day)

def test_twelve_hour_bounds() -> None:
    assert parse_due("mon-12am", NOW) == at_due(f"2026-10-19T00:00{P}")
    assert parse_due("mon-12pm", NOW) == at_due(f"2026-10-19T12:00{P}")
    assert parse_due("mon-11:59pm", NOW) == at_due(f"2026-10-19T23:59{P}")

@pytest.mark.parametrize("token", [
    "mon-0am", "mon-13pm", "mon-9", "mon-14:00", "mon-9:60am", "mon-9:5am", "mon-009am",
    "2026-10-14 16:45", "2026-02-30", "2026-10-20T25:00", "+0h", "+10000h", "+2w", "+h", "soon",
    "+٣h", "+²h", "mon-٩am", "mon-+5pm", "", "monday",
])
def test_rejected_tokens(token: str) -> None:
    assert parse_due(token, NOW) is None

def test_delta_upper_bound_is_inclusive() -> None:
    assert parse_due("+9999h", NOW) is not None

# Changements d'heure (vigilance n° 1) : veille du passage à l'heure d'été.
SPRING = parse_zoned(f"2026-03-28T10:30{P}")

def test_dst_hours_are_real_time_and_days_are_wall_time() -> None:
    assert parse_due("+24h", SPRING) == at_due(f"2026-03-29T11:30{P}")
    assert parse_due("+1d", SPRING) == at_due(f"2026-03-29T10:30{P}")

def test_dst_gap_is_shifted_forward_and_ambiguous_time_takes_first() -> None:
    assert parse_due("2026-03-29T02:30", SPRING) == at_due(f"2026-03-29T03:30{P}")
    assert parse_due("2026-10-25T02:30", NOW) == DueAt(at=datetime(2026, 10, 25, 0, 30, tzinfo=UTC))
```

```python
# tests/test_quick_add.py
def test_full_syntax_from_spec() -> None:
    q = parse_quick_add("Review the PR @meute ! >tomorrow", NOW)
    assert q == QuickAdd(title="Review the PR", project="meute", priority=Priority.HIGH,
                         due=date_due("2026-10-15"))

def test_invalid_due_tokens_stay_in_title() -> None:
    q = parse_quick_add("Pay >2026-02-30 >mon-25pm >+0h >soon", NOW)
    assert (q.title, q.due) == ("Pay >2026-02-30 >mon-25pm >+0h >soon", None)

def test_punctuation_and_emails_are_not_tokens() -> None:
    q = parse_quick_add("Fix the bug! write to a@b.fr", NOW)
    assert (q.title, q.project, q.priority) == ("Fix the bug! write to a@b.fr", None, Priority.NORMAL)

def test_last_token_wins_and_triple_bang_stays() -> None:
    q = parse_quick_add("x @a @b ! !! !!!", NOW)
    assert (q.title, q.project, q.priority) == ("x !!!", "b", Priority.URGENT)

def test_lone_at_sign_stays_in_title() -> None:
    assert parse_quick_add("x @", NOW).title == "x @"

@pytest.mark.parametrize("text", ["@meute !! >tomorrow", "   ", ""])
def test_only_tokens_is_an_error(text: str) -> None:
    with pytest.raises(InvalidInput, match="^empty title$"):
        parse_quick_add(text, NOW)

@given(st.text(max_size=200))
def test_never_raises_anything_but_invalid_input(text: str) -> None:
    with contextlib.suppress(InvalidInput):
        parse_quick_add(text, NOW)
    parse_due(text, NOW)

@given(st.text(alphabet="abcXYZ019@!>+:- ", max_size=80))
def test_ok_title_is_non_empty_trimmed_single_spaced(text: str) -> None:
    with contextlib.suppress(InvalidInput):
        title = parse_quick_add(text, NOW).title
        assert title and title == title.strip() and "  " not in title

@given(st.lists(st.text(alphabet="abcdeéè", min_size=1, max_size=10), min_size=1, max_size=8))
def test_plain_words_are_kept_verbatim(words: list[str]) -> None:
    q = parse_quick_add(" ".join(words), NOW)
    assert (q.title, q.priority, q.project, q.due) == (" ".join(words), Priority.NORMAL, None, None)
```

- [ ] **Étape 2 : constater l'échec.** `uv add --dev hypothesis`, puis `uv run pytest tests/test_due_parse.py tests/test_quick_add.py` → `ModuleNotFoundError: No module named 'meute.core.due_parse'`.
- [ ] **Étape 3 : implémenter** `due_parse.py` (le tableau des règles), `quick_add.py`, les profils dans `tests/conftest.py` et la variable de CI.
- [ ] **Étape 4 : constater le succès**, aussi avec `HYPOTHESIS_PROFILE=ci uv run pytest tests/test_quick_add.py`.
- [ ] **Étape 5 : `bash scripts/verify.sh`, `/simplify`.**
- [ ] **Étape 6 : commiter.** `git commit -m "feat(core): quick entry and due date parsing"`

---

### Task 4 : ouverture de la base et migrations [sécurité]

**Fichiers :**
- Créer : `src/meute/core/db/__init__.py` (docstring seule), `src/meute/core/db/connection.py`, `src/meute/core/db/migrations.py`, `src/meute/core/db/sql/001_init.sql`
- Test : `tests/test_db_open.py`, `tests/test_migrations.py`

**Remplace :** `crates/meute-core/tests/db_open.rs`, tests de `crates/meute-core/src/db/migrations.rs` et de `crates/meute-core/src/db/mod.rs`, `pragma_string_rejects_empty_and_malformed_names` de `crates/meute-core/tests/db_errors_mutants.rs`.

**Interfaces :**
- Consomme : `MeuteError`, `InvalidInput`, `utc_now` (Tasks 1–2).
- Produit :
  - `errors.py` : `class MigrationError(MeuteError)` ;
  - `migrations.py` : `MIGRATIONS: tuple[str, ...]` (contenu des fichiers `sql/NNN_*.sql`, triés, lus par `importlib.resources`) ; `current_version(conn: sqlite3.Connection) -> int` (`PRAGMA user_version`) ; `backup_path(db_path: Path, version: int) -> Path` (`meute.db.bak-<version>` à côté) ; `migrate(conn: sqlite3.Connection, db_path: Path | None, migrations: Sequence[str] = MIGRATIONS) -> None` ;
  - `connection.py` : `Clock = Callable[[], datetime]` et la classe `Database` (dataclass gelée, champs `conn: sqlite3.Connection` et `clock: Clock`) :
    - `Database.open(path: Path, *, busy_timeout_ms: int, clock: Clock = utc_now) -> Database` : crée les dossiers parents, `sqlite3.connect(path, autocommit=True)`, pragmas `busy_timeout`, `journal_mode = WAL`, `foreign_keys = ON`, puis `migrate` ;
    - `Database.in_memory(*, clock: Clock = utc_now) -> Database` : `foreign_keys = ON`, puis `migrate(conn, None)` ;
    - `now(self) -> datetime`, `schema_version(self) -> int`, `pragma(self, name: str) -> str` (`name` doit correspondre à `[a-z_]+`, sinon `InvalidInput`) ;
    - `transaction(self) -> AbstractContextManager[sqlite3.Connection]` : `BEGIN IMMEDIATE`, `COMMIT` en sortie normale, `ROLLBACK` sur exception ;
    - `close(self)`, `__enter__` / `__exit__` (ferme la connexion).

**Règles de `migrate`** (spécification § 13) :
- Version actuelle `v`, cible `n = len(migrations)`. `v > n` → `MigrationError("database schema version {v} is newer than this meute ({n})")`, rien n'est touché. `v == n` → rien.
- `0 < v < n` et base fichier → sauvegarde `VACUUM INTO ?` vers `backup_path(path, v)`, après suppression d'une sauvegarde existante du même nom.
- Chaque migration `i` (de `v + 1` à `n`) s'exécute dans **une** transaction avec `PRAGMA user_version = i` ; en cas d'erreur `sqlite3.Error`, `ROLLBACK` puis `MigrationError("migration {i} failed: …")` chaînée (`from`).

**Migration 1** (`001_init.sql`) : seulement les tables de ce plan. `sessions`, `session_events`, `metric_samples`, `quota_samples` et `saved_states` arrivent avec les plans 2, 3 et 6.

```sql
CREATE TABLE projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL CHECK (length(trim(name)) > 0),
  -- name.casefold(), computed in Python: COLLATE NOCASE only folds ASCII.
  name_key TEXT NOT NULL UNIQUE,
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
  id INTEGER PRIMARY KEY AUTOINCREMENT,
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
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  body TEXT NOT NULL,
  author TEXT NOT NULL, channel TEXT NOT NULL, session_id TEXT,
  created_at TEXT NOT NULL
);
-- No foreign key: the history outlives the task.
CREATE TABLE task_events (
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL,
  field TEXT NOT NULL, old_value TEXT, new_value TEXT,
  author TEXT NOT NULL, channel TEXT NOT NULL, session_id TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX task_events_task ON task_events(task_id);
```

- [ ] **Étape 1 : écrire les tests qui doivent échouer.** Une fonction locale `tables(conn) -> set[str]` lit `sqlite_master` (hors `sqlite_%`).

```python
# tests/test_db_open.py
def test_open_creates_file_with_wal_and_latest_schema(tmp_path: Path) -> None:
    path = tmp_path / "sub/meute.db"
    with Database.open(path, busy_timeout_ms=5000) as db:
        assert path.exists()
        assert db.schema_version() == len(MIGRATIONS) == 1
        assert (db.pragma("journal_mode"), db.pragma("foreign_keys"), db.pragma("busy_timeout")) \
            == ("wal", "1", "5000")

def test_schema_has_plan_1_tables(tmp_path: Path) -> None:
    # {"projects", "repos", "project_repos", "tasks", "task_notes", "task_events"}

def test_in_memory_is_migrated_with_foreign_keys_and_clock() -> None:
    fixed = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    with Database.in_memory(clock=lambda: fixed) as db:
        assert (db.schema_version(), db.pragma("foreign_keys"), db.now()) == (1, "1", fixed)

def test_reopening_is_idempotent_and_makes_no_backup(tmp_path: Path) -> None:
    # deux ouvertures successives ; aucun fichier contenant ".bak-" dans tmp_path

@pytest.mark.parametrize("name", ["", "journal-mode", "Journal_Mode", "foreign keys",
                                  "user_version; DROP TABLE tasks"])
def test_pragma_rejects_malformed_names(name: str) -> None:
    with Database.in_memory() as db, pytest.raises(InvalidInput):
        db.pragma(name)

def test_transaction_rolls_back_on_error() -> None:
    # dans db.transaction(), INSERT d'un projet puis exception levée → aucune ligne dans projects
```

```python
# tests/test_migrations.py
V1 = ("CREATE TABLE a(x);",)
V2 = (*V1, "CREATE TABLE b(x);")

def test_upgrading_an_existing_file_backs_it_up_first(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    with closing(sqlite3.connect(path, autocommit=True)) as conn:
        migrate(conn, path, V1)
    with closing(sqlite3.connect(path, autocommit=True)) as conn:
        migrate(conn, path, V2)
        assert current_version(conn) == 2 and "b" in tables(conn)
    with closing(sqlite3.connect(tmp_path / "meute.db.bak-1")) as saved:
        assert tables(saved) == {"a"}

def test_existing_backup_is_replaced(tmp_path: Path) -> None:
    # un fichier "meute.db.bak-1" quelconque existe déjà ; la montée V1 → V2 réussit et le remplace

def test_fresh_file_makes_no_backup(tmp_path: Path) -> None:
    # migrate(conn, path, V2) sur un fichier neuf : version 2, aucun "*.bak-*"

def test_failed_migration_rolls_back_and_keeps_version(tmp_path: Path) -> None:
    # V1 appliquée ; puis (*V1, "CREATE TABLE c(x); CREATE TABLE broken(") → MigrationError,
    # current_version == 1, "c" absente

def test_newer_database_is_refused_untouched(tmp_path: Path) -> None:
    # V2 appliquée ; migrate(conn, path, V1) → MigrationError("…version 2 is newer than this meute (1)") ;
    # version toujours 2, aucune sauvegarde
```

- [ ] **Étape 2 : constater l'échec.** `uv run pytest tests/test_db_open.py tests/test_migrations.py` → `ModuleNotFoundError`.
- [ ] **Étape 3 : implémenter** `connection.py`, `migrations.py` et `001_init.sql`. Le SQL de migration est exécuté par `conn.executescript` encadré de `BEGIN IMMEDIATE;` et de `PRAGMA user_version = i; COMMIT;`. Vérifier que `sql/001_init.sql` est bien embarqué (`uv build`, puis le fichier figure dans la wheel).
- [ ] **Étape 4 : constater le succès.**
- [ ] **Étape 5 : `bash scripts/verify.sh`, `/simplify`, `/security-review`.**
- [ ] **Étape 6 : commiter.** `git commit -m "feat(core): SQLite database, migrations and pre-migration backup"`

---

### Task 5 : projets, création et lecture des tâches [sécurité]

**Fichiers :**
- Créer : `src/meute/core/db/rows.py`, `src/meute/core/db/projects.py`, `src/meute/core/db/tasks.py`
- Modifier : `tests/conftest.py`, `tests/support.py`
- Test : `tests/test_db_projects.py`, `tests/test_db_tasks.py`

**Remplace :** `crates/meute-core/tests/db_tasks.rs`, `create_project_only_maps_constraint_violations_to_duplicates` et `create_task_only_maps_foreign_key_violations_to_unknown_project` de `crates/meute-core/tests/db_errors_mutants.rs`, et les utilitaires de `crates/meute-core/tests/common/mod.rs`.

**Interfaces :**
- Consomme : `Database` (Task 4), types du Task 2.
- Produit :
  - `errors.py` : `class NotFound(MeuteError)`, attributs `entity: str` (`task` ou `project`) et `ident: str` (`#99`, `42`), `str()` = `{entity} not found: {ident}` ;
  - `rows.py` : `TASK_SELECT: str` (tâche + `LEFT JOIN projects`), `row_to_task(row) -> Task`, `row_to_event(row) -> TaskEvent`, `row_to_note(row) -> Note`, `fetch_task(conn: sqlite3.Connection, task_id: TaskId) -> Task` (`NotFound("task", "#N")`), `insert_event(conn, task_id, field, old, new, actor, now) -> None`, `due_columns(due: Due | None) -> tuple[str | None, str | None]` ;
  - `projects.py` : `create_project(db: Database, name: str, description: str = "") -> Project` (nom nettoyé ; vide → `InvalidInput("project name cannot be empty")` ; `name_key` déjà pris → `InvalidInput("project already exists: <name>")`, seulement pour `sqlite3.IntegrityError` de code `SQLITE_CONSTRAINT_UNIQUE`) ; `project_by_name(db, name: str) -> Project | None` (par `name.strip().casefold()`) ; `list_projects(db) -> list[Project]` (par `name_key`, puis `id`) ;
  - `tasks.py` :
    - `AnyProject()`, `InProject(project_id: ProjectId)`, `Floating()` et `ProjectFilter = AnyProject | InProject | Floating` (`Floating` : tâches sans projet, spécification § 9.5) ;
    - `TaskFilter(include_done: bool = False, project: ProjectFilter = field(default_factory=AnyProject), status: StatusKind | None = None)` : `status=DONE` **implique** les tâches terminées, même avec `include_done=False` ;
    - `create_task(db, new: NewTask, actor: Actor) -> Task` : titre nettoyé, vide → `InvalidInput("title cannot be empty")` ; statut `todo`, version 1 ; un événement `created` (`new_value` = titre) ; projet inconnu → `NotFound("project", "<id>")`, seulement pour `sqlite3.IntegrityError` de code `SQLITE_CONSTRAINT_FOREIGNKEY` ; tout dans une `db.transaction()` ;
    - `get_task(db, task_id: TaskId) -> Task`, `list_tasks(db, task_filter: TaskFilter) -> list[Task]` (par `id` croissant ; requête paramétrée, jamais de valeur interpolée), `history(db, task_id) -> list[TaskEvent]` (par `id`).
  - `tests/support.py` : `USER = Actor(author=Author.USER, channel=Channel.CLI)`, `CLAUDE = Actor(author=Author.CLAUDE, channel=Channel.MCP, session_id="s-1")`, `FIXED = datetime(2026, 10, 14, 8, 30, tzinfo=UTC)`, `new_task(title: str, project_id: ProjectId | None = None) -> NewTask`.
  - `tests/conftest.py` : fixtures `db` (`Database.in_memory(clock=lambda: FIXED)`, fermée après le test) et `file_db` (`tuple[Database, Path]` sur `tmp_path / "meute.db"`, même horloge).

- [ ] **Étape 1 : écrire les tests qui doivent échouer.**

```python
# tests/test_db_projects.py
def test_project_names_are_unique_ignoring_case(db: Database) -> None:
    create_project(db, "Meute")
    assert project_by_name(db, "meute") is not None
    with pytest.raises(InvalidInput, match="^project already exists: MEUTE$"):
        create_project(db, "MEUTE")
    with pytest.raises(InvalidInput, match="cannot be empty"):
        create_project(db, "  ")

def test_project_names_fold_non_ascii_case(db: Database) -> None:   # vigilance n° 2
    create_project(db, "Équipe")
    with pytest.raises(InvalidInput):
        create_project(db, "équipe")
    found = project_by_name(db, " ÉQUIPE ")
    assert found is not None and found.name == "Équipe"

def test_list_projects_is_sorted_by_name(db: Database) -> None:
    # "zeta", "Alpha", "beta" → ["Alpha", "beta", "zeta"] ; project_by_name(db, "x") is None

def test_create_project_only_maps_unique_violations(file_db: tuple[Database, Path]) -> None:
    db, path = file_db
    with closing(sqlite3.connect(path)) as raw:
        raw.execute("ALTER TABLE projects RENAME TO projects_gone")
    with pytest.raises(sqlite3.OperationalError):
        create_project(db, "x")
```

```python
# tests/test_db_tasks.py
def test_create_and_get_task_with_project(db: Database) -> None:
    p = create_project(db, "meute")
    t = create_task(db, NewTask(title="  Write the plan ", priority=Priority.HIGH, project_id=p.id), USER)
    assert (t.title, t.version, t.status, t.priority) == ("Write the plan", 1, Todo(), Priority.HIGH)
    assert t.project == ProjectRef(id=p.id, name="meute")
    assert (t.created_at, t.updated_at, t.completed_at) == (FIXED, FIXED, None)
    assert get_task(db, t.id) == t
    [event] = history(db, t.id)
    assert (event.field, event.new_value, event.author, event.channel) == \
        ("created", "Write the plan", Author.USER, Channel.CLI)

def test_list_filters_done_floating_project_and_status(file_db: tuple[Database, Path]) -> None:
    db, path = file_db
    a = create_project(db, "A")
    t1, t2, t3, t4 = (create_task(db, new_task(n, p), USER) for n, p in
                      (("t1", a.id), ("t2", None), ("t3", a.id), ("t4", None)))
    with closing(sqlite3.connect(path, autocommit=True)) as raw:  # no update API yet
        raw.execute("UPDATE tasks SET status='done', completed_at='2026-10-14T09:00:00.000000Z' WHERE id=3")
        raw.execute("UPDATE tasks SET status='blocked', blocked_reason='ci' WHERE id=4")
    def ids(task_filter: TaskFilter) -> list[TaskId]:
        return [t.id for t in list_tasks(db, task_filter)]
    assert ids(TaskFilter()) == [t1.id, t2.id, t4.id]
    assert ids(TaskFilter(project=Floating())) == [t2.id, t4.id]
    assert ids(TaskFilter(include_done=True, project=InProject(project_id=a.id))) == [t1.id, t3.id]
    assert ids(TaskFilter(status=StatusKind.DONE)) == [t3.id]          # done implique les terminées
    assert ids(TaskFilter(status=StatusKind.BLOCKED)) == [t4.id]
    assert get_task(db, t4.id).status == Blocked(reason="ci")

def test_get_missing_task_is_not_found(db: Database) -> None:
    with pytest.raises(NotFound, match=r"^task not found: #99$"):
        get_task(db, TaskId(99))

def test_create_with_unknown_project_is_not_found_and_creates_nothing(db: Database) -> None:
    # create_task(…, new_task("x", ProjectId(42))) → NotFound, entity "project", str "project not found: 42" ;
    # list_tasks(db, TaskFilter(include_done=True)) == []

def test_blank_title_is_rejected(db: Database) -> None:
    # "   " → InvalidInput("title cannot be empty") ; aucune tâche

def test_create_task_only_maps_foreign_key_violations(file_db: tuple[Database, Path]) -> None:
    # projet "p" créé ; trigger "BEFORE INSERT ON tasks BEGIN SELECT RAISE(ABORT, 'refused'); END"
    # posé par une seconde connexion → create_task lève sqlite3.IntegrityError, pas NotFound
```

- [ ] **Étape 2 : constater l'échec.** `uv run pytest tests/test_db_projects.py tests/test_db_tasks.py` → `ModuleNotFoundError`.
- [ ] **Étape 3 : implémenter** `rows.py`, `projects.py`, `tasks.py`, `NotFound`, et les ajouts à `tests/support.py` et `tests/conftest.py`. La conversion ligne → objet est regroupée dans `rows.py` ; une valeur de statut ou de priorité inconnue en base lève `ValueError` (base corrompue, pas une entrée utilisateur).
- [ ] **Étape 4 : constater le succès.**
- [ ] **Étape 5 : `bash scripts/verify.sh`, `/simplify`, `/security-review`.**
- [ ] **Étape 6 : commiter.** `git commit -m "feat(core): projects, task creation and listing"`

---

### Task 6 : mises à jour versionnées, notes et suppression [sécurité]

**Fichiers :**
- Créer : `src/meute/core/db/task_update.py`, `src/meute/core/db/task_notes.py`
- Test : `tests/test_db_task_update.py`, `tests/test_db_task_notes.py`

**Remplace :** `crates/meute-core/tests/db_task_update.rs`. Son test `blank_blocked_reason_is_rejected_and_nothing_written` est sans objet : `Blocked` ne peut plus être construit avec une raison blanche (Task 2).

**Interfaces :**
- Consomme : `Database`, `rows.*`, `get_task`, `history` (Tasks 4–5), `TaskPatch`, `KEEP` (Task 2).
- Produit :
  - `errors.py` : `class VersionConflict(MeuteError)`, attribut `current: Task`, `str()` = `modified in the meantime (current version: {current.version})` (spécification § 9.2 ; `Task` importé sous `TYPE_CHECKING`) ;
  - `task_update.py` : `update_task(db, task_id: TaskId, expected_version: int, patch: TaskPatch, actor: Actor) -> Task` et `delete_task(db, task_id: TaskId, expected_version: int, actor: Actor) -> None` ;
  - `task_notes.py` : `add_note(db, task_id: TaskId, body: str, actor: Actor) -> Note` et `notes(db, task_id: TaskId) -> list[Note]` (par `id`).

**Règles** (spécification § 9.1, 9.2) :
- Tout se fait dans `db.transaction()` (`BEGIN IMMEDIATE`). On relit la tâche (`NotFound` si absente). Version différente → `VersionConflict(current)`, rien n'est écrit.
- Le titre du patch est nettoyé, vide → `InvalidInput("title cannot be empty")`. Un projet inconnu → `NotFound("project", …)`, rien n'est écrit.
- Patch sans changement réel → la tâche inchangée, sans nouvelle version ni événement.
- Sinon : `UPDATE … WHERE id = ? AND version = ?` avec `version = version + 1` et `updated_at = now` ; zéro ligne → `VersionConflict` sur la tâche relue. Un événement par champ modifié, dans l'ordre `title`, `description`, `status`, `priority`, `due`, `project`. Valeurs : texte pour le titre et la description ; valeur du `StatusKind`, ou `blocked: <raison>` pour `Blocked` ; valeur de `Priority` ; `due_to_json(due)["value"]` ; nom du projet. Une valeur absente vaut `None`.
- `completed_at` : `now` au passage à `Done`, conservé si la tâche reste `Done`, `None` en sortant de `Done`.
- Note : corps nettoyé, vide → `InvalidInput("note cannot be empty")` ; tâche absente → `NotFound` ; la version de la tâche ne change pas.
- Suppression : contrôle de version comme ci-dessus, événement `deleted` (`old_value` = titre), puis `DELETE` (notes en cascade, historique conservé). Les identifiants ne sont jamais réutilisés (`AUTOINCREMENT`).

- [ ] **Étape 1 : écrire les tests qui doivent échouer.** Utilitaire local `with_task(db) -> Task` : crée « Review the PR » (version 1).

```python
# tests/test_db_task_update.py
def test_update_bumps_version_once_and_logs_each_field(db: Database) -> None:
    t = with_task(db)
    t2 = update_task(db, t.id, 1, TaskPatch(title="New", priority=Priority.URGENT), USER)
    assert (t2.title, t2.priority, t2.version) == ("New", Priority.URGENT, 2)
    assert [e.field for e in history(db, t.id)] == ["created", "title", "priority"]

def test_event_values_use_kinds_text_and_project_name(db: Database) -> None:
    t = with_task(db)
    p = create_project(db, "meute")
    update_task(db, t.id, 1, TaskPatch(status=InProgress(), due=date_due("2026-11-01"), project_id=p.id), CLAUDE)
    update_task(db, t.id, 2, TaskPatch(status=Blocked(reason="waiting for CI"), project_id=None), USER)
    events = history(db, t.id)
    assert [(e.field, e.old_value, e.new_value) for e in events[1:]] == [
        ("status", "todo", "in_progress"), ("due", None, "2026-11-01"), ("project", None, "meute"),
        ("status", "in_progress", "blocked: waiting for CI"), ("project", "meute", None)]
    assert (events[1].author, events[1].channel, events[1].session_id) == (Author.CLAUDE, Channel.MCP, "s-1")

def test_stale_version_is_rejected_with_current_state_and_no_event(db: Database) -> None:
    t = with_task(db)
    update_task(db, t.id, 1, TaskPatch(title="A"), USER)
    with pytest.raises(VersionConflict, match=r"^modified in the meantime \(current version: 2\)$") as err:
        update_task(db, t.id, 1, TaskPatch(title="B"), CLAUDE)
    assert (err.value.current.title, err.value.current.version) == ("A", 2)
    assert len(history(db, t.id)) == 2

def test_noop_patch_changes_nothing(db: Database) -> None:
    # TaskPatch() et TaskPatch(title=" Review the PR ") → version 1, un seul événement

def test_blank_title_is_rejected_and_nothing_written(db: Database) -> None: ...

def test_done_sets_keeps_and_clears_completed_at(db: Database) -> None:
    # → Done : completed_at == FIXED ; Done + titre changé : completed_at conservé ; → Review : None

def test_patch_with_unknown_project_is_not_found_and_nothing_written(db: Database) -> None:
    # project_id=ProjectId(42) → NotFound (entity "project") ; version 1, un événement

def test_update_missing_task_is_not_found(db: Database) -> None: ...

def test_two_connections_same_version_second_conflicts(tmp_path: Path) -> None:
    # deux Database.open sur le même fichier ; a met à jour en version 1 (succès, "From A"),
    # b met à jour en version 1 → VersionConflict, current.title == "From A" ; 2 événements

def test_delete_checks_version_and_keeps_history(db: Database) -> None:
    t = with_task(db)
    add_note(db, t.id, "n", USER)
    with pytest.raises(VersionConflict):
        delete_task(db, t.id, 7, USER)
    delete_task(db, t.id, 1, USER)
    with pytest.raises(NotFound):
        get_task(db, t.id)
    last = history(db, t.id)[-1]
    assert (last.field, last.old_value) == ("deleted", "Review the PR")
    assert notes(db, t.id) == []

def test_task_ids_are_never_reused_after_delete(db: Database) -> None:
    # "one", "two" (supprimée), "three" → id 3 ; historique de 2 == ["created", "deleted"]

def test_stored_timestamps_are_fixed_width_utc(file_db: tuple[Database, Path]) -> None:
    # projet, tâche avec due=DueAt, note, passage à Done ; lus par une seconde connexion :
    # projects.created_at, tasks.created_at/updated_at/completed_at/due_at, task_notes.created_at,
    # task_events.created_at ont 27 caractères et finissent par "Z"
```

```python
# tests/test_db_task_notes.py
def test_notes_do_not_bump_version_and_keep_author(db: Database) -> None:
    t = with_task(db)
    note = add_note(db, t.id, "  Done with the SQL part ", CLAUDE)
    assert (note.body, note.author, note.channel, note.session_id) == \
        ("Done with the SQL part", Author.CLAUDE, Channel.MCP, "s-1")
    assert get_task(db, t.id).version == 1 and notes(db, t.id) == [note]

def test_blank_note_and_missing_task_are_rejected(db: Database) -> None:
    # "  " → InvalidInput("note cannot be empty") ; TaskId(9) → NotFound
```

- [ ] **Étape 2 : constater l'échec.** `uv run pytest tests/test_db_task_update.py tests/test_db_task_notes.py` → `ModuleNotFoundError`.
- [ ] **Étape 3 : implémenter** `VersionConflict`, `task_update.py` et `task_notes.py` selon les règles. Le calcul des changements (`TaskPatch` appliqué à la tâche courante → valeurs suivantes et liste des changements) est une fonction pure, séparée de l'écriture.
- [ ] **Étape 4 : constater le succès.**
- [ ] **Étape 5 : `bash scripts/verify.sh`, `/simplify`, `/security-review`.**
- [ ] **Étape 6 : commiter.** `git commit -m "feat(core): versioned task updates, notes and deletion"`

---

### Task 7 : regroupement par urgence, tri et affichage des échéances

**Fichiers :**
- Créer : `src/meute/core/views.py`
- Modifier : `tests/support.py`
- Test : `tests/test_views.py`

**Remplace :** `crates/meute-core/src/views/tests.rs`, `crates/meute-core/tests/views_boundary_mutants.rs`.

**Interfaces :**
- Consomme : `Task`, `Due`, `Priority`, statuts (Task 2).
- Produit :
  - `class Bucket(Enum)` : `OVERDUE`, `TODAY`, `UPCOMING`, `NO_DUE`, `DONE_TODAY`, propriété `label` : `Overdue`, `Today`, `Upcoming`, `No due date`, `Done today` (spécification § 9.5) ;
  - `bucket_of(task: Task, now: datetime) -> Bucket | None` ; `is_overdue(task: Task, now: datetime) -> bool` ; `sort_for_display(tasks: Iterable[Task], now: datetime) -> list[Task]` (fuseau de `now`) ; `format_due(due: Due, now: datetime) -> str`.
  - `tests/support.py` : `make_task(task_id: int, *, due: Due | None = None, status: TaskStatus | None = None, priority: Priority = Priority.NORMAL, completed_at: datetime | None = None) -> Task` (`None` → `Todo()`, titre `task <id>`, horodatages fixes).

**Règles :**
- `Done` : `DONE_TODAY` si `completed_at` tombe aujourd'hui dans le fuseau de `now`, `None` sinon.
- Ouverte avec `DueDate(d)` : `OVERDUE` si `d` < aujourd'hui, `TODAY` si égal, `UPCOMING` sinon. Avec `DueAt(t)` : `OVERDUE` si `t` < `now` (strictement), `TODAY` si `t` tombe aujourd'hui (heure locale), `UPCOMING` sinon. Sans échéance : `NO_DUE`.
- Tri : échéance croissante, une `DueDate` comptant pour 23:59:59 ce jour-là dans le fuseau de `now`, l'absence d'échéance en dernier ; puis `Priority.rank` ; puis `id`.
- `format_due`, dans le fuseau de `now` : date `today`, `tomorrow`, sinon `Mon Oct 19` (jour et mois abrégés en anglais, jour du mois sans zéro), suivie de l'année si elle diffère (`Tue Jan 5 2027`) ; `DueAt` : la même forme puis l'heure sur 12 heures, sans minutes nulles (`today 6pm`, `Fri Oct 16 2:30pm`, `Mon Oct 19 12am`, `12pm` à midi). Les noms viennent de deux tuples constants, **jamais** de `strftime("%a")`, qui dépend de la locale.

- [ ] **Étape 1 : écrire les tests qui doivent échouer.**

```python
# tests/test_views.py
P = "[Europe/Paris]"

@pytest.mark.parametrize(("task", "bucket"), [
    (make_task(1, due=date_due("2026-10-13")), Bucket.OVERDUE),
    (make_task(2, due=at_due(f"2026-10-14T09:00{P}")), Bucket.OVERDUE),
    (make_task(3, due=date_due("2026-10-14")), Bucket.TODAY),
    (make_task(4, due=at_due(f"2026-10-14T18:00{P}")), Bucket.TODAY),
    (make_task(5, due=date_due("2026-10-15")), Bucket.UPCOMING),
    (make_task(6), Bucket.NO_DUE),
    (make_task(7, status=Done(), completed_at=datetime(2026, 10, 14, 7, 0, tzinfo=UTC)), Bucket.DONE_TODAY),
    # 23:30 UTC le 13 = 01:30 à Paris le 14
    (make_task(8, status=Done(), completed_at=datetime(2026, 10, 13, 23, 30, tzinfo=UTC)), Bucket.DONE_TODAY),
    (make_task(9, status=Done(), completed_at=datetime(2026, 10, 13, 7, 0, tzinfo=UTC)), None),
    (make_task(10, due=date_due("2026-10-13"), status=Review()), Bucket.OVERDUE),
])
def test_buckets_follow_rules(task: Task, bucket: Bucket | None) -> None:
    assert bucket_of(task, NOW) == bucket

def test_deadline_exactly_now_is_not_overdue() -> None:
    assert not is_overdue(make_task(1, due=DueAt(at=NOW)), NOW)
    assert is_overdue(make_task(1, due=DueAt(at=NOW - timedelta(seconds=1))), NOW)
    assert not is_overdue(make_task(1, due=date_due("2026-10-13"), status=Done()), NOW)

def test_sort_by_due_then_priority_then_id() -> None:
    tasks = [make_task(1, priority=Priority.URGENT),
             make_task(2, due=date_due("2026-10-15"), priority=Priority.LOW),
             make_task(3, due=date_due("2026-10-15"), priority=Priority.HIGH),
             make_task(4, due=at_due(f"2026-10-15T09:00{P}"), priority=Priority.LOW)]
    assert [t.id for t in sort_for_display(tasks, NOW)] == [4, 3, 2, 1]

@pytest.mark.parametrize(("due", "text"), [
    (date_due("2026-10-14"), "today"), (date_due("2026-10-15"), "tomorrow"),
    (date_due("2026-10-19"), "Mon Oct 19"), (date_due("2027-01-05"), "Tue Jan 5 2027"),
    (at_due(f"2026-10-14T18:00{P}"), "today 6pm"), (at_due(f"2026-10-16T14:30{P}"), "Fri Oct 16 2:30pm"),
    (at_due(f"2026-10-19T00:00{P}"), "Mon Oct 19 12am"), (at_due(f"2026-10-15T12:00{P}"), "tomorrow 12pm"),
])
def test_due_formatting_in_english(due: Due, text: str) -> None:
    assert format_due(due, NOW) == text

def test_due_at_is_shown_in_local_time_across_dst() -> None:
    # 2026-10-25T01:30Z (après le passage à l'heure d'hiver) vu depuis NOW → "Sun Oct 25 2:30am"

def test_bucket_labels() -> None:
    assert [b.label for b in Bucket] == ["Overdue", "Today", "Upcoming", "No due date", "Done today"]
```

- [ ] **Étape 2 : constater l'échec.** `uv run pytest tests/test_views.py` → `ModuleNotFoundError`.
- [ ] **Étape 3 : implémenter `views.py`** et `make_task`.
- [ ] **Étape 4 : constater le succès.**
- [ ] **Étape 5 : `bash scripts/verify.sh`, `/simplify`.**
- [ ] **Étape 6 : commiter.** `git commit -m "feat(core): urgency buckets, display order and due formatting"`

---

### Task 8 : CLI — contexte, ajout, liste et affichage des tâches, projets [sécurité]

**Fichiers :**
- Créer : `src/meute/cli/context.py`, `src/meute/cli/render.py`, `src/meute/cli/task_app.py`, `src/meute/cli/task_commands.py`, `src/meute/cli/project_commands.py`
- Modifier : `src/meute/cli/__init__.py`, `tests/conftest.py`, `tests/support.py`, `pyproject.toml` et `uv.lock` (via `uv add --dev syrupy`)
- Test : `tests/test_cli_tasks.py`, `tests/test_cli_projects.py`, `tests/test_cli_errors.py`, instantanés `tests/__snapshots__/test_cli_tasks.ambr`

**Remplace :** `crates/meute/tests/cli_tasks.rs`, `crates/meute/tests/cli_errors.rs`, `crates/meute/tests/support/mod.rs` et les instantanés `cli_tasks__snapshot_task_list_mixed.snap` et `cli_tasks__snapshot_task_show_with_notes.snap`.

**Interfaces :**
- Consomme : tout `meute.core` (Tasks 1–7).
- Produit :
  - `context.py` :
    - `local_zone(environ: Mapping[str, str]) -> tzinfo` : `ZoneInfo(environ["TZ"])` si la variable est un nom IANA valide, sinon `ZoneInfo.from_file` sur `/etc/localtime`, sinon UTC. Jamais `datetime.now().astimezone()`, dont le décalage fixe fausse `>+1d` et `>tonight` autour d'un changement d'heure ;
    - `current_time(environ: Mapping[str, str]) -> datetime` : `parse_zoned(environ["MEUTE_NOW"])` si la variable est définie (tests de bout en bout, non documentée), sinon `datetime.now(local_zone(environ))` ; invalide → `InvalidInput("invalid MEUTE_NOW: <valeur>")` ;
    - `CliContext(db: Database, now: datetime, actor: Actor, config: Config, paths: Paths)` ;
    - `open_context(environ: Mapping[str, str]) -> AbstractContextManager[CliContext]` : `Paths.from_env(environ, home=Path.home())`, `ensure_dirs`, `ensure_config`, `load_config`, `Database.open(db_file, busy_timeout_ms=5000, clock=…)` (horloge figée sur `now` si `MEUTE_NOW` est définie), acteur `USER` / `CLI` avec `session_id = environ.get("MEUTE_SESSION")` ; ferme la base en sortie ;
    - `require_project(ctx: CliContext, name: str) -> Project` : `InvalidInput("unknown project: <name> (projects: a, b)")`, ou `(no projects)` s'il n'y en a aucun. On ne crée jamais de projet sur une faute de frappe.
  - `render.py` (fonctions pures) : `task_line(task: Task, now: datetime) -> str`, `preview_line(parsed: QuickAdd, now: datetime) -> str`, `task_detail(task: Task, notes: Sequence[Note], now: datetime) -> str`.
  - `task_app.py` : `task_app = typer.Typer(no_args_is_help=True)`, partagé par `task_commands.py` (Task 8) et `task_edit_commands.py` (Task 9).
  - `cli/__init__.py` : `app.add_typer(task_app, name="task")` et `project_app`, imports des modules de commandes ; `run(argv)` traduit les erreurs (ci-dessous).
  - `tests/conftest.py` : fixture `sandbox(tmp_path) -> Sandbox`, avec `Sandbox.root: Path`, `Sandbox.run(*args: str, env: Mapping[str, str] | None = None, stdin: str = "") -> subprocess.CompletedProcess[str]` (sous-processus `sys.executable -m meute`, environnement copié sans `MEUTE_SESSION`, avec `HOME=root/home`, `XDG_CONFIG_HOME=root/config`, `XDG_DATA_HOME=root/data`, `XDG_STATE_HOME=root/state`, `MEUTE_NOW=2026-10-14T10:30[Europe/Paris]`) et `Sandbox.db() -> AbstractContextManager[Database]` (`root/data/meute/meute.db`, horloge `FIXED`).
  - `tests/support.py` : `seed_mixed(db: Database) -> None` et `load_json(text: str) -> object` (`json.loads`, une seule suppression `reportAny` justifiée).

**Commandes et sorties** (les arguments de `task add` sont joints par des espaces) :

| Commande | Sortie |
|---|---|
| `meute task add <saisie…> [--dry-run]` | `Created: <task_line>` ; avec `--dry-run`, `Parsed: <preview_line>` et rien n'est créé. Un `@projet` inconnu → erreur `require_project`, rien n'est créé |
| `meute task list [--all] [--project NAME \| --floating] [--status KIND] [--json]` | une `task_line` par tâche, ordre `sort_for_display` ; `--status` par `parse_status_kind` (aucune validation propre à la CLI) ; `--project` et `--floating` ensemble → erreur d'usage (code 2) ; `--json` : tableau de `task_to_json` |
| `meute task show <ID> [--json]` | `task_detail` ; `--json` : `task_to_json` plus la clé `notes` (liste de `note_to_json`) |
| `meute project add <NAME> [--description D]` | `Project created: <name>` |
| `meute project list [--json]` | un nom par ligne ; `--json` : tableau de `project_to_json` |

- JSON : `json.dumps(…, ensure_ascii=False, separators=(",", ":"))`.
- **`task_line`** (spécification § 9.5) : `#12 » ! Title @project · tail`. Dans l'ordre : `task_label`, symbole, marqueur de priorité s'il n'est pas vide, titre, `@project` s'il existe, puis ` · ` et **un** des éléments suivants : `blocked: <reason>` ; `in review` ; l'échéance (`format_due`), suivie de ` (overdue)` si `is_overdue`. Rien si aucun ne s'applique. `preview_line` : la même ligne sans identifiant, avec le symbole de `Todo` et sans `(overdue)`.
- **`task_detail`**, horodatages `YYYY-MM-DD HH:MM` dans le fuseau de `now` :

```
#1 Tidy the desk
Status: to do
Priority: normal
Due: —
Project: —
Version: 1
Created: 2026-10-14 10:30
Updated: 2026-10-14 10:30
Notes:
[2026-10-14 10:30] user: First item done.
[2026-10-14 10:30] claude: Review still to do.
```

  `Status:` ajoute ` (<reason>)` pour une tâche bloquée ; `Completed: …` suit `Updated:` si la tâche est terminée ; `Description: …` suit si elle n'est pas vide ; `Notes:` n'apparaît que s'il y a des notes.
- **Erreurs**, dans `run` : message sur stderr préfixé par `meute: `. Codes : 0 succès ; 1 `MeuteError` (hors cas suivants), `OSError`, `sqlite3.Error` ; 2 usage (Click) ; 3 `VersionConflict`, suivi sur une seconde ligne de la `task_line` de `err.current` ; 4 `NotFound`. Les exceptions du cœur traversent `app()` : on les attrape autour de l'appel, sans `except Exception`.

**`seed_mixed`** (une tâche par statut et priorité, avec et sans projet `meute`, échéances variées ; créées par `USER`, puis statuts posés par `update_task` en version 1) :

| # | Titre | Priorité | Échéance | Projet | Statut |
|---|---|---|---|---|---|
| 1 | Tidy the desk | normal | — | — | todo |
| 2 | Write the guide | high | 2026-10-15 | meute | in_progress |
| 3 | Deploy | urgent | 2026-10-14 | meute | blocked « waiting for CI » |
| 4 | Review the PR | normal | 2026-10-12 | — | review |
| 5 | Close the ticket | low | — | meute | done |
| 6 | Prepare the demo | normal | 2026-10-21 | meute | todo |
| 7 | Call Marie | high | 2026-10-14T13:00Z | — | todo |
| 8 | Pay the invoice | normal | 2026-10-10 | — | todo |

- [ ] **Étape 1 : écrire les tests qui doivent échouer.**

```python
# tests/test_cli_tasks.py
def test_add_then_list_shows_spec_line(sandbox: Sandbox) -> None:
    assert sandbox.run("project", "add", "meute").returncode == 0
    added = sandbox.run("task", "add", "Review", "the", "PR", "@meute", "!", ">tomorrow")
    assert (added.returncode, added.stdout) == (0, "Created: #1 · ! Review the PR @meute · tomorrow\n")
    assert sandbox.run("task", "list").stdout == "#1 · ! Review the PR @meute · tomorrow\n"

def test_unknown_project_creates_nothing(sandbox: Sandbox) -> None:
    sandbox.run("project", "add", "meute")
    result = sandbox.run("task", "add", "x", "@meuet")
    assert result.returncode == 1
    assert result.stderr == "meute: unknown project: meuet (projects: meute)\n"
    assert sandbox.run("task", "list", "--all", "--json").stdout == "[]\n"

def test_unknown_project_without_any_project(sandbox: Sandbox) -> None:
    # "task add x @nope" → stderr "meute: unknown project: nope (no projects)\n"

def test_dry_run_creates_nothing(sandbox: Sandbox) -> None:
    result = sandbox.run("task", "add", "--dry-run", "Pay", "!!", ">fri-2:30pm")
    assert result.stdout == "Parsed: · !! Pay · Fri Oct 16 2:30pm\n"
    assert sandbox.run("task", "list", "--json").stdout == "[]\n"

def test_show_missing_task_exits_4(sandbox: Sandbox) -> None:
    result = sandbox.run("task", "show", "42")
    assert (result.returncode, result.stderr) == (4, "meute: task not found: #42\n")

def test_first_run_writes_default_config(sandbox: Sandbox) -> None:
    sandbox.run("task", "list")
    assert (sandbox.root / "config/meute/config.toml").read_text(encoding="utf-8") == DEFAULT_CONFIG

def test_list_status_done_includes_done_tasks(sandbox: Sandbox) -> None:
    with sandbox.db() as db:
        seed_mixed(db)
    assert sandbox.run("task", "list", "--status", "done").stdout == "#5 ✓ Close the ticket @meute\n"
    assert "Close the ticket" not in sandbox.run("task", "list").stdout

def test_list_unknown_status_exits_1(sandbox: Sandbox) -> None:
    # "--status", "nope" → code 1, stderr "meute: unknown status: nope\n"

def test_list_filters_by_project_and_floating(sandbox: Sandbox) -> None:
    # seed_mixed ; "--project meute --all" contient "Deploy" et pas "Tidy the desk" ;
    # "--floating" contient "Tidy the desk" et pas "Deploy" ;
    # "--project nope" → code 1, "unknown project: nope (projects: meute)" ; les deux options → code 2

def test_list_and_show_json(sandbox: Sandbox) -> None:
    # seed_mixed ; load_json(list --all --json) : 8 objets ; celui d'id 2 a
    # due == {"kind": "date", "value": "2026-10-15"} et project == {"id": 1, "name": "meute"} ;
    # show 3 --json : status "blocked", blocked_reason "waiting for CI", notes == []

def test_invalid_meute_now_names_the_variable(sandbox: Sandbox) -> None:
    result = sandbox.run("task", "list", env={"MEUTE_NOW": "not a date"})
    assert result.returncode == 1 and result.stderr.startswith("meute: invalid MEUTE_NOW: ")

def test_snapshot_task_list_mixed(sandbox: Sandbox, snapshot: SnapshotAssertion) -> None:
    # seed_mixed ; snapshot == sandbox.run("task", "list", "--all").stdout

def test_snapshot_task_show_with_notes(sandbox: Sandbox, snapshot: SnapshotAssertion) -> None:
    # seed_mixed ; notes sur #1 : "First item done." par USER, "Review still to do." par
    # Actor(CLAUDE, MCP, "s1") ; snapshot == sandbox.run("task", "show", "1").stdout
```

  Instantanés attendus, à comparer ligne par ligne avant d'accepter (`uv run pytest --snapshot-update` une seule fois, puis relecture du diff de `.ambr`) : pour `task show 1`, le bloc `task_detail` ci-dessus ; pour `task list --all` :

```
#8 · Pay the invoice · Sat Oct 10 (overdue)
#4 ◎ Review the PR · in review
#7 · ! Call Marie · today 3pm
#3 ✕ !! Deploy @meute · blocked: waiting for CI
#2 » ! Write the guide @meute · tomorrow
#6 · Prepare the demo @meute · Wed Oct 21
#1 · Tidy the desk
#5 ✓ Close the ticket @meute
```

```python
# tests/test_cli_projects.py
def test_project_add_and_list(sandbox: Sandbox) -> None:
    assert sandbox.run("project", "add", "zeta").stdout == "Project created: zeta\n"
    sandbox.run("project", "add", "alpha", "--description", "d")
    assert sandbox.run("project", "list").stdout == "alpha\nzeta\n"
    assert '"name":"alpha"' in sandbox.run("project", "list", "--json").stdout

def test_duplicate_project_exits_1(sandbox: Sandbox) -> None:
    # "Meute" puis "meute" → code 1, stderr "meute: project already exists: meute\n"
```

```python
# tests/test_cli_errors.py
def test_os_error_is_printed_exactly_once(sandbox: Sandbox) -> None:
    blocker = sandbox.root / "not-a-dir"
    blocker.write_text("", encoding="utf-8")
    result = sandbox.run("task", "list", env={"XDG_DATA_HOME": str(blocker)})
    assert result.returncode == 1
    assert result.stderr.startswith("meute: ") and result.stderr.count("Not a directory") == 1
    assert "Traceback" not in result.stderr
```

- [ ] **Étape 2 : constater l'échec.** `uv add --dev syrupy`, puis `uv run pytest tests/test_cli_tasks.py tests/test_cli_projects.py tests/test_cli_errors.py` → échec : `No such command 'task'` (code 2).
- [ ] **Étape 3 : implémenter** `context.py`, `render.py`, `task_app.py`, `task_commands.py`, `project_commands.py` et `run`. Options Typer avec `Annotated[…, typer.Option(help=…)]`, aides en anglais. `test_entry.py` et `test_importtime.py` restent verts : `ingest` n'importe toujours pas la CLI.
- [ ] **Étape 4 : constater le succès**, instantanés relus et acceptés.
- [ ] **Étape 5 : `bash scripts/verify.sh`, `/simplify`, `/security-review`.**
- [ ] **Étape 6 : commiter.** `git commit -m "feat(cli): add, list and show tasks, manage projects"`

---

### Task 9 : CLI — modification, statut, notes, suppression et configuration [sécurité]

**Fichiers :**
- Créer : `src/meute/cli/task_edit_commands.py`, `src/meute/cli/config_commands.py`, `src/meute/cli/config_edit.py`
- Modifier : `src/meute/cli/__init__.py`, `pyproject.toml` et `uv.lock` (via `uv add tomlkit`)
- Test : `tests/test_cli_task_edit.py`, `tests/test_cli_config.py`, `tests/test_config_edit.py`, instantané `tests/__snapshots__/test_cli_task_edit.ambr`

**Remplace :** `crates/meute/tests/cli_task_edit.rs`, `crates/meute/tests/cli_config.rs`, l'instantané `cli_task_edit__snapshot_conflict_message.snap`, et les tests de `config_set` de `crates/meute-core/src/config/tests.rs` et `crates/meute-core/tests/config_io_mutants.rs`.

**Interfaces :**
- Consomme : `update_task`, `delete_task`, `add_note` (Task 6), `parse_due`, `parse_priority`, `parse_status_kind`, `status_from_kind` (Tasks 2–3), `config_key`, `validate_config`, `write_atomic`, `ensure_config`, `config_get` (Task 1), `open_context`, `require_project`, `render.task_line`, `task_app` (Task 8).
- Produit : `config_edit.config_set(path: Path, key: str, value: str) -> None`, et les commandes ci-dessous.

| Commande | Effet et sortie |
|---|---|
| `meute task edit <ID> [--title T] [--description D] [--priority P] [--due TOKEN\|none] [--project NAME\|none] [--expected-version V]` | `TaskPatch` : `--due` par `parse_due` (`None` → `InvalidInput("invalid due date: <token>")`), `none` efface ; `--priority` par `parse_priority`. Affiche la `task_line` après modification |
| `meute task status <ID> <KIND> [--reason R] [--expected-version V]` | `status_from_kind(parse_status_kind(KIND), R)` : aucune validation propre à la CLI. Affiche la `task_line` |
| `meute task note <ID> <text…>` | `Note added to #N` |
| `meute task rm <ID> [--yes] [--expected-version V]` | Sans `--yes` sur un terminal (`sys.stdin.isatty()`) : `Delete #N “Title”? [y/N] ` (`y` ou `yes` confirme, sinon `InvalidInput("deletion cancelled")`). Sans `--yes` hors terminal : `InvalidInput("confirmation required: rerun with --yes")`. Puis `Deleted: #N` |
| `meute config path` | le chemin du fichier, sans ouvrir ni la base ni la configuration (fonctionne sur un fichier invalide) |
| `meute config get <KEY>` / `meute config set <KEY> <VALUE>` | `ensure_config`, puis `config_get` / `config_set` ; `set` n'affiche rien |

- Sans `--expected-version`, la version relue juste avant l'écriture est utilisée.
- **`config_set`** : `config_key(key)` d'abord ; document `tomlkit` du fichier (absent → vide ; erreur d'analyse → `ConfigError(path, message)` avec `line N`) ; la valeur est `tomlkit.value(value)` si c'est une valeur TOML valide **seule**, une chaîne sinon ; la section est créée si besoin, le commentaire de fin de ligne de l'ancienne valeur est conservé ; le document entier est revalidé par `validate_config` (`InvalidInput`, fichier intact) ; écriture par `write_atomic`.

- [ ] **Étape 1 : écrire les tests qui doivent échouer.** `with_task(sandbox)` : `task add Review the PR` (#1, version 1).

```python
# tests/test_cli_task_edit.py
def test_status_blocked_requires_reason_then_shows_it(sandbox: Sandbox) -> None:
    with_task(sandbox)
    refused = sandbox.run("task", "status", "1", "blocked")
    assert (refused.returncode, refused.stderr) == (1, "meute: a blocked task needs a non-empty reason\n")
    done = sandbox.run("task", "status", "1", "blocked", "--reason", "waiting for review")
    assert done.stdout == "#1 ✕ Review the PR · blocked: waiting for review\n"

def test_status_unknown_kind_exits_1(sandbox: Sandbox) -> None:
    # "status 1 finished" → code 1, "meute: unknown status: finished\n"

def test_stale_expected_version_exits_3_with_current_state(sandbox: Sandbox, snapshot: SnapshotAssertion) -> None:
    with_task(sandbox)
    sandbox.run("task", "edit", "1", "--title", "A")
    result = sandbox.run("task", "edit", "1", "--title", "B", "--expected-version", "1")
    assert result.returncode == 3
    assert result.stderr == snapshot   # "meute: modified in the meantime (current version: 2)\n#1 · A\n"

def test_rm_without_yes_off_tty_refuses(sandbox: Sandbox) -> None:
    with_task(sandbox)
    refused = sandbox.run("task", "rm", "1")
    assert (refused.returncode, refused.stderr) == (1, "meute: confirmation required: rerun with --yes\n")
    assert sandbox.run("task", "show", "1").returncode == 0
    assert sandbox.run("task", "rm", "1", "--yes").stdout == "Deleted: #1\n"
    assert sandbox.run("task", "show", "1").returncode == 4

def test_note_then_show_lists_it_with_author(sandbox: Sandbox) -> None:
    with_task(sandbox)
    assert sandbox.run("task", "note", "1", "Started").stdout == "Note added to #1\n"
    assert "] user: Started\n" in sandbox.run("task", "show", "1").stdout

def test_edit_due_invalid_token_is_rejected(sandbox: Sandbox) -> None:
    # "--due soon" → code 1, "meute: invalid due date: soon\n" ; "--priority top" → "unknown priority: top"

def test_edit_sets_and_clears_due_and_project(sandbox: Sandbox) -> None:
    with_task(sandbox)
    sandbox.run("project", "add", "meute")
    set_ = sandbox.run("task", "edit", "1", "--project", "meute", "--due", "tomorrow", "--priority", "high")
    assert set_.stdout == "#1 · ! Review the PR @meute · tomorrow\n"
    assert sandbox.run("task", "edit", "1", "--project", "none", "--due", "none").stdout == "#1 · ! Review the PR\n"
    # "--project nope" → code 1, "unknown project: nope (projects: meute)"
```

```python
# tests/test_cli_config.py
def test_set_then_get_round_trips(sandbox: Sandbox) -> None:
    assert sandbox.run("config", "set", "ui.board_width", "72").returncode == 0
    assert sandbox.run("config", "get", "ui.board_width").stdout == "72\n"

def test_set_unknown_key_exits_1(sandbox: Sandbox) -> None:
    # "config set ui.nope 1" → code 1, "meute: unknown key: ui.nope\n"

def test_path_ends_with_config_toml_even_when_invalid(sandbox: Sandbox) -> None:
    # fichier "[ui]\nboard_width = = 3\n" ; "config path" → code 0, stdout finit par "meute/config.toml\n"

def test_set_on_invalid_config_reports_path_and_line_and_keeps_file(sandbox: Sandbox) -> None:
    # même fichier ; "config set ui.board_width 72" → code 1, stderr contient "config.toml" et "line 2" ;
    # fichier intact
```

```python
# tests/test_config_edit.py
def test_set_preserves_comments_and_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("# keep me\n[ui]\nboard_width = 60 # width\n[perso]\nx = 1\n", encoding="utf-8")
    config_set(path, "ui.board_width", "72")
    text = path.read_text(encoding="utf-8")
    assert "# keep me" in text and "board_width = 72 # width" in text and "[perso]" in text
    assert config_get(path, "ui.board_width") == "72"

@pytest.mark.parametrize(("key", "value"), [
    ("ui.nope", "1"), ("ui.board_width", "large"), ("ui.board_width", "true"),
    ("claude.permission_mode", "yolo"), ("ui.board_width", "60\n[evil]\nx = 1"),
])
def test_set_rejects_bad_keys_and_values_and_keeps_file(tmp_path: Path, key: str, value: str) -> None:
    # ensure_config ; config_set lève InvalidInput ; fichier identique à DEFAULT_CONFIG

def test_set_on_absent_file_creates_it(tmp_path: Path) -> None:
    # config_set(tmp_path / "absent.toml", "ui.board_width", "80") ; config_get → "80"

def test_set_accepts_strings_and_lists(tmp_path: Path) -> None:
    # "claude.permission_mode" "plan" → get "plan" ; "repos.roots" '["~/a", "~/b"]' → get '["~/a", "~/b"]'
```

- [ ] **Étape 2 : constater l'échec.** `uv add tomlkit`, puis `uv run pytest tests/test_cli_task_edit.py tests/test_cli_config.py tests/test_config_edit.py` → `No such command 'edit'` et `ModuleNotFoundError: No module named 'meute.cli.config_edit'`.
- [ ] **Étape 3 : implémenter** les trois modules et les enregistrer dans `cli/__init__.py`. Lire la documentation `tomlkit` de la version installée pour `tomlkit.value` et la conservation des commentaires.
- [ ] **Étape 4 : constater le succès**, instantané du conflit relu et accepté.
- [ ] **Étape 5 : `bash scripts/verify.sh`, `/simplify`, `/security-review`.**
- [ ] **Étape 6 : commiter.** `git commit -m "feat(cli): edit, status, notes, deletion and configuration"`

---

### Task 10 : mutations, revue de la branche, puis PR

**Fichiers :**
- Modifier : les tests concernés par les mutations survivantes ; `pyproject.toml` et `uv.lock` (via `uv add --dev mutmut`, section `[tool.mutmut]`) ; `docs/dev/developpement-assiste-par-ia.md` § 4 et `CLAUDE.md` (outils désormais installés : `hypothesis`, `syrupy`, `mutmut`)
- Créer : `docs/dev/mutants/2026-plan-1-python.md`

**Interfaces :**
- Consomme : tout le code des Tasks 1 à 9.
- Produit : le rapport de mutation et la PR du plan 1 Python.

- [ ] **Étape 1 : configurer `mutmut`** d'après la documentation de la version installée : mutation de `src/meute/core/` uniquement. Les tests de la CLI passent par un sous-processus et ne voient pas les mutants : la couverture des mutations repose sur les tests en processus du cœur, c'est voulu. Noter dans le rapport la configuration retenue (en particulier vis-à-vis de `-n auto`). `/mutants/` est déjà ignoré par Git.
- [ ] **Étape 2 : lancer `mutmut run`**, puis `mutmut results`. Noter le décompte (tués, survivants, délais, suspects).
- [ ] **Étape 3 : traiter chaque survivant en TDD.** Un test qui l'aurait tué ; preuve qu'il **échoue** sur le code muté (`mutmut apply <id>` le temps de la vérification, ou mutation à la main), puis passe sur le code réel. Une mutation équivalente (aucun comportement observable ne change) est justifiée en une phrase dans le rapport. Attendu : aucun survivant sans test ni justification dans `quick_add.py`, `due_parse.py`, `views.py`, `config.py`, `db/`.
- [ ] **Étape 4 : écrire le rapport** `docs/dev/mutants/2026-plan-1-python.md` : commande, décompte avant et après, tests ajoutés (fichier, test, mutation tuée), justifications. Mettre à jour la phrase « Seuls `pytest` et `pytest-xdist` sont installés » du guide § 4 et la ligne § 4 de `CLAUDE.md`.
- [ ] **Étape 5 : `/simplify` puis `/security-review`** sur toute la branche (`git diff main...HEAD`) ; corriger en TDD ce qui est relevé.
- [ ] **Étape 6 : vérification complète** : `bash scripts/verify.sh` et `HYPOTHESIS_PROFILE=ci uv run pytest`, sorties citées.
- [ ] **Étape 7 : commiter, pousser et ouvrir la PR.**

```bash
git commit -m "test: strengthen tests after mutmut"
git push -u origin feat/plan-1-python
gh pr create --base main --assignee gaetinux --title "Plan 1 (Python): foundation and tasks" \
  --body "<summary of the 10 tasks, lint exceptions with their reasons, mutation report, then the line 🤖 Generated with [Claude Code](https://claude.com/claude-code), without any session link>"
```

---

## Auto-relecture

- **Couverture de la spécification** : § 4.2–4.3 (paquet, `core` stdlib, `__init__` sans import, CLI Typer) → Contraintes globales, Tasks 1–9 ; § 9.1 → Task 2 ; § 9.2 → Task 6 ; § 9.3 → Task 3, aperçu au Task 8 ; § 9.5 (symboles, lignes, groupes) → Tasks 7–8 ; § 13 (chemins, configuration, `config get/set`, migrations, sauvegarde, tables du plan) → Tasks 1, 4, 9 ; § 16 (exceptions typées, codes de sortie) → Tasks 1, 4–6, 8 ; § 17 (hypothesis, syrupy, migrations depuis une base vide puis de la version précédente, `verify.sh`) → Tasks 3, 4, 8, 10. Hors périmètre, comme dans le plan Rust : `meute doctor` (plan 6), purge des métriques et tables de sessions (plans 2–3), vue Tâches du TUI (plan 4).
- **Reports intégrés** : `StatusKind` (Task 2) utilisé par `TaskFilter` (Task 5) ; `done` implique les terminées dans le cœur (Task 5) ; `{kind, value}` de `Due` (Task 2) ; validation de statut par le cœur seul (Tasks 8–9) ; utilitaires communs dans `tests/conftest.py` (fixtures) et `tests/support.py` (fonctions).
- **Cohérence des types** : `TaskId`, `ProjectId`, `Due`, `TaskPatch`/`KEEP`, `TaskFilter`/`ProjectFilter`, `Database`, `CliContext`, `task_line` ont le même nom et la même signature dans les blocs Interfaces et les tests.
