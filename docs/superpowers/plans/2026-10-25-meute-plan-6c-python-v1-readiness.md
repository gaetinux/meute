# meute — Plan 6c Python : préparation de la V1 — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Objectif :** un nouvel utilisateur lance `meute doctor`, voit ce qui manque et quoi faire, puis `meute` : ses nouvelles sessions se rangent sous des projets créés pour lui, `session_events` ne grossit plus sans limite, et le README suffit. Le paquet passe en `1.0.0`.

**Architecture :** comme aux plans précédents :
- ce qui se décide est dans `meute.core`, pur et sur la stdlib seule : le choix du projet d'un lancement, les niveaux et le rendu de `doctor`, l'analyse des versions, la lecture du schéma en lecture seule ;
- `meute.cli` assemble : le projet au lancement (`launch_bash`, `launch_claude`), les relevés de `doctor` et sa commande, la purge protégée au démarrage du tableau ;
- ni migration, ni changement du TUI.

**Stack technique :** l'existant (Python 3.13, uv, Typer, `syrupy`, `hypothesis`, `mutmut`). Aucune nouvelle dépendance.

**Spécification :**
- conception de ce plan : `docs/superpowers/specs/2026-10-25-meute-v1-readiness-design.md` ;
- spécification générale : `docs/superpowers/specs/2026-10-15-meute-design.md`, § 9.5, § 10 et § 13 ;
- guide : `docs/dev/developpement-assiste-par-ia.md`.

**Prérequis :** le plan 6b est mergé (PR #15). La branche `feat/plan-6c-python` a été créée sur `main` à jour (f6f32e4) et porte la conception (384f47c).

## Décisions de conception (à relire)

1. **Le projet demandé vient de la tâche.** `ClaudeLaunch` n'a pas de `project_id` : pour `L` ou une tâche choisie dans `N`, le projet demandé est celui de `get_task(ctx.db, task_id)`. D'où la signature `launch_project(ctx, *, repo_id, task_id)` au lieu de `(ctx, repo_id, project_id)` dans la conception.
2. **Le dépôt est celui que l'appelant passe** (`request.repo_id`) : les appelants le résolvent déjà, worktrees liés compris (`repo_id_of_folder`, plan 6a). `launch_project` ne relit pas le dossier.
3. **Les noms de la purge ne changent pas.** La conception renommait `purge_samples` et `SAMPLE_RETENTION` ; trois tests existants les importent ou les remplacent (`tests/test_board_purge.py`, `tests/test_db_claude_sessions.py`). On garde donc `purge_samples`, `purge_old_samples` et `SAMPLE_RETENTION`, et seule leur docstring change. Aucune exception de test n'est nécessaire.
4. **`doctor` a son propre exécuteur** (`subprocess.run`, `timeout=5`, sans shell, `stdin=DEVNULL`), au lieu de `tmux.client._exec` et `Tmux.run`, qui n'ont pas de délai. L'exécuteur prend le `PATH` de l'environnement reçu, pour que les tests y placent leurs faux outils.
5. **Les singuliers et pluriels sont fixés :** `1 problem found` / `2 problems found`, `running, 1 session` / `running, 4 sessions`. La conception écrivait `<n> problem(s) found`.
6. **Un `fail` de tmux** (absent ou trop vieux) saute la ligne `server` ; un `claude` absent saute la ligne `options`. Les autres vérifications tournent toujours.

## Contraintes globales

**Hérité des plans 1 à 6b (inchangé)**
- **Frontières d'imports** (import-linter) : `meute.core`, `meute.tmux` et `meute.git` n'utilisent que la stdlib et ne s'importent pas entre eux. `meute.tui` n'importe ni `meute.tmux` ni `meute.git`. Seul `meute.cli` assemble.
- **Code :** dataclasses gelées, `match` exhaustif terminé par `assert_never` ; pas d'`Any`, de `cast` ni d'`assert` hors des tests ; docstrings sur tout le public de `meute.core` ; fichiers de moins de 300 lignes (`cli/board_backend.py` en fait 298 : n'y ajouter aucune ligne de code) ; exceptions de lint précises, suivies de ` — raison`.
- **Textes :** interface en anglais, textes de la conception et de ce plan copiés mot pour mot ; toute donnée affichée passe par `printable` ou `shown_path` (`meute.core.paths`).
- **Tests :** tmux uniquement sur des serveurs jetables (`tmux_server`, `sandbox`) ; le faux `claude` (`tests/fake_claude/claude`) ou des faux écrits dans `tmp_path`, jamais le vrai ; ni le serveur `meute`, ni le serveur tmux `default`, **même en lecture seule** ; jamais de modification de `~/.claude/settings.json` ni de `~/.claude.json` ; git seulement sur des dépôts jetables de `tmp_path`.

**Propre au plan 6c**
- **Valeurs :** tmux 3.2 au minimum, 3.3 pour `M-t` ; git 2.36 ; claude 2.1.301 ; délai de 5 s par commande extérieure ; rétention de 30 jours (`SAMPLE_RETENTION`).
- **Options de claude vérifiées**, dans cet ordre : `--settings`, `--mcp-config`, `--session-id`, `--resume`, `--permission-mode`, `--append-system-prompt`. `--append-system-prompt` ne doit pas être trouvée dans `--append-system-prompt-file` : comparer des mots entiers.
- **Ordre et noms des lignes de `doctor` :** `tmux`, `git`, `claude`, `options`, `config`, `database`, `state`, `server`, puis la `note`. Le niveau est sur 6 colonnes (`ok`, `warn`, `fail`, `note`), le nom sur 10.
- **Textes exacts de `doctor`** (`<v>` : la version lue, première ligne, `printable`, sans le préfixe `tmux ` ni `git version `) :
  - tmux : `ok` → `<v>` ; `warn` → `<v>: M-t needs tmux 3.3 or later` ; `fail` → `not found: meute needs tmux 3.2 or later`, `<v>: meute needs tmux 3.2 or later`, `unreadable version: <sortie>` ;
  - git : `ok` → `<v>` ; `fail` → `not found: worktrees and the Git line need git 2.36 or later`, `<v>: worktrees and the Git line need git 2.36 or later`, `unreadable version: <sortie>` ;
  - claude : `ok` → `<v>` ; `warn` → `<v>: meute is tested with claude 2.1.301 or later`, `unreadable version: <sortie>` ; `fail` → `not found: Claude sessions are disabled` ;
  - options : `ok` → `claude --help lists every option meute uses` ; `fail` → `claude --help does not list: <option>, <option>` ;
  - délai dépassé (toute commande) : `fail` → `<outil> did not answer within 5 s`, où `<outil>` est `tmux`, `git` ou `claude` ;
  - config : `ok` → `<chemin>` ou `<chemin> (absent: defaults are used)` ; `fail` → le texte de la `ConfigError` ;
  - database : `ok` → `<chemin> (schema <n>)` ; `warn` → `<chemin> (schema <n>): migrated at the next start`, `<chemin>: created at the first start` ; `fail` → `<chemin> (schema <n>): newer than this meute (<m>)`, `<chemin>: <erreur>` ;
  - state : `ok` → `<chemin>` ; `fail` → `<chemin>: not writable` ;
  - server : `ok` → `tmux server <socket>: running, <n> sessions` ou `tmux server <socket>: not running (meute starts it)` ;
  - note : `--append-system-prompt-file (used above 8000 bytes of context) is not in claude --help and cannot be checked` ;
  - fin : `<n> problem found` / `<n> problems found` quand il y a des `warn` ou des `fail`, rien sinon.
- **Code de sortie de `doctor` :** 1 s'il y a au moins un `fail`, 0 sinon.

**Qualité et workflow**
- **TDD strict.** Ne jamais modifier, supprimer ni désactiver un test existant. La seule exception demandée par ce plan prolonge la numérotation du plan 6b. **Elle est à autoriser par l'auteur à la relecture du plan**, et elle est signalée dans le commit et dans la PR :
  - **n° 32** (Task 1), seulement si un tel test existe : un test ou un instantané existant qui lance une session dans un dépôt connu sans projet, et qui fige l'absence de projet (`project_id` vide, liste de projets vide, `project` absent d'une sortie JSON), voit seulement cette attente passer au projet créé. Rien d'autre ne change.
- **Instantanés :** relus ligne par ligne, jamais de `--snapshot-update` à l'aveugle. Avec xdist, la mise à jour se fait avec `-n0`.
- **Fin de tâche :** `uv run ruff clean` puis `bash scripts/verify.sh`, et un commit.
- **Commits :** en anglais, terminés par `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`, sans ligne `Claude-Session`.
- **PR :** une seule, à la fin, **titre et corps en anglais**, assignée à `gaetinux`.

## Hors périmètre

- Création d'un projet à l'adoption d'un orphelin, pour une session extérieure, ou par `r` ; rattrapage des sessions déjà en base.
- `doctor --fix`, `doctor --json` ; rétention réglable ; plafond d'événements par session ; `VACUUM`.
- Tag et release (l'auteur, après le merge).

## Points de vigilance (Review Focus)

1. **Une tâche d'un projet lancée dans le dépôt d'un autre projet** (`L` sur une tâche de « api » dont le dépôt choisi est « web »). La session va dans « api », et aucun projet « web » n'est créé. Test au Task 1.
2. **Deux dépôts du même nom dans deux racines**, ou un dépôt nommé ` Web ` à côté d'un projet `web`. Aucun doublon de projet : le projet existant est repris (casse et espaces ignorés). Test au Task 1.
3. **Une base verrouillée par un autre processus au démarrage du tableau.** Le tableau démarre quand même, et la purge est retentée au démarrage suivant. Test au Task 2.
4. **Un outil qui ne répond pas** (un faux `claude --help` qui dort 10 s), ou qui écrit des octets non UTF-8 ou une séquence d'échappement. `doctor` finit en un peu plus de 5 s par outil muet, avec une ligne `fail` lisible ; il n'affiche jamais la séquence d'échappement. Tests au Task 3 (analyse, `hypothesis`) et au Task 4 (délai, sortie).
5. **`doctor` sur une machine neuve** (aucun dossier XDG, aucune base). Il ne crée rien : ni configuration, ni base, ni dossier d'état, ni fichier `-wal`. Les lignes disent `absent: defaults are used` et `created at the first start`, et le code de sortie ne dépend que des outils. Test au Task 4.

---

### Task 1 : projets créés au lancement

**Fichiers :**
- Modifier :
  - `src/meute/core/session_project.py` : `launch_project_id` ;
  - `src/meute/cli/session_launch.py` : `launch_bash` remplit `project_id` ;
  - `src/meute/cli/session_launch_claude.py` : `launch_claude` passe `project_id` à `ClaudeOrigin` et à `NewSession`.
- Créer : `src/meute/cli/launch_project.py`
- Tests : `tests/test_launch_project_choice.py` (cœur), `tests/test_launch_project.py` (CLI, avec le sandbox et le faux `claude`)

**Interfaces :**
- Consomme : `project_of`, `repo_project_links(db)`, `list_projects(db)`, `list_repos(db)`, `create_repo_project(db, name)`, `get_task(db, task_id)`.
- Produit :
  - `launch_project_id(requested: ProjectId | None, repo: Repo | None, *, links: Mapping[RepoId, ProjectId], projects: Sequence[NamedProject]) -> ProjectId | None` dans `meute.core.session_project` : les étapes 1 à 3 de la conception (le projet demandé s'il existe ; le projet lié au dépôt ; le projet au nom du dépôt, `strip().casefold()`). `None` veut dire « rien trouvé ».
  - `launch_project(ctx: CliContext, *, repo_id: RepoId | None, task_id: TaskId | None) -> ProjectId | None` dans `cli/launch_project.py` : le projet demandé est celui de la tâche ; si `launch_project_id` ne trouve rien et que le dépôt est connu, l'étape 4 renvoie `create_repo_project(ctx.db, repo.name.strip()).id` ; sinon `None`.

- [ ] **Étape 1 : écrire les tests du cœur, qui doivent échouer.** Le projet demandé gagne sur le lien et sur le nom ; un projet demandé qui n'existe plus est ignoré ; le lien gagne sur le nom (dépôt `web` lié au projet `front`, en présence d'un projet `web`) ; `" Web "` trouve le projet `web` ; un dépôt inconnu et rien de demandé donnent `None`.
- [ ] **Étape 2 : écrire les tests de la CLI, qui doivent échouer** (une base de fichier, des dépôts jetables enregistrés par `sync_repos`, le faux `claude`, le serveur du sandbox) :
  - `launch_bash` puis `launch_claude` dans un dépôt `alpha` sans projet : un projet `alpha` existe, lié à `alpha`, et les deux sessions ont son `project_id` ; il n'y a qu'un seul projet `alpha` ;
  - **point de vigilance 1 :** `launch_claude` avec la tâche d'un projet `api` dans le dépôt `web` : `project_id` vaut celui d'`api`, et `project_by_name(db, "web")` est `None` ;
  - **point de vigilance 2 :** deux dépôts `web` (deux racines) et un projet `Web` existant : aucun projet créé, la session a le projet `Web` ;
  - un `repo_id` à `None` (dossier hors dépôt) : aucun projet créé, `project_id` à `None` ;
  - le contexte composé d'une session Claude lit les consignes du projet trouvé (projet `alpha` avec des consignes posées par `set_project_instructions`, lien seulement) ;
  - un échec de tmux (serveur arrêté ou `spawn_window` remplacé pour lever `TmuxError`) : le projet reste, aucune session n'est enregistrée ;
  - `resume_session` et l'adoption d'un orphelin ne créent aucun projet.
- [ ] **Étape 3 : vérifier l'échec, puis lancer toute la suite.** Un test existant qui fige l'absence de projet relève de l'exception n° 32 : n'adapter que cette attente, et lister le test dans le commit. Tout autre échec est un défaut.
- [ ] **Étape 4 : implémenter.** `launch_project` est appelée avant `prepare_claude` (Claude) et avant `spawn_and_record` (Bash), après `resolve_folder` : un dossier introuvable ne crée pas de projet.
- [ ] **Étape 5 : vérification complète, puis commit** `git commit -m "feat: a new session in a repository without a project creates it"`

---

### Task 2 : purge de `session_events`

**Fichiers :**
- Modifier :
  - `src/meute/core/db/claude_sessions.py` : `purge_samples` supprime aussi `session_events`, dans la même transaction ;
  - `src/meute/cli/board_backend.py` : la docstring de `purge_old_samples` seulement (`Delete the metric and quota samples and the session events older than 30 days; return how many (§ 13).`) ;
  - `src/meute/cli/__init__.py` : dans `board`, `purge_old_samples(ctx)` est entouré de `contextlib.suppress(sqlite3.Error, MeuteError)`, avec le commentaire `# a locked database must not keep the dashboard from starting: retried at the next start`.
- Test : `tests/test_purge_events.py`

**Interfaces :**
- Produit : `purge_samples(db, *, older_than) -> int`, qui renvoie le total des trois tables.

- [ ] **Étape 1 : écrire les tests, qui doivent échouer.**
  - Un événement de 31 jours est supprimé, un de 29 jours est gardé, et un événement exactement à la limite est gardé (comme les relevés).
  - Le total renvoyé compte les relevés de métriques, de quotas et les événements.
  - La session elle-même reste.
  - **Point de vigilance 3 :** `meute board`, avec `purge_samples` remplacé par une fonction qui lève `sqlite3.OperationalError("database is locked")`, suit quand même `scan`, `run`, `close` et sort avec 0 (même montage que `tests/test_board_purge.py`, dans le nouveau fichier). Même chose avec une `MeuteError`.
- [ ] **Étape 2 : vérifier l'échec.**
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète, puis commit** `git commit -m "feat: the start-up purge drops session events older than 30 days"`

---

### Task 3 : `doctor`, le cœur

**Fichiers :**
- Créer : `src/meute/core/doctor.py`
- Modifier : `src/meute/core/db/schema.py` : `read_schema_version`
- Tests : `tests/test_doctor_core.py`, `tests/test_db_schema_readonly.py`

**Interfaces :**
- Produit, dans `meute.core.doctor` :
  - `class CheckLevel(StrEnum)` : `OK = "ok"`, `WARN = "warn"`, `FAIL = "fail"`, `NOTE = "note"` ;
  - `@dataclass(frozen=True, slots=True, kw_only=True) class Check` : `level: CheckLevel`, `name: str`, `text: str` ;
  - `parse_version(output: str) -> tuple[int, ...] | None` : le premier `\d+(\.\d+)+` de la première ligne, en entiers (`"tmux 3.5a"` → `(3, 5)`, `"tmux next-3.6"` → `(3, 6)`, `"git version 2.47.3"` → `(2, 47, 3)`, `"2.1.302 (Claude Code)"` → `(2, 1, 302)`) ; ne lève jamais ;
  - `shown_version(output: str, prefix: str) -> str` : la première ligne, sans `prefix` (`"tmux "`, `"git version "`, `""`), passée par `printable` et coupée à 40 caractères ;
  - `tmux_check(output: str | None) -> Check`, `git_check(output: str | None) -> Check`, `claude_check(output: str | None) -> Check` : `None` veut dire « introuvable » ; textes et seuils des contraintes globales ;
  - `options_check(help_text: str) -> Check` : comparaison par mots entiers (`re.findall(r"--[a-z][a-z-]*", help_text)`) ;
  - `timeout_check(name: str) -> Check` ;
  - `database_check(shown: str, version: int | None, latest: int) -> Check` (`None` : base absente) ;
  - `NOTE_CHECK: Check` ;
  - `render_checks(checks: Sequence[Check]) -> str` : une ligne par vérification (niveau sur 6 colonnes, nom sur 10, sans espaces en fin de ligne), puis la ligne de fin ;
  - `exit_code(checks: Sequence[Check]) -> int`.
- Produit, dans `meute.core.db.schema` : `read_schema_version(path: Path) -> int | None` : `None` si le fichier n'existe pas ; sinon `sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)`, `PRAGMA user_version`, puis fermeture. Lève `sqlite3.Error` si le fichier n'est pas une base.
- Produit : `LATEST_SCHEMA: int = len(MIGRATIONS)` dans `meute.core.db.migrations`, si rien de tel n'existe déjà.

- [ ] **Étape 1 : écrire les tests, qui doivent échouer.**
  - **Versions :** les quatre exemples de `parse_version`, plus `""`, `"tmux master"` et `"\x1b[31m"` → `None`. Une propriété `hypothesis` (`st.text()`) : `parse_version` et `shown_version` ne lèvent jamais, et `shown_version` ne rend aucun caractère de contrôle (**point de vigilance 4**).
  - **Seuils :** tmux 3.1 → `fail`, 3.2 → `warn`, 3.3 → `ok`, `3.10` → `ok` (comparaison de tuples, pas de chaînes) ; git 2.35.9 → `fail`, 2.36 → `ok` ; claude 2.1.300 → `warn`, 2.1.301 → `ok` ; `None` pour chacun → le texte `not found: …` et son niveau ; une version illisible → `fail` pour tmux et git, `warn` pour claude.
  - **Options :** une aide qui ne contient que `--append-system-prompt-file` → `fail` qui nomme `--append-system-prompt` ; une aide sans `--resume` ni `--settings` → `claude --help does not list: --settings, --resume` (ordre des contraintes globales).
  - **Base :** version à jour → `ok` ; plus ancienne → `warn` ; plus récente → `fail` ; `None` → `warn` `created at the first start`.
  - **Rendu :** un instantané `syrupy` d'une liste mêlant les quatre niveaux, avec `2 problems found` ; une liste sans `warn` ni `fail` n'a pas de ligne de fin ; `1 problem found` au singulier. Le code de sortie vaut 1 avec un `fail`, 0 avec seulement des `warn`.
  - **`read_schema_version` :** une base migrée → `len(MIGRATIONS)` ; un fichier absent → `None`, et il n'est pas créé ; un fichier texte → `sqlite3.DatabaseError` ; aucun `-wal` ni `-shm` n'apparaît à côté d'une base en mode `DELETE` ; un chemin qui contient une espace et un `#` fonctionne.
- [ ] **Étape 2 : vérifier l'échec.**
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète, puis commit** `git commit -m "feat(core): doctor checks, version parsing and read-only schema version"`

---

### Task 4 : `meute doctor`

**Fichiers :**
- Créer : `src/meute/cli/doctor.py`
- Modifier : `src/meute/cli/__init__.py` : la commande `doctor`, importée dans la fonction (comme `board`), sans `open_context`.
- Test : `tests/test_cli_doctor.py`, et son instantané.

**Interfaces :**
- Consomme : le Task 3 ; `Paths.from_env`, `load_config`, `ConfigError`, `find_claude`, `shown_path`, `printable`, le socket `environ.get("MEUTE_TMUX_SOCKET") or DEFAULT_SOCKET` (même règle que `meute_tmux`, `cli/tmux_env.py`).
- Produit :
  - `tool_output(argv: Sequence[str], environ: Mapping[str, str]) -> subprocess.CompletedProcess[str] | None | TimedOut` dans `cli/doctor.py` : `None` si le programme est introuvable (`shutil.which(argv[0], path=environ.get("PATH"))`, puis lancé par ce chemin absolu) ; `TimedOut` (une classe gelée vide) si le délai de 5 s est dépassé ; sinon le résultat, décodé en `utf-8` avec `errors="replace"`. Les versions et l'aide se lisent dans `stdout`, quel que soit le code de retour ;
  - `run_doctor(environ: Mapping[str, str], *, home: Path) -> list[Check]` : les vérifications dans l'ordre des contraintes globales ;
  - la commande `meute doctor`, qui affiche `render_checks` et sort avec `exit_code`.

- [ ] **Étape 1 : écrire les tests, qui doivent échouer** (`sandbox.run("doctor", env={"PATH": ...})`, avec un dossier `bin` de `tmp_path` qui contient de faux `tmux`, `git` et `claude` en `sh`, plus des liens vers `sh` et vers le vrai `tmux` quand un cas en a besoin ; le serveur tmux est celui du sandbox) :
  - un instantané de la sortie complète quand tout va bien (faux outils aux bonnes versions, base créée par une première commande `meute task list`, serveur du sandbox démarré) ;
  - pour chaque outil : absent, trop vieux, illisible ; tmux 3.2 donne `warn` et le code 0 ;
  - **point de vigilance 4 :** un faux `claude` dont `--help` dort 10 s → `claude did not answer within 5 s`, et la commande dure moins de 8 s ; un faux `git --version` qui écrit `\x1b[2Jgit version 2.40` et un octet `\xff` ne fait apparaître ni `\x1b` ni d'exception ;
  - `claude` absent : pas de ligne `options` ; tmux absent : pas de ligne `server` ;
  - configuration invalide (`[ui]\nrecent_days = "x"`) → `fail` avec le texte de la `ConfigError` ;
  - base plus ancienne (une base migrée, puis `PRAGMA user_version = 3`) → `warn` ; plus récente (`user_version = 99`) → `fail` ; fichier texte à la place de la base → `fail` ;
  - dossier d'état en `0o500` → `fail` `not writable` (sauté si les tests tournent en root) ;
  - serveur arrêté → `not running (meute starts it)` ; serveur démarré avec deux sessions → `running, 2 sessions` ;
  - **point de vigilance 5 :** dans un sandbox neuf, après `meute doctor`, ni `config/meute`, ni `data/meute`, ni `state/meute` n'existent, et le serveur tmux du sandbox n'est pas démarré ;
  - le code de sortie : 1 avec un `fail`, 0 avec seulement des `warn`.
- [ ] **Étape 2 : vérifier l'échec.**
- [ ] **Étape 3 : implémenter.** Le dossier d'état est `ok` s'il existe et que `os.access(path, os.W_OK | os.X_OK)` est vrai, ou s'il est absent et que son premier parent existant l'est. Le serveur se lit par `tool_output([*Tmux(socket=…).base_args(), "list-sessions", "-F", "#{session_name}"], environ)`, et un code de retour non nul veut dire « arrêté » (`no server running`, `error connecting to` : le texte de tmux n'est pas affiché). La base se lit par `read_schema_version` : `sqlite3.Error` et `OSError` deviennent `fail` avec leur texte.
- [ ] **Étape 4 : vérification complète, puis commit** `git commit -m "feat: meute doctor"`

---

### Task 5 : documentation, version, mutation, essai, relectures et PR

**Fichiers :**
- Modifier :
  - `README.md` : `**Status:** V1.`, et les sections **Requirements**, **Getting started**, **Projects**, **Data**, **Troubleshooting** de la conception ; les sections existantes relues pour la cohérence ;
  - la spécification générale : § 9.5, § 10 et § 13, comme le dit la conception ;
  - la feuille de route : 6c fait, « Reports issus du plan 6c », et une section « Après la V1 » qui reprend ce qui reste ouvert ;
  - la conception : « Écarts constatés à la réalisation », dont les décisions 1, 3 et 5 de ce plan ;
  - `pyproject.toml` : `version = "1.0.0"`, puis `uv lock` (seule la version de `meute` change dans `uv.lock`) ; la sélection de mutmut gagne les tests du cœur de ce plan.
- Créer : `docs/dev/mutants/2026-plan-6c-python.md`

- [ ] **Étape 1 : la documentation et la version.** Vérifier `uv run meute --version` → `meute 1.0.0`.
- [ ] **Étape 2 : la mutation.** Lancer `rm -rf mutants && uv run mutmut run --max-children 4`, puis `uv run mutmut results`. Tuer les survivants utiles dans `tests/test_mutants_plan6c.py`, et justifier les autres.
- [ ] **Étape 3 : l'essai scripté** (serveur tmux jetable, faux `claude`, `HOME` et `XDG_*` épinglés, dépôts jetables). Il enchaîne :
  1. `meute doctor` sur une machine neuve : rien n'est créé ;
  2. `meute` puis `c` dans un dépôt `alpha` : `meute project list` montre `alpha` ;
  3. `L` sur une tâche d'un autre projet : pas de nouveau projet ;
  4. un événement vieilli de 31 jours en SQL, puis un nouveau tableau : il a disparu ;
  5. `meute doctor` avec tout en place : code 0.
- [ ] **Étape 4 : `/simplify`, puis `/security-review`** sur toute la branche. Appliquer les constats, puis faire une vérification complète.
- [ ] **Étape 5 : commit, push, puis la PR**, en anglais et assignée à `gaetinux`. Elle liste l'exception n° 32 (si elle a servi), les écarts, les limites et les essais manuels de l'auteur (vrai terminal, vrai Claude : `meute doctor` sur sa machine, premier lancement dans un dépôt, regroupement de deux dépôts dans un projet).

---

### Task 6 : `meute project link` et `unlink` (ajoutée le 2026-10-25, décision de l'auteur)

**Fichiers :**
- Modifier : `src/meute/core/db/repos.py` (`move_repo`, `unlink_repo`) ; `src/meute/cli/project_commands.py` (les deux commandes ; si le fichier passe 300 lignes, les mettre dans `src/meute/cli/project_link_commands.py`, enregistrées sur `project_app`) ; `README.md` (section Projects : la limite « aucune commande » disparaît, les deux commandes y figurent) ; la feuille de route et les « Écarts » de la conception si elles citent cette limite.
- Test : `tests/test_cli_project_link.py`

**Interfaces :**
- Produit :
  - `move_repo(db, project_id: ProjectId, repo_id: RepoId) -> None` : dans une transaction, supprime les autres liens du dépôt puis insère celui-ci (sans effet s'il existe déjà seul) ;
  - `unlink_repo(db, project_id, repo_id) -> bool` : vrai si un lien a été supprimé ;
  - `find_repo(repos: Sequence[Repo], wanted: str) -> Repo` dans `meute.core.repo` : chemin si `/` dans `wanted` (comparaison de chemins résolus par l'appelant), sinon nom `strip().casefold()` ; lève `InvalidInput` avec les textes de la conception.
- Textes exacts : section « Rattacher un dépôt à un projet » de la conception.

- [ ] **Étape 1 : écrire les tests, qui doivent échouer.** `link` d'un dépôt `web` (projet automatique `web`) vers `api` : `repo_project_links` donne `api`, et un nouveau lancement dans `web` (faux `claude`, serveur du sandbox) a le projet `api` ; refaire `link` répond pareil ; `unlink` puis lancement : retour au projet `web` par le nom ; `unlink` sans lien → erreur et code 1 ; projet inconnu → l'erreur de `require_project` ; dépôt inconnu ; nom ambigu (deux racines) → la liste des chemins, puis `link` par chemin réussit ; un nom de dépôt avec une séquence d'échappement s'affiche par `printable`.
- [ ] **Étape 2 : vérifier l'échec, implémenter, vérification complète, puis commit** `git commit -m "feat: meute project link and unlink"`
