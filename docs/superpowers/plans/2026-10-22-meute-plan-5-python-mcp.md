# meute — Plan 5 Python : MCP et contexte composé — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Objectif :** les sessions Claude lancées par meute disposent du serveur `meute mcp` et de ses 7 outils de tâches. Elles reçoivent aussi le contexte composé du § 8 : consignes globales, consignes du projet et tâche liée. `L`, et `N` avec une tâche, ne collent plus que « Work on task #N. ».

**Architecture :** comme aux plans précédents, ce qui se décide se calcule dans `meute.core`, de façon pure et avec la stdlib seule :
- la lecture des entrées des outils et le JSON des tâches ;
- le contexte composé.

Le reste se répartit ainsi :
- `meute.mcp` construit le serveur `FastMCP` au-dessus d'un protocole `McpBackend` synchrone ;
- `meute.cli` implémente ce protocole et fournit la commande `meute mcp` ;
- `meute.claude` écrit `mcp.json` et les réglages de la session, et construit l'argv.

**Stack technique :**
- l'existant : Python 3.13, uv, Typer, Textual 8.2, `syrupy`, `hypothesis`, `mutmut` ;
- une nouvelle dépendance, **`mcp`** (SDK officiel, `FastMCP`), ajoutée par `uv add mcp`.

**Spécification :**
- conception de ce plan : `docs/superpowers/specs/2026-10-22-meute-mcp-design.md` ;
- spécification générale : `docs/superpowers/specs/2026-10-15-meute-design.md`, § 8, § 9.6 et § 12 ;
- guide : `docs/dev/developpement-assiste-par-ia.md`.

**Prérequis :** le plan 4c est mergé (PR #12). La branche `feat/plan-5-python` existe déjà ; elle a été créée sur `main` à jour et porte la conception (3d2d7da).

## Décisions de conception (à relire)

1. **Options facultatives dans `claude_argv` et `settings_document`.** `claude_argv` gagne `mcp_config: Path | None = None` et `context: ContextArg | None = None`. `settings_document` et `write_settings` gagnent `allowed_tools: Sequence[str] = ()`, et la clé `permissions` n'apparaît que si cette liste n'est pas vide. Les appels existants gardent ainsi leur résultat. Seul le lancement réel passe les nouvelles valeurs.
2. **`--mcp-config <fichier>` vient juste après `--settings <fichier>`** dans l'argv. Le contexte (option ou fichier, selon S11) vient juste avant `--name=`.
3. **Le collage complet disparaît.** `core/task_prompt.py` n'a plus d'appelant, il est supprimé avec son test (exception n° 25). Une tâche se lit désormais par `task_read`.
4. **Les entrées des outils sont lues dans le cœur, sans toucher la CLI.** `core/mcp_data.py` lit le statut, la priorité, l'échéance et le filtre d'échéance. La CLI ne change pas : ses messages d'erreur sont fixés par des tests. Elle pourra réutiliser ces lectures plus tard.
5. **Un `McpBackend` par processus.** `meute mcp` construit un `CliMcpBackend` qui garde les chemins, la configuration et la session appelante. Il ouvre une connexion SQLite par appel d'outil, sans état gardé entre deux appels.
6. **Les outils `FastMCP` sont des fonctions synchrones.** `FastMCP` accepte des outils synchrones. Il n'y a ni `await` ni fil d'exécution à gérer dans `meute.mcp`, au-delà du `run()` du SDK.

## Contraintes globales

**Hérité des plans 1 à 4c (inchangé)**
- **Frontières d'imports** (import-linter) : `meute.core`, `meute.tmux` et `meute.git` n'utilisent que la stdlib. `meute.mcp` n'importe que `meute.core` et `mcp`. Seul `meute.cli` assemble les morceaux. Seul `meute.mcp` importe `mcp`.
- **Code :**
  - dataclasses gelées, `match` exhaustif terminé par `assert_never` ;
  - pas d'`Any`, de `cast` ni d'`assert` hors des tests ;
  - docstrings sur tout le public de `meute.core` ;
  - fichiers de moins de 300 lignes ;
  - exceptions de lint précises, suivies de ` — raison`.
- **Textes :**
  - interface en anglais, textes de ce plan et de la conception copiés mot pour mot ;
  - toute donnée affichée par la CLI passe par `printable` ;
  - tout argument passé à tmux passe par `Tmux.run`.
- **Tests :**
  - tmux uniquement sur des serveurs jetables (`tmux_server`, `sandbox`) ;
  - aucun test automatique n'appelle le vrai `claude` ;
  - ni le serveur `meute`, ni le serveur tmux `default` de l'utilisateur, **même en lecture seule** ;
  - jamais de modification de `~/.claude/settings.json` ni de `~/.claude.json`.

**Propre au plan 5**
- **Sortie standard de `meute mcp` :** elle ne porte que le protocole, sans aucun `print`, avertissement ni message de migration. Les erreurs inattendues vont dans `<state_dir>/mcp.log`.
- **Textes exacts :**
  - « The repository's `CLAUDE.md` files are authoritative on code conventions. The task is authoritative on the goal. If they contradict each other, point it out to the user instead of choosing. » ;
  - « You are working on task #N. Read it with the `task_read` tool and report your progress with `task_note_add`. » ;
  - « Work on task #N. » ;
  - `Global instructions:` et `Project instructions (<nom>):` ;
  - `meute database unavailable: <raison>` et `internal error`.
- **Outils autorisés :** `mcp__meute__task_list`, `mcp__meute__task_read`, `mcp__meute__task_create`, `mcp__meute__task_update`, `mcp__meute__task_set_status`, `mcp__meute__task_note_add` et `mcp__meute__task_link_session`, dans cet ordre (`MEUTE_TOOLS`).

**Qualité et workflow**
- **TDD strict.** Ne jamais modifier, supprimer ni désactiver un test existant. Les seules exceptions autorisées par ce plan prolongent la numérotation du plan 4c. Chacune est relue et signalée dans le commit et dans la PR :
  - **n° 24** (Task 7) : `tests/test_task_launch.py::test_the_text_is_pasted_without_being_sent` et `tests/test_task_launch_form.py::test_the_form_folder_title_and_mode_are_kept_and_the_text_pasted`. Le texte collé attendu devient `work_on_task_text(task.id)` au lieu de `task_prompt(…)`, et l'import suit. Rien d'autre ne change.
  - **n° 25** (Task 7) : suppression de `tests/test_task_prompt.py`, avec `src/meute/core/task_prompt.py`, qui n'a plus d'appelant.
  - **n° 26** (Task 6) : `tests/test_cli_session_claude.py`, le test qui fixe l'argv exact (lignes 52-60). L'argv attendu gagne `"--mcp-config", str(<dossier de la session>/"mcp.json")` juste après `--settings`. Rien d'autre ne change.
- **Instantanés :** relus ligne par ligne, jamais de `--snapshot-update` à l'aveugle.
- **Fin de tâche :** chaque tâche se termine par `bash scripts/verify.sh` et un commit. Le plan se termine par `/simplify` puis `/security-review`.
- **Commits :** en anglais, terminés par `Co-Authored-By: Claude …`, sans ligne `Claude-Session`.
- **PR :** une seule, à la fin, **titre et corps en anglais**, assignée à `gaetinux`.

## Hors périmètre

- **Pas exposé en MCP :** les outils de suppression, d'arrêt de session ou de projets, et les confirmations en attente.
- **Sessions hors meute :** pas de serveur MCP pour les sessions Claude lancées hors de meute.
- **Plan 6 :** les worktrees, les états sauvegardés, `meute doctor`, les projets créés automatiquement et la vue Sessions sans base.

## Points de vigilance (Review Focus)

1. **Une écriture parasite sur la sortie standard de `meute mcp`** : un avertissement Python, la sauvegarde ou la migration de la base au premier appel, ou un log du SDK. Claude doit garder la session MCP. Test de bout en bout au Task 5, lancé avec `PYTHONWARNINGS=default` sur une base à migrer.
2. **Des entrées d'outil hostiles ou fausses** : `id` négatif ou inexistant, `status` inconnu, `blocked` sans raison, `reason` sans `blocked`, `due` sans fuseau, `expected_version` périmée, `body` vide ou fait d'espaces. Chaque cas donne une erreur d'outil lisible, et rien n'est écrit. Tests au Task 2 (cœur) et au Task 4 (serveur).
3. **`MEUTE_SESSION` faux** : en majuscules, `x;y`, vide ou absent. Aucune session n'est écrite dans l'historique, et `task_link_session` répond une erreur. Test au Task 5.
4. **La base est verrouillée ou absente pendant un appel** : l'outil répond `meute database unavailable: …`, et l'appel suivant marche. Test au Task 5.
5. **Des consignes longues ou étranges** : 20 000 caractères, des sauts de ligne, `;` en fin, `--x` en début. Elles arrivent intactes à Claude, en un seul mot d'argv ou dans le fichier, selon S11. Test au Task 6.

---

### Task 1 : spike S11 (MCP et contexte avec le vrai Claude)

**Fichiers :**
- Créer : `docs/superpowers/spikes/2026-10-22-spike-s11.md`

**S11 demande l'accord explicite de l'auteur avant de lancer le vrai `claude`.**
- **Environnement :**
  - un serveur tmux jetable (`-L meute-spike-s11`) ;
  - le `HOME` réel, pour l'authentification ;
  - un dossier jetable dans le scratchpad ;
  - un petit serveur `FastMCP` jetable dans le scratchpad (`uv run --with mcp`). Il expose un outil `echo_env`, qui renvoie `MEUTE_SESSION`, et un outil `task_read` factice.
- **Lancement :** `claude --settings <réglages avec permissions.allow pour les deux outils> --mcp-config <mcp.json> --session-id <uuid> --permission-mode manual --name=s11 --append-system-prompt "<texte>"`.
- **À relever :**
  1. Les outils sont-ils listés (`/mcp`) ?
  2. L'appel d'outil passe-t-il sans demande d'autorisation ?
  3. `MEUTE_SESSION` arrive-t-il dans l'environnement du serveur ?
  4. Les réglages de l'utilisateur restent-ils actifs ?
  5. Le texte d'`--append-system-prompt` est-il suivi ? On le vérifie avec une consigne observable, par exemple « reply with the word PINEAPPLE first ».
  6. Existe-t-il une variante fichier (`claude --help`) ?
  7. Quelle taille l'argument supporte-t-il (20 000 caractères) ?
  8. Combien de temps prend le démarrage à froid du serveur, et Claude l'attend-il ?
- **Fin :** tuer le serveur jetable.

- [ ] **Étape 1 : demander l'accord, puis lancer S11 s'il est donné.** Sinon, noter « S11 reporté » : le plan suit alors la documentation de Claude Code, avec l'option `--append-system-prompt` en argument et `permissions.allow`.
- [ ] **Étape 2 : écrire le compte rendu** (commandes, sorties anonymisées, réponses aux questions 1 à 8) et fixer dans une section « Décision » :
  - la forme du contexte : le type `ContextArg`, soit `--append-system-prompt <texte>`, soit l'option fichier qui l'emporte ;
  - la forme de `mcp.json`.
- [ ] **Étape 3 : commit** `git commit -m "docs: spike S11 (MCP config and system prompt under meute)"`

---

### Task 2 : entrées des outils et JSON des tâches (cœur)

**Fichiers :**
- Créer : `src/meute/core/mcp_data.py`
- Test : `tests/test_mcp_data.py`

**Interfaces :**
- `DueFilter` : `Enum` (`OVERDUE = "overdue"`, `TODAY = "today"`, `WEEK = "week"`).
- **Lectures**, qui lèvent toutes `InvalidInput` avec le texte entre parenthèses :
  - `parse_status(text: str, reason: str | None) -> TaskStatus`. Les noms valides sont `todo`, `in_progress`, `blocked`, `review` et `done`. Les erreurs : `unknown status: <texte>`, `blocked needs a reason` (raison absente ou faite d'espaces) et `a reason only goes with blocked`.
  - `parse_priority(text: str) -> Priority` (`unknown priority: <texte>`).
  - `parse_due(text: str) -> Due`. `YYYY-MM-DD` donne `DueDate`, et un instant ISO avec fuseau donne `DueAt`. Erreur : `due must be a date (YYYY-MM-DD) or an instant with a time zone: <texte>`.
  - `parse_due_filter(text: str) -> DueFilter` (`unknown due filter: <texte>`).
- `due_matches(due: Due | None, due_filter: DueFilter, now: datetime) -> bool` :
  - `overdue` : avant maintenant (une `DueDate` est en retard à partir du lendemain, en heure locale de `now`) ;
  - `today` : la date locale est celle de `now` ;
  - `week` : dans les 7 jours à venir, sans les tâches en retard.
- **JSON :**
  - `task_summary_json(task: Task) -> JsonObject` : `{id, title, status, priority, due, project}` ;
  - `task_json(task: Task, notes: Sequence[Note]) -> JsonObject` : tous les champs de la conception. `due` passe par `due_text`. Les dates sont en ISO UTC. `blocked_reason` vaut `null` hors `blocked`. `notes` est une liste de `{id, body, author, channel, session_id, created_at}`.

- [ ] **Étape 1 : écrire les tests, qui doivent échouer.**
  - Chaque lecture, sur une valeur valide et sur une valeur invalide, avec son texte d'erreur exact.
  - **Point de vigilance 2 :** `blocked` sans raison, raison faite d'espaces, raison sans `blocked`, `due` sans fuseau.
  - `due_matches`, aux bords : minuit local, un jour de changement d'heure, `DueAt` dans 7 jours moins une seconde.
  - Les JSON, avec un instantané `syrupy`.
  - Une propriété `hypothesis` : `parse_due(due_text(d)) == d` pour toute `Due`.
- [ ] **Étape 2 : vérifier l'échec.**
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète, puis commit** `git commit -m "feat(core): MCP tool inputs and task JSON"`

---

### Task 3 : contexte composé et consignes

**Fichiers :**
- Créer : `src/meute/core/context.py`
- Modifier :
  - `src/meute/core/config_validate.py` (`ClaudeConfig.instructions: str = ""`, validée comme chaîne) ;
  - `src/meute/core/config.py` (`DEFAULT_CONFIG` : sous `[claude]`, `# Instructions added to every Claude session launched by meute.` puis `instructions = ""`) ;
  - `src/meute/core/db/projects.py` (`set_project_instructions`) ;
  - `src/meute/core/db/sessions.py` (`link_session_task`) ;
  - `src/meute/cli/project_commands.py` (`edit`, `show`).
- Test : `tests/test_context.py`, `tests/test_project_instructions.py`, `tests/test_db_link_session.py`, `tests/test_config_instructions.py`

**Interfaces :**
- `CONTRADICTION_RULE: str` et `task_line(task_id: TaskId) -> str` : les textes exacts.
- `work_on_task_text(task_id: TaskId) -> str` : `Work on task #N.`.
- `compose_context(*, global_instructions: str, project: Project | None, task_id: TaskId | None) -> str | None` :
  - renvoie `None` si les consignes globales et celles du projet sont vides (après `strip`) et qu'il n'y a pas de tâche ;
  - sinon, les blocs de la conception, dans l'ordre, séparés par une ligne vide ;
  - les consignes sont gardées telles quelles, seuls les espaces de début et de fin sont retirés ;
  - un bloc vide est omis.
- `set_project_instructions(db: Database, project_id: ProjectId, instructions: str) -> Project` (`NotFound` si le projet n'existe pas).
- `link_session_task(db: Database, session_id: SessionId, task_id: TaskId) -> Session` (`NotFound` pour la session ou la tâche).
- La CLI :
  - `meute project edit <nom> (--instructions TEXTE | --instructions-file FICHIER)` : exactement une des deux options, sinon l'erreur `give --instructions or --instructions-file` ; le fichier est lu en UTF-8 ;
  - `meute project show <nom>` affiche `name`, `description`, `instructions` (passées par `printable`, sauts de ligne gardés) et `repos`, ou les donne en JSON avec `--json`.

- [ ] **Étape 1 : écrire les tests, qui doivent échouer.**
  - Instantanés `syrupy` de `compose_context` : aucun niveau, chaque niveau seul, les trois ensemble.
  - Des consignes faites d'espaces seulement sont omises.
  - `set_project_instructions` et `link_session_task`, y compris leurs `NotFound`.
  - `meute config set claude.instructions "x"` puis `config get`.
  - `project edit` avec chaque option, avec les deux options, sans option, avec un fichier absent ; `project show` en texte et en JSON.
  - `DEFAULT_CONFIG` contient la clé et reste une configuration valide.
- [ ] **Étape 2 : vérifier l'échec.**
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète, puis commit** `git commit -m "feat: composed context, global and project instructions"`

---

### Task 4 : serveur MCP (`meute.mcp`) **[sécurité]**

**Fichiers :**
- Créer : `src/meute/mcp/backend.py`, `src/meute/mcp/server.py`
- Modifier :
  - `pyproject.toml` et `uv.lock` (`uv add mcp`) ;
  - `scripts/` : la vérification des licences, si une licence nouvelle et permissive doit être ajoutée ;
  - `docs/dev/developpement-assiste-par-ia.md` § 7.
- Test : `tests/test_mcp_server.py`, et l'instantané de la liste des outils.

**Interfaces :**
- `McpBackend` est un `Protocol`, avec une méthode par outil, chacune acceptant des types simples :
  - `task_list(project: str | None, status: str | None, due: str | None, include_done: bool) -> JsonValue` ;
  - `task_read(task_id: int) -> JsonObject` ;
  - `task_create(title: str, description: str | None, priority: str | None, due: str | None, project: str | None) -> JsonObject` ;
  - `task_update(task_id: int, expected_version: int, changes: TaskChanges) -> JsonObject`, où `TaskChanges` est une dataclass gelée de champs `str | None | Keep` ;
  - `task_set_status(task_id: int, status: str, reason: str | None, expected_version: int) -> JsonObject` ;
  - `task_note_add(task_id: int, body: str) -> JsonObject` ;
  - `task_link_session(task_id: int) -> JsonObject`.
- `build_server(backend: McpBackend) -> FastMCP` : un serveur nommé `meute`, avec les 7 outils. Chaque outil :
  - porte une docstring d'une ligne en anglais, qui devient sa description ;
  - a des paramètres nommés comme dans la conception (`id`, `expected_version`, etc.) ;
  - transforme `MeuteError` en erreur d'outil, avec son message ;
  - pour toute autre exception, appelle `on_unexpected(exc)` (un journal injecté), puis répond `internal error`.
- `run_stdio(server: FastMCP) -> None` : `server.run("stdio")`.

- [ ] **Étape 1 : écrire les tests, qui doivent échouer.** Ils passent par le client en mémoire du SDK (`create_connected_server_and_client_session`) et un faux backend.
  - Instantané de `tools/list` : noms, descriptions et schémas.
  - Chaque outil appelle la bonne méthode avec les bons arguments.
  - Une `MeuteError` donne `isError` avec son message exact.
  - Un `VersionConflict` donne un message qui contient la version actuelle.
  - Une `RuntimeError` donne `internal error`, et le journal reçoit l'exception.
  - **Point de vigilance 2 :** un `id` qui n'est pas un entier est refusé par le schéma, sans appeler le backend.
- [ ] **Étape 2 : vérifier l'échec.**
- [ ] **Étape 3 : `uv add mcp`, puis implémenter.**
  - Vérifier que les contrats d'imports passent.
  - Si basedpyright signale des types inconnus venus du SDK, ajouter des exceptions précises avec leur raison. Le mode strict n'est jamais abaissé.
- [ ] **Étape 4 : vérification complète (licences et pip-audit compris), puis commit** `git commit -m "feat(mcp): task tools server over an McpBackend"`

---

### Task 5 : backend CLI et commande `meute mcp` **[sécurité]**

**Fichiers :**
- Créer : `src/meute/cli/mcp_backend.py`, `src/meute/cli/mcp_command.py`
- Modifier : `src/meute/cli/__init__.py` (la commande `mcp`, avec l'aide `MCP server for Claude sessions (stdio).`)
- Test : `tests/test_mcp_backend.py`, `tests/test_mcp_stdio.py`

**Interfaces :**
- `CliMcpBackend(paths: Paths, config: Config, caller: SessionId | None, clock: Callable[[], datetime])` implémente `McpBackend` :
  - chaque méthode ouvre `open_database(paths, clock)` ;
  - l'acteur est `Actor(author=CLAUDE, channel=MCP, session_id=caller)` ;
  - les entrées passent par `core/mcp_data.py` ;
  - `task_create` sans `project` prend `session_project` de la session appelante ;
  - un nom de projet inconnu donne `unknown project: <nom>` ;
  - une `sqlite3.Error` ou un `OSError` d'ouverture donne `MeuteError("meute database unavailable: <raison>")`.
- `caller_session(environ: Mapping[str, str]) -> SessionId | None` : `MEUTE_SESSION`, retenue seulement si `parse_session_id` l'accepte sous sa forme exacte.
- `meute mcp` :
  - construit le backend ;
  - passe à `build_server` un journal qui écrit dans `<state_dir>/mcp.log`, avec la même rotation que `ingest.log` (réutiliser ou extraire sa fonction) ;
  - appelle `run_stdio`.
  - Rien n'est écrit sur la sortie standard avant ce `run_stdio`. La base n'est ni ouverte ni migrée avant le premier appel d'outil.

- [ ] **Étape 1 : écrire les tests, qui doivent échouer.**
  - **Backend, sur une base jetable :**
    - chaque outil ;
    - l'historique `claude`/`mcp` avec la session ;
    - **point de vigilance 3** : `MEUTE_SESSION` en majuscules, `x;y`, vide ou absent, qui donne aucune session dans l'historique et une erreur pour `task_link_session` ;
    - le projet par défaut de `task_create`, et un projet inconnu ;
    - **point de vigilance 4** : avec une base verrouillée (`BEGIN EXCLUSIVE` sur une autre connexion, `busy_timeout` court), l'outil répond `meute database unavailable: …`, puis l'appel suivant passe une fois le verrou levé ;
    - une `expected_version` périmée, qui ne change rien.
  - **De bout en bout (`test_mcp_stdio.py`) :**
    - `meute mcp` en sous-processus, piloté par le client stdio du SDK, sur une base à créer et à migrer ;
    - les variables `PYTHONWARNINGS=default` et `XDG_*` jetables ;
    - les appels `initialize`, `tools/list` et `task_read` d'une tâche créée avant ;
    - **point de vigilance 1** : le client ne voit aucune ligne hors protocole, et la sortie d'erreur du processus est relue.
- [ ] **Étape 2 : vérifier l'échec.**
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète, puis commit** `git commit -m "feat: meute mcp serves the task tools"`

---

### Task 6 : brancher les sessions Claude **[sécurité]**

**Fichiers :**
- Créer : `src/meute/claude/mcp_config.py`
- Modifier :
  - `src/meute/claude/settings.py` (`allowed_tools`, `MEUTE_TOOLS`) ;
  - `src/meute/claude/launch.py` (`claude_argv` : `mcp_config`, `context`) ;
  - `src/meute/cli/session_launch_claude.py` ;
  - `src/meute/cli/session_resume.py` ;
  - `tests/fake_claude/claude` : il accepte `--mcp-config <fichier>` et l'option de contexte, et les enregistre déjà dans `MEUTE_FAKE_CLAUDE_ARGS`.
- Test : `tests/test_claude_mcp_config.py`, `tests/test_launch_context.py` ; exception n° 26

**Interfaces :**
- `mcp_config_document(meute_command: Sequence[str], session_id: SessionId) -> JsonObject` : `{"mcpServers": {"meute": {"type": "stdio", "command": meute_command[0], "args": [*meute_command[1:], "mcp"], "env": {"MEUTE_SESSION": session_id}}}}`, dans la forme confirmée ou corrigée par S11.
- `write_mcp_config(state_dir: Path, session_id: SessionId, meute_command: Sequence[str]) -> Path` : écrit `<state_dir>/sessions/<id>/mcp.json`, avec les mêmes droits que `write_settings` (dossiers 0700, fichier 0600, écriture atomique).
- `MEUTE_TOOLS: tuple[str, ...]` : les 7 noms des contraintes globales.
- `settings_document(meute_command, allowed_tools: Sequence[str] = ())` : si `allowed_tools` n'est pas vide, ajoute `"permissions": {"allow": [...]}`.
- `ContextArg` : selon S11, soit le texte (`--append-system-prompt <texte>`), soit un fichier 0600 (`<dossier de la session>/context.md`) passé par l'option fichier.
- `claude_argv(..., mcp_config: Path | None = None, context: ContextArg | None = None)` : la décision 2 fixe l'ordre des options.
- `session_context(ctx: CliContext, session: Session) -> str | None` : `compose_context` avec `ctx.config.claude.instructions`, le projet (`session_project`) et `session.task_id`.
- **Lancement et reprise :**
  - `launch_claude` et `resume_session` écrivent `mcp.json` et `settings.json` (avec `MEUTE_TOOLS`), puis passent `--mcp-config` ;
  - ils passent aussi le contexte quand il n'est pas `None` ;
  - la reprise recalcule le contexte avec les données du moment.

- [ ] **Étape 1 : écrire les tests, qui doivent échouer.**
  - Le document et les droits de `mcp.json`.
  - `settings_document` avec et sans outils ; les tests existants restent intacts.
  - L'argv exact avec `mcp_config` et `context`.
  - **Faux `claude` :**
    - `c` dans un projet qui a des consignes : l'argv porte `--mcp-config` et le contexte, et `mcp.json` désigne la session ;
    - sans consignes ni tâche : pas d'option de contexte ;
    - la reprise reprend le contexte, et celui-ci a changé si les consignes ont changé entre-temps.
  - **Point de vigilance 5 :** des consignes de 20 000 caractères, avec sauts de ligne, `;` final et `--x` en tête, arrivent intactes (un mot d'argv ou le contenu du fichier).
  - Appliquer l'exception n° 26 et la relire.
- [ ] **Étape 2 : vérifier l'échec.**
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète, puis commit** `git commit -m "feat: Claude sessions get the meute MCP server and the composed context"`

---

### Task 7 : `L` et `N` collent « Work on task #N. »

**Fichiers :**
- Modifier : `src/meute/cli/task_launch.py`
- Supprimer : `src/meute/core/task_prompt.py`, `tests/test_task_prompt.py` (exception n° 25)
- Test : exception n° 24, et `tests/test_task_launch_work_on.py`

**Interfaces :**
- `_launch_and_paste` colle `work_on_task_text(task_id)`. Il garde le reste à l'identique : le fichier privé, le tampon tmux, l'attente de 10 s et `PromptNotPasted`.
- La session lancée est liée à la tâche, comme avant. Son contexte porte donc la ligne de la tâche, grâce au Task 6.

- [ ] **Étape 1 : écrire les tests, qui doivent échouer.**
  - Avec le faux `claude` (mode `paste`) : `L` colle exactement `Work on task #3.` sans saut de ligne final ni envoi.
  - L'argv contient le contexte avec `You are working on task #3.`.
  - Appliquer les exceptions n° 24 et 25, et les relire.
- [ ] **Étape 2 : vérifier l'échec.**
- [ ] **Étape 3 : implémenter.** Retirer les imports devenus inutiles.
- [ ] **Étape 4 : vérification complète, puis commit** `git commit -m "feat: L and N paste Work on task #N. instead of the task text"`

---

### Task 8 : documentation, mutation, relectures et PR

**Fichiers :**
- Modifier :
  - `docs/superpowers/specs/2026-10-15-meute-design.md` : § 8, § 9.6, § 12, la ligne S11 du § 14, et les lignes « Restent à vérifier » désormais tranchées ;
  - `docs/superpowers/specs/2026-10-22-meute-mcp-design.md` : les écarts relevés ;
  - `docs/superpowers/plans/2026-10-15-meute-v1-roadmap.md` : 5 fait, et une section « Reports issus du plan 5 » ;
  - `README.md` : `meute mcp`, les consignes, `project edit` et `project show`.
- Créer : `docs/dev/mutants/2026-plan-5-python.md`

- [ ] **Étape 1 : mutation.**
  - Ajouter les nouveaux tests du cœur à la sélection mutmut de `pyproject.toml`.
  - Lancer `uv run mutmut run --max-children 4`, puis `uv run mutmut results`.
  - Tuer les survivants utiles dans `tests/test_mutants_plan5.py`, et justifier les autres dans le rapport.
- [ ] **Étape 2 : `/simplify` sur la branche** (src et tests, sans les instantanés ni les docs).
- [ ] **Étape 3 : `/security-review`** sur l'argv de Claude, `mcp.json`, `MEUTE_SESSION`, les entrées des outils, la base sous verrou et la sortie standard. Corriger en TDD.
- [ ] **Étape 4 : essai scripté**, sur un serveur jetable et avec le faux `claude` :
  - `c` dans un projet avec consignes : l'argv et `mcp.json` sont corrects ;
  - `L` : « Work on task #N. » est collé ;
  - `meute mcp` piloté à la main par le client stdio : `task_read`, `task_note_add`, puis la note est visible dans l'onglet Tâches.

  Le tableau des résultats va dans le rapport de mutation. La liste des essais manuels pour l'auteur (vrai Claude, vrai terminal) va dans la PR.
- [ ] **Étape 5 : vérification complète, puis commit** `git commit -m "docs: plan 5 mutation report, spec and roadmap"`. Pousser la branche, puis ouvrir la PR `feat: MCP task tools and composed context (plan 5)`, assignée à `gaetinux`, **titre et corps en anglais**. Elle liste les exceptions n° 24 à 26 et les essais manuels.
