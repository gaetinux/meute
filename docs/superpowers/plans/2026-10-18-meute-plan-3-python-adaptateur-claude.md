# meute — Plan 3 Python : adaptateur Claude — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Objectif :** meute lance des sessions Claude Code dans `meute-bg`, reçoit leurs hooks et leur statusline par `meute ingest`, en déduit les états du § 6.1, affiche la statusline (portage du script de l'auteur), et voit les sessions Claude lancées hors de meute grâce à `claude agents --json`.

**Architecture :** l'interprétation des hooks et de la statusline, le calcul des états et le rendu de la statusline sont des fonctions pures de `meute.core`, car `meute.ingest` (le chemin chaud, moins de 50 ms) n'a le droit d'importer que `meute.core`. `meute.ingest` lit stdin, ouvre la base sans jamais la migrer, applique l'effet et ne fait jamais échouer Claude. `meute.claude` construit la ligne de commande et le fichier `--settings`, et lit `claude agents --json`. `meute.cli` assemble le lancement et la relecture.

**Stack technique :** existante (Python 3.13, uv, Typer, Textual, `tomlkit`, pytest, `hypothesis`, `syrupy`, `pytest-textual-snapshot`, `mutmut`) ; aucune dépendance nouvelle ; externes : `tmux` ≥ 3.2, `claude` (2.1.302 en local, absent de la CI : un faux `claude` le remplace dans les tests).

**Spécification :** `docs/superpowers/specs/2026-10-15-meute-design.md`, § 4.3, 5.5, 6.1, 6.2, 7.1 à 7.3, 7.4 (couleurs et heures pleines seulement), 13, 16, 17. Spikes : `docs/superpowers/spikes/2026-10-15-spikes-s1-s5.md` (S1 à S3), `docs/superpowers/spikes/2026-10-16-spike-s6-demarrage-python.md`. Guide : `docs/dev/developpement-assiste-par-ia.md`. Feuille de route : `docs/superpowers/plans/2026-10-15-meute-v1-roadmap.md` (reports des plans 1 et 2).

**Référence de la statusline :** `https://github.com/gaetinux/claude-statusline`, fichier `statusline-command.sh` (227 lignes, script de l'auteur). La Task 7 en fait un portage fidèle, segment par segment.

**Prérequis :** plans 1 et 2 mergés (PR #7 et #8). Branche : `feat/plan-3-python`, créée depuis `main`.

## Décisions de conception (à relire)

1. **Interprétation dans le cœur, pas dans `meute.claude`.** La spécification (§ 4.3) range « l'interprétation des hooks et de la statusline » dans `meute.claude`, mais `meute.ingest` ne peut importer que `meute.core` (§ 4.3, contrats import-linter). Comme ces règles sont des transitions d'état, elles vont dans `meute.core` (`hooks.py`, `statusline.py`, `statusline_render.py`) ; `meute.claude` garde la ligne de commande, `--settings` et `claude agents --json`.
2. **`--session-id` = l'identifiant interne de meute.** Le `native_id` reçu dans `SessionStart` est donc égal à l'`id` ; il est quand même enregistré, et un hook dont le `session_id` diffère est historisé sans changer l'état.
3. **Pas de `--mcp-config` ni d'`--append-system-prompt` dans ce plan.** `meute mcp` et le contexte composé (§ 8) arrivent au plan 5 ; passer un `mcp.json` vers une commande qui n'existe pas encore afficherait une erreur dans chaque session.
4. **Touche `c` pour lancer Claude dans le tableau de bord**, `n` lance toujours Bash. Le « dernier type utilisé » de `n` reste au plan 4. Le pied de page change (instantanés relus, exception autorisée n° 3).
5. **`claude agents --json` est non bloquant dans le tableau de bord** : il prend environ 400 ms, il est lancé en sous-processus et récolté au relevé suivant, au plus toutes les 10 s. La CLI l'appelle de façon synchrone (`session list`).
6. **L'état supposé** `MaybeStuck` (« stuck? ») vient d'une absence de hook depuis `claude.stuck_after_minutes` (défaut 10) sur une session `Running` ou `SubagentRunning`, sauf si `claude agents --json` donne un statut, qui l'emporte (source officielle observée).

## Contraintes globales

**Hérité des plans 1 et 2 (inchangé)**
- `meute.core`, `meute.tmux`, `meute.git` : stdlib et leur propre package seulement ; `meute.claude` : `meute.core` et stdlib ; `meute.ingest` : `meute.core` et stdlib, **sous-modules nécessaires seulement** ; `meute.tui` : `meute.core` et `textual` ; seul `meute.cli` assemble. `__init__.py` sans import. On importe le sous-module précis.
- Dataclasses `frozen=True, slots=True, kw_only=True` ; variantes en union de dataclasses gelées ; `match` exhaustif terminé par `case _: assert_never(x)` ; identifiants en `NewType` ; pas d'`Any`, de `cast`, d'`assert` hors tests ; docstrings Google sur le public de `meute.core` ; fichiers de moins de 300 lignes.
- Exceptions aux lints : une règle précise et ` — raison`. `subprocess` en liste d'arguments, jamais `shell=True`.
- Interface en anglais ; textes de ce plan copiés mot pour mot.
- Tests tmux sur serveurs jetables `meute-test-<uuid>` toujours tués ; la fixture `sandbox` fixe toujours `MEUTE_TMUX_SOCKET`. **Aucun test automatique n'appelle le vrai `claude`** : la fixture `sandbox` place en tête du `PATH` un dossier contenant le faux `claude` de la Task 10 dès que cette tâche existe ; avant, les tests qui ont besoin de `claude` en fabriquent un minimal dans `tmp_path`.
- Les données venues de Claude (titres, messages, arguments d'outils, noms de modèle, worktrees) passent par `printable` (Task 2) avant tout affichage, y compris dans la statusline et la barre d'état tmux.

**Chemin `ingest`** (spécification § 7.3)
- Moins de 50 ms en temps normal ; `busy_timeout` de 200 ms ; au-delà, l'événement est abandonné et une ligne est ajoutée à `~/.local/state/meute/ingest.log` (format `<instant UTC> <commande> <classe d'erreur>: <message>`, jamais le contenu du JSON reçu ; rotation en `ingest.log.1` au-delà de 1 MiB).
- Code de sortie toujours 0 ; rien sur stdout, sauf la statusline ; `MEUTE_SESSION` absente, invalide ou inconnue : l'événement est ignoré (la statusline s'affiche quand même).
- `ingest` **ne migre jamais** la base : si la version du schéma n'est pas celle du code, l'événement est abandonné et journalisé.
- Le test `importtime` reste la garde ; il est étendu (Task 5) : le chemin `ingest hook` n'importe ni `meute.core.db.migrations`, ni `meute.core.config`, ni `tomllib`.

**Qualité et workflow**
- TDD strict. Ne jamais modifier, supprimer ni désactiver un test existant. **Seules exceptions autorisées par ce plan**, signalées dans le commit et la PR :
  1. Task 3 : la version de schéma attendue passe de `2` à `3` et les tables `session_events`, `metric_samples`, `quota_samples` s'ajoutent à l'ensemble attendu dans `tests/test_db_open.py` (ces tests vérifient le dernier schéma) ;
  2. Task 4 : aucun test existant n'est touché, mais `PaneObservation` gagne un champ facultatif `settled: bool = True` ;
  3. Task 9 : le pied de page du tableau de bord change ; les instantanés SVG de `tests/__snapshots__/test_tui_board/` sont régénérés et **relus** (seule la ligne de pied de page doit changer).
- Instantanés relus ligne par ligne ; jamais `--snapshot-update` à l'aveugle.
- Chaque tâche se termine par `bash scripts/verify.sh`, `/simplify`, et `/security-review` pour les tâches **[sécurité]**. Commits en anglais terminés par `Co-Authored-By: Claude …`, sans ligne `Claude-Session` ni lien de session. Une PR à la fin, assignée à `gaetinux`.

## Hors périmètre (reporté, inscrit dans la feuille de route à la Task 12)

- Vue Sessions complète, « needs attention », `M-n` / `M-N`, compteur de la barre d'état, quotas et projection « limit around HH:MM », formulaire `N`, « dernier type utilisé » (plan 4).
- `meute mcp`, `--mcp-config`, `--append-system-prompt` et le contexte composé du § 8 (plan 5).
- Reprise `--resume`, états sauvegardés, worktrees, `meute doctor` (plan 6).
- Affichage du mode de permission en couleur dans le tableau de bord (plan 4) ; ce plan l'affiche dans `meute session list`.

## Points de vigilance (Review Focus)

1. **Hooks qui arrivent en rafale et en parallèle.** Claude déclenche plusieurs hooks presque en même temps (`PreToolUse`, `PostToolUse`, `Stop`) ; deux processus `ingest` et le tableau de bord écrivent dans la même base. Aucun ne doit échouer en silence ni corrompre l'état : transactions `BEGIN IMMEDIATE`, `busy_timeout` 200 ms, journal en cas d'abandon. Test au Task 5 (`test_parallel_hooks_all_land_or_are_logged`).
2. **JSON inattendu.** Un hook peut arriver avec des champs absents, de types inattendus, ou un événement inconnu (Claude évolue). `interpret_hook` ne lève jamais (propriété `hypothesis`) ; `ingest` sort avec 0. Tests aux Tasks 4 et 5.
3. **Séquences d'échappement dans les données de Claude.** Un message, un argument d'outil ou un nom de worktree contenant `ESC[` ou des caractères bidi falsifierait le terminal de l'utilisateur, dans la statusline comme dans le tableau de bord. `printable` partout. Tests aux Tasks 2 et 7.
4. **Session terminée qui reçoit encore des hooks.** Un `Stop` tardif après `SessionEnd`, ou un hook d'une session déjà `Exited` ou `Unreachable`, ne ressuscite rien (principe 5) : historisé, état inchangé. Test au Task 4.
5. **`claude` absent ou lent.** Sans `claude`, `session new --kind claude` échoue avec un message clair et Bash reste disponible (§ 16) ; un `claude agents --json` qui échoue, rend un JSON illisible ou dépasse son délai n'affecte ni la liste ni le tableau. Tests aux Tasks 9 et 11.

---

### Task 1 : capture des messages réels de Claude (spike S7)

Les messages bruts du spike S2/S3 n'ont pas été conservés. Cette tâche les capture avec le vrai `claude` local et les commite comme fixtures. **C'est la seule tâche qui lance le vrai Claude** (accord de l'auteur ; coût de quelques centimes).

**Fichiers :**
- Créer : `scripts/capture-claude-fixtures.sh` (script de capture, relisible, rejouable par l'auteur)
- Créer : `tests/fixtures/claude/2.1.302/hooks/<Event>-<n>.json`, `tests/fixtures/claude/2.1.302/statusline-<n>.json`, `tests/fixtures/claude/2.1.302/agents.json`, `tests/fixtures/claude/2.1.302/settings.json` (le fichier `--settings` qui a fonctionné)
- Créer : `docs/superpowers/spikes/2026-10-18-spike-s7-capture-claude.md`

**Déroulement imposé :**
- Serveur tmux jetable `-L meute-capture-<uuid>` (tué à la fin), dossier de travail : **le dépôt meute lui-même** (déjà approuvé par l'auteur dans Claude : aucune question de confiance, donc aucune écriture de Claude dans `~/.claude.json` pour un nouveau dossier).
- `claude --settings <fichier de capture> --session-id <uuid> --permission-mode manual --name=meute-capture` ; le fichier de capture déclare un hook `command` pour chacun de `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PermissionRequest`, `PostToolUse`, `PreCompact`, `SubagentStart`, `SubagentStop`, `Stop`, `SessionEnd`, `Notification`, et une `statusLine` ; chaque commande copie stdin dans un fichier horodaté sous le scratchpad, avec `MEUTE_SESSION` ajouté en tête du nom.
- Prompts envoyés par `tmux send-keys` : `Reply with the single word pong.` ; `Run the shell command: echo meute-capture` (une demande de permission : la répondre « Yes » par touches) ; `Use the Task tool with a general-purpose subagent to reply pong.` ; `/compact` ; puis `/exit`.
- Puis `claude agents --json` pendant qu'une session tourne.
- Nettoyage : remplacer `/home/<utilisateur>` par `/home/user`, le chemin du scratchpad par `/tmp/capture`, retirer tout jeton, adresse e-mail ou identifiant de compte s'il en apparaît ; le `transcript_path` devient `/home/user/.claude/projects/x/<id>.jsonl`.
- **Le dépôt ne doit pas changer** hors des fichiers listés : `git status` vérifié avant le commit (aucun fichier créé par Claude).

**Le rapport S7 répond, preuve à l'appui :**
1. La forme exacte du fichier `--settings` acceptée (avec ou sans `matcher` pour chaque hook).
2. Les champs réels de chaque hook, en particulier `SessionStart.model` (chaîne ou objet ?), `SubagentStart`/`SubagentStop.agent_type`, `PreCompact`, `SessionEnd.reason`, `PermissionRequest.tool_input`.
3. Les hooks de l'utilisateur (dans `~/.claude/settings.json`) restent-ils actifs avec `--settings` ? (Lecture seule de ce fichier : ne pas le modifier ; s'il n'a pas de hooks, le noter.)
4. `--name=<titre>` est-il accepté, y compris pour un titre commençant par `-` ?
5. La durée de `claude agents --json` (`hyperfine -N --runs 10`).

- [ ] **Étape 1 : écrire le script de capture et le lancer.**
- [ ] **Étape 2 : nettoyer les fichiers, vérifier par `grep -rn "gaetinux\|@" tests/fixtures/claude` qu'il ne reste rien de personnel.**
- [ ] **Étape 3 : écrire le rapport S7.** Si un fait contredit ce plan (forme des hooks, champs), le rapport le dit et la tâche suivante concernée s'appuie sur le rapport.
- [ ] **Étape 4 : vérification complète, commit.** `git commit -m "test: capture real Claude Code 2.1.302 hook and statusline messages"`

---

### Task 2 : base ouverte en parallèle et texte affichable [sécurité]

Critère d'entrée du plan 3 (report du plan 1) et report « caractères de contrôle ».

**Fichiers :**
- Modifier : `src/meute/core/db/migrations.py`, `src/meute/core/db/connection.py`
- Créer : `src/meute/core/db/schema.py`, `src/meute/core/text.py`
- Modifier (affichage) : `src/meute/cli/render.py`, `src/meute/cli/task_commands.py`, `src/meute/cli/task_edit_commands.py`, `src/meute/cli/session_commands.py`, `src/meute/cli/repo_commands.py`, `src/meute/core/board_view.py`, `src/meute/cli/session_show.py` (valeur de `@meute_status`)
- Test : `tests/test_db_concurrent_open.py`, `tests/test_text.py`, plus des tests d'affichage nouveaux dans les fichiers de tests CLI (fichiers nouveaux : `tests/test_cli_printable.py`)

**Interfaces :**
- Produit :
  - `SCHEMA_VERSION: int` dans `meute/core/db/schema.py` (vaut `len(MIGRATIONS)` ; un test le vérifie) ;
  - `Database.open_existing(path: Path, *, busy_timeout_ms: int, clock: Clock = utc_now) -> Database` : ouvre sans créer ni migrer ; fichier absent → `FileNotFoundError` ; version différente de `SCHEMA_VERSION` → `MigrationError("database schema version <v> does not match this meute (<SCHEMA_VERSION>)")` ; n'importe pas `meute.core.db.migrations` ;
  - `migrate` prend un verrou exclusif `fcntl.flock` sur `<db>.lock` (même dossier, créé en `0o600`) autour de la relecture de version, de la sauvegarde et des migrations, pour une base fichier ; la version est relue **après** l'obtention du verrou ;
  - `printable(text: str, *, keep_newlines: bool = False) -> str` dans `meute/core/text.py` : remplace par `U+FFFD` chaque caractère de catégorie Unicode `Cc` (sauf `\n` quand `keep_newlines`, et `\t` remplacé par une espace) et les contrôles bidi `U+202A`–`U+202E`, `U+2066`–`U+2069` ; le reste est inchangé.
- Où appliquer `printable` : toute donnée venant de la base ou de Claude affichée en texte (titres et descriptions de tâches, notes avec `keep_newlines=True`, historique, titres et dossiers de sessions, noms de dépôts et de projets, lignes du tableau de bord, `@meute_status`). Les sorties `--json` restent brutes (le JSON échappe déjà les contrôles).

- [ ] **Étape 1 : tests qui échouent.**
  - `test_two_processes_migrating_a_v1_file_both_succeed` : base v1 (une tâche), deux sous-processus `python -c "Database.open(...)"` lancés ensemble (barrière par fichier) → codes 0, version finale `SCHEMA_VERSION`, la tâche intacte, exactement un `meute.db.bak-1`.
  - `test_open_existing_refuses_another_version_without_touching_it` (version 1 → `MigrationError`, fichier inchangé octet pour octet) ; `test_open_existing_missing_file` ; `test_schema_version_matches_migrations`.
  - `test_printable` (paramétré) : `"a\x1b[31mb"` → `"a�[31mb"`, `"x‮y"` → `"x�y"`, `"a\tb"` → `"a b"`, `"l1\nl2"` → `"l1�l2"` et, avec `keep_newlines`, inchangé ; `"\x85"` (C1) → `"�"` ; texte accentué et emoji inchangés ; propriété `hypothesis` : le résultat ne contient aucun caractère `Cc` hors `\n` autorisé.
  - `tests/test_cli_printable.py` : une tâche titrée `"ok\x1b]0;pwned\x07"` → `task list` et `task show` n'émettent aucun octet `\x1b` ni `\x07` ; une session titrée avec `\x1b[2J` → `session list` idem ; une note multi-ligne garde ses sauts de ligne.
- [ ] **Étape 2 : constater l'échec. Étape 3 : implémenter.** Ajouter les nouveaux tests en processus à la sélection de mutmut.
- [ ] **Étape 4 : vérification complète ; `/simplify`, `/security-review`, commit.** `git commit -m "fix(core): serialise concurrent migrations and sanitise displayed text"`

---

### Task 3 : schéma Claude (migration 3)

**Fichiers :**
- Créer : `src/meute/core/db/sql/003_claude.sql`, `src/meute/core/claude_session.py`, `src/meute/core/db/claude_sessions.py`
- Modifier : `tests/test_db_open.py` (exception autorisée n° 1)
- Test : `tests/test_db_claude_sessions.py`

**Interfaces :**
- Migration `003_claude.sql`, texte exact :

```sql
ALTER TABLE sessions ADD COLUMN native_id TEXT;
ALTER TABLE sessions ADD COLUMN transcript_path TEXT;
ALTER TABLE sessions ADD COLUMN model TEXT;
ALTER TABLE sessions ADD COLUMN permission_mode TEXT;
ALTER TABLE sessions ADD COLUMN last_tool TEXT;
ALTER TABLE sessions ADD COLUMN pending_permission TEXT;
ALTER TABLE sessions ADD COLUMN last_message TEXT;
CREATE TABLE session_events (
  id INTEGER PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  event TEXT NOT NULL,
  detail TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE INDEX session_events_session ON session_events(session_id, created_at);
CREATE TABLE metric_samples (
  id INTEGER PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  model TEXT, effort TEXT,
  context_pct REAL, cost_usd REAL, duration_ms INTEGER,
  lines_added INTEGER, lines_removed INTEGER,
  worktree_name TEXT, worktree_branch TEXT, worktree_path TEXT,
  repo_host TEXT, repo_owner TEXT, repo_name TEXT
);
CREATE INDEX metric_samples_session ON metric_samples(session_id, created_at);
CREATE TABLE quota_samples (
  id INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  five_hour_pct REAL, five_hour_resets_at TEXT,
  seven_day_pct REAL, seven_day_resets_at TEXT
);
CREATE INDEX quota_samples_created ON quota_samples(created_at);
```

- Produit, dans `claude_session.py` : `ClaudeDetails(native_id: str | None = None, transcript_path: str | None = None, model: str | None = None, permission_mode: str | None = None, last_tool: str | None = None, pending_permission: str | None = None, last_message: str | None = None)` et `claude_details_to_json(details) -> JsonObject` (mêmes clés) ; `SessionEvent(session_id, event: str, detail: str, created_at: datetime)`.
- Produit, dans `db/claude_sessions.py` :
  - `get_claude_details(db, session_id: SessionId) -> ClaudeDetails` (`NotFound("session", id)`) ;
  - `session_events(db, session_id, *, limit: int = 50) -> list[SessionEvent]`, les plus récents en dernier ;
  - `purge_samples(db, *, older_than: datetime) -> int` : supprime les `metric_samples` et `quota_samples` plus anciens, renvoie le nombre de lignes supprimées.
- `SCHEMA_VERSION` passe à `3` (le test de la Task 2 le vérifie contre `len(MIGRATIONS)`).
- `Session` et `session_to_json` ne changent pas (les tests existants les fixent) ; les détails Claude sont lus à part.

- [ ] **Étape 1 : tests qui échouent** : aller-retour des colonnes Claude (écrites en SQL brut, lues par `get_claude_details`) ; `session_events` ordonnés et limités ; suppression d'une session supprime ses événements et relevés (cascade) ; `purge_samples` à la frontière (un relevé exactement à `older_than` est gardé) ; migration d'un fichier v2 contenant une session → v3, session intacte, `meute.db.bak-2`.
- [ ] **Étape 2 : échec. Étape 3 : implémenter**, puis l'exception autorisée n° 1 (et rien d'autre dans `test_db_open.py`). Sélection mutmut.
- [ ] **Étape 4 : vérification complète ; `/simplify`, commit.** `git commit -m "feat(core): Claude session columns, session events and metric samples (migration 3)"`

---

### Task 4 : interprétation des hooks et réconciliation Claude

**Fichiers :**
- Créer : `src/meute/core/hooks.py`, `src/meute/core/db/hook_apply.py`
- Modifier : `src/meute/core/reconcile.py` (`settled`), `src/meute/cli/session_refresh.py` (panneaux morts sans statut)
- Test : `tests/test_hooks.py` (fixtures de la Task 1), `tests/test_db_hook_apply.py`, `tests/test_reconcile_settled.py`, `tests/test_session_refresh_settled.py`

**Interfaces :**
- Produit, dans `hooks.py` :
  - `HookEffect(state: SessionState | None, native_id: str | None = None, transcript_path: str | None = None, model: str | None = None, permission_mode: str | None = None, last_tool: str | None = None, pending_permission: str | None = None, last_message: str | None = None, history: str)` : `None` = « ne change pas » ; `history` = le texte enregistré dans `session_events.detail` ;
  - `interpret_hook(event: str, payload: Mapping[str, object]) -> HookEffect | None` : `None` = ignoré ; **ne lève jamais** ;
  - `tool_excerpt(tool_name: str, tool_input: object) -> str` : `Bash` → `command` ; `Read`, `Edit`, `Write`, `NotebookEdit` → `file_path` ; sinon la première valeur chaîne ; une seule ligne, 80 caractères au plus (`…` en fin si coupé) ; résultat `"<tool_name> <extrait>"`, ou `"<tool_name>"` sans extrait.
- Table d'interprétation (spécification § 7.1, corrigée par le rapport S7 si besoin) :

| Événement | `state` | Champs |
|---|---|---|
| `SessionStart` | `Idle()` | `native_id` ← `session_id`, `transcript_path`, `model` (chaîne, ou `id` de l'objet) |
| `UserPromptSubmit` | `Running()` | `permission_mode` |
| `PreToolUse` | `Running()` | `last_tool` ← `tool_excerpt` |
| `PermissionRequest` | `PermissionRequested()` | `pending_permission` ← `tool_excerpt` |
| `PostToolUse` | `Running()` | — |
| `PreCompact` | `Compacting()` | — |
| `SubagentStart` / `SubagentStop` | `SubagentRunning()` / `Running()` | ignorés (`None`) si `agent_type` est absent ou vide |
| `Stop` | `WaitingInput()` | `last_message` ← `last_assistant_message`, 500 caractères au plus |
| `SessionEnd` | `Exited(code=None)` | — |
| `Notification` | `None` | historique seulement : `message` |
| autre événement | `None` | historique seulement : le nom de l'événement |

- Produit, dans `db/hook_apply.py` : `apply_hook(db, session_id: SessionId, event: str, effect: HookEffect) -> bool` (`True` si l'état a changé), en une transaction `BEGIN IMMEDIATE` : insère toujours une ligne `session_events(event, effect.history)` ; si la session n'est pas vivante, ou si `effect.native_id` et le `native_id` déjà connu diffèrent, rien d'autre ; sinon écrit les champs non `None`, met `pending_permission` à `NULL` dès que le nouvel état n'est pas `PermissionRequested`, et applique `state` par la règle `ended_at` de `set_session_state` (`last_activity_at = now` à chaque hook appliqué). Session inconnue → `NotFound`.
- `PaneObservation` gagne `settled: bool = True` ; `reconcile` ne met pas à jour une session vivante dont le panneau mort n'est pas `settled`.
- Dans `apply_refresh` (CLI), un panneau mort sans `dead_status` : interroger `display-message -p -t <pane> '#{pane_dead_signal} #{pane_dead_time}'` ; signal connu → `settled`, `exit_code=None` ; pas de signal et mort depuis moins de 3 s → `settled=False` ; sinon `settled`, `exit_code=None` (tmux 3.4 a perdu le statut, report du plan 2).

- [ ] **Étape 1 : tests qui échouent.**
  - un test par ligne de la table, à partir des fixtures de la Task 1 (chargées par une aide `claude_fixture(name)` dans `tests/support.py`) ;
  - `test_subagent_hooks_without_agent_type_are_ignored` ;
  - `test_tool_excerpt` (paramétré : Bash, Edit, MCP inconnu, valeur multi-ligne, 200 caractères) ;
  - `test_interpret_hook_never_raises` (`hypothesis` : événement quelconque, payload JSON quelconque, dont types inattendus) ;
  - `apply_hook` : `test_permission_then_post_tool_clears_pending`, `test_late_hook_after_session_end_changes_nothing_but_history` (point de vigilance 4), `test_hook_of_unreachable_session_is_history_only`, `test_mismatched_native_id_is_history_only`, `test_last_activity_moves_on_each_applied_hook` ;
  - `reconcile` : `test_unsettled_dead_pane_is_not_reconciled_yet` ;
  - `apply_refresh` sur serveur tmux de test : panneau mort par signal (`kill -TERM` du processus du panneau, `remain-on-exit on`) → `Exited(code=None)` sans attendre.
- [ ] **Étape 2 : échec. Étape 3 : implémenter.** Sélection mutmut (fichiers en processus).
- [ ] **Étape 4 : vérification complète ; `/simplify`, commit.** `git commit -m "feat(core): interpret Claude hooks into session states"`

---

### Task 5 : `meute ingest hook` [sécurité]

**Fichiers :**
- Modifier : `src/meute/ingest/__init__.py` ; créer `src/meute/ingest/hook.py`, `src/meute/ingest/log.py`
- Test : `tests/test_ingest_hook.py`, `tests/test_ingest_log.py`, `tests/test_importtime.py` (nouveaux tests seulement)

**Interfaces :**
- `meute.ingest.run(args)` : `["hook", <event>]` → `run_hook(event, stdin, environ)` ; `["statusline"]` → Task 7 ; autre → rien, 0. Tout est attrapé (`BaseException` sauf `KeyboardInterrupt`/`SystemExit` relancés en 0) et journalisé.
- `run_hook(event: str, stdin: TextIO, environ: Mapping[str, str]) -> None` : lit au plus 1 MiB ; JSON objet sinon journalisé ; `MEUTE_SESSION` analysée par `parse_session_id` (invalide → ignoré sans journal) ; chemins par `Paths.from_env(environ, home=Path.home())` ; base absente → ignoré ; `Database.open_existing(busy_timeout_ms=200)` ; `interpret_hook` puis `apply_hook` ; `NotFound` → ignoré sans journal ; `sqlite3.OperationalError` (verrou) et le reste → journalisés.
- `log_failure(state_dir: Path, command: str, error: BaseException, now: datetime) -> None` dans `log.py` : une ligne `<to_db(now)> <command> <type(error).__name__>: <str(error) sur une ligne, 200 caractères au plus>` ; rotation quand le fichier dépasse 1 MiB ; ne lève jamais (un échec d'écriture du journal est avalé).

- [ ] **Étape 1 : tests qui échouent** (sous-processus `python -m meute ingest hook <Event>` avec `sandbox`) :
  - `test_hook_updates_the_session` : session Claude créée en base (état `Unknown`), `SessionStart` puis `PermissionRequest` (fixtures) → état `PermissionRequested`, `pending_permission` rempli, stdout vide, code 0 ;
  - `test_unknown_or_missing_session_is_ignored_silently` (pas de journal) ;
  - `test_invalid_json_is_logged_and_exits_zero` ;
  - `test_locked_database_drops_the_event_within_the_budget` : une connexion tient `BEGIN IMMEDIATE` → l'ingestion rend la main en moins de 1 s, code 0, une ligne `OperationalError` dans `ingest.log`, état inchangé ;
  - `test_old_schema_is_never_migrated_from_ingest` : base v2 → événement abandonné, fichier inchangé, journal ;
  - `test_parallel_hooks_all_land_or_are_logged` (point de vigilance 1) : 8 hooks `PreToolUse` lancés en parallèle → 8 lignes dans `session_events` ou, pour chacune manquante, une ligne de journal ; aucune base corrompue (`PRAGMA integrity_check` = `ok`) ;
  - `test_log_rotates_past_one_mebibyte` et `test_log_never_raises` (dossier non inscriptible) ;
  - importtime : `test_ingest_hook_path_skips_migrations_and_config` (`meute.core.db.migrations`, `meute.core.config`, `tomllib` absents de la trace).
- [ ] **Étape 2 : échec. Étape 3 : implémenter.**
- [ ] **Étape 4 : mesurer** `hyperfine -N --warmup 5 --runs 100 --input <fixture PreToolUse> 'uv run --frozen python -m meute ingest hook PreToolUse'` (base de sandbox) et, si possible, avec le script installé par `uv tool install --force .` dans un `HOME` jetable ; noter médiane et p95 dans le rapport ; au-delà de 50 ms en médiane, le signaler (pas d'optimisation non demandée).
- [ ] **Étape 5 : vérification complète ; `/simplify`, `/security-review`, commit.** `git commit -m "feat(ingest): record Claude hooks without ever disturbing the session"`

---

### Task 6 : relevés de la statusline

**Fichiers :**
- Créer : `src/meute/core/statusline.py`, `src/meute/core/db/samples.py`
- Test : `tests/test_statusline_parse.py`, `tests/test_db_samples.py`

**Interfaces :**
- `StatuslineData(cwd: str | None, model_name: str | None, effort: str | None, context_pct: float | None, five_hour_pct: float | None, five_hour_resets_at: datetime | None, seven_day_pct: float | None, seven_day_resets_at: datetime | None, cost_usd: float | None, duration_ms: int | None, lines_added: int | None, lines_removed: int | None, worktree_name: str | None, worktree_branch: str | None, worktree_path: str | None, agent_name: str | None, repo_host: str | None, repo_owner: str | None, repo_name: str | None)` ; tous les champs ont `None` pour défaut.
- `parse_statusline(payload: Mapping[str, object]) -> StatuslineData` : chemins JSON du § 7.2 et du script (`workspace.current_dir` puis `cwd` ; `model.display_name` puis `model.id` ; `agent.name`) ; une valeur de mauvais type devient `None` (pas de `bool` pour un nombre) ; `resets_at` en secondes epoch → `datetime` UTC ; ne lève jamais (propriété `hypothesis`).
- Dans `db/samples.py` :
  - `record_metrics(db, session_id, data, *, min_interval: timedelta = timedelta(seconds=30)) -> bool` : insère un relevé si la session existe et si un champ diffère du dernier relevé de la session ou si le dernier date d'au moins `min_interval` ; renvoie `True` si une ligne est écrite ;
  - `record_quota(db, data, *, min_interval=…) -> bool` : même règle sur la table `quota_samples` (compte entier, § 7.4), seulement si au moins un pourcentage est connu ;
  - `latest_metrics(db, session_id) -> StatuslineData | None`, `latest_quota(db) -> StatuslineData | None` (champs de quota seulement).

- [ ] **Étape 1 : tests qui échouent** : parse des fixtures de la Task 1 (valeurs exactes) ; types inattendus ; propriété « ne lève jamais » ; limitation d'écriture : même relevé à t et t+10 s → une ligne, à t+30 s → deux, valeur changée à t+5 s → deux ; quota sans pourcentage → rien ; session inconnue → `False`.
- [ ] **Étape 2 : échec. Étape 3 : implémenter.** Sélection mutmut.
- [ ] **Étape 4 : vérification complète ; `/simplify`, commit.** `git commit -m "feat(core): statusline samples with write throttling"`

---

### Task 7 : rendu de la statusline et `meute ingest statusline` [sécurité]

Portage fidèle de `statusline-command.sh` (dépôt `gaetinux/claude-statusline`), avec trois écarts voulus : textes en anglais (`7d` au lieu de `7j`), heures pleines lues dans `[quotas]` au lieu d'être fixées à 8 h–14 h New York, et `printable` sur toute donnée de Claude.

**Fichiers :**
- Créer : `src/meute/core/statusline_render.py`, `src/meute/core/clock.py` (`local_zone` déplacé du CLI ; `meute/cli/context.py` le réimporte sous le même nom), `src/meute/ingest/statusline.py`
- Modifier : `src/meute/core/config_validate.py` et `src/meute/core/config.py` (section `[statusline]`)
- Test : `tests/test_statusline_render.py` (+ instantanés), `tests/test_ingest_statusline.py`, `tests/test_config.py` (nouveaux tests)

**Interfaces :**
- `render_statusline(data: StatuslineData, *, user: str, now: datetime, quotas: QuotasConfig, local: tzinfo, width: int) -> str`, segments et règles du script :
  - toujours : `\033[1;32m➜\033[0m \033[1m{user}\033[0m \033[36m{basename(cwd) ou "~"}\033[0m`, le modèle `\033[35m{model}\033[0m` (défaut `Claude`), le 5 h s'il est connu, puis heures pleines ;
  - barre `mini_bar(pct)` : 5 cases, `filled = (pct + 10) * 5 // 100` bornée à 0–5, `█` puis `░` ; couleur `pct_color` : `31` à partir de 80, `33` à partir de 50, `32` sinon ; pourcentages arrondis comme `printf '%.0f'` (au pair le plus proche) ;
  - 5 h : `\033[{c}m{barre}\033[0m \033[90m5h\033[0m {n}%` ; contexte : idem avec `ctx` ; 7 j : idem avec `7d`, **seulement au-dessus de 50 %** ;
  - coût : `${cost:.2f}`, seulement au-dessus de 0,10 ; worktree et agent : `\033[36m{nom}\033[0m` ;
  - durée seulement au-delà de 600 000 ms : `\033[90m{h}h{mm}m\033[0m` à partir d'une heure, sinon `\033[90m{m}m\033[0m` ;
  - lignes : `\033[32m+{a}\033[0m` et `\033[31m-{d}\033[0m` (ceux qui sont non nuls, séparés par une espace) ;
  - heures pleines (jours ouvrés, de `peak_start_hour` à `peak_end_hour` dans `peak_timezone`) : pendant → `\033[1;31m⚡ PEAK\033[0m \033[90m(~{fin - heure}h left)\033[0m` ; week-end, ou vendredi après la fin → `\033[1;32m✦ OFF-PEAK\033[0m \033[90m(weekend)\033[0m` ; après la fin un jour ouvré → `… (until {heure locale du début}h)` ; avant le début → `… (peak in ~{début - heure}h)` ;
  - séparateur ` \033[90m│\033[0m ` ; assemblage et repli à la largeur exactement comme le script (palier 3 : 7d, durée, lignes ; palier 2 : contexte, coût, worktree, agent, réajoutés dans l'ordre `wt, ag, ctx, cost` lors du second repli), longueur visible = sans les séquences `\033[…m`.
- `statusline_width(environ: Mapping[str, str], tty_columns: Callable[[], int | None]) -> int` : `COLUMNS` entier positif, sinon les colonnes du terminal si plus de 80, sinon 200 (logique du script).
- `[statusline]` dans `DEFAULT_CONFIG`, après `[quotas]` :

  ```toml
  [statusline]
  # Optional command that receives the same JSON and replaces meute's status line.
  chain = ""
  ```

  `StatuslineConfig(chain: str = "")`, champ `Config.statusline`.
- `run_statusline(stdin, stdout, environ) -> None` (ingest) : lit le JSON (1 MiB au plus), enregistre relevés et quota si la session est connue (échecs journalisés, jamais bloquants), lit la configuration (`tomllib` autorisé sur ce chemin seulement), puis écrit le rendu, ou la sortie de `chain` : `["/bin/sh", "-c", chain]`, même stdin, délai de 1 s ; échec, délai dépassé ou sortie vide → le rendu de meute.

- [ ] **Étape 1 : tests qui échouent.**
  - unitaires de chaque segment (barre aux bornes 0, 9, 10, 89, 90, 100, 150 ; couleurs 49/50/79/80 ; coût 0,10 et 0,11 ; 7 j 50 et 51 ; durées 600 000, 600 001, 3 900 000 ms ; lignes +3, -2, les deux, aucune) ;
  - heures pleines avec `now` fixés : mardi 10 h New York, mardi 15 h, vendredi 15 h, samedi, mardi 6 h ; fuseau local Europe/Paris ;
  - instantanés `syrupy` du rendu d'une fixture riche à 200, 120, 80 et 60 colonnes, relus contre les règles ci-dessus (afficher la chaîne avec ses `\033` dans l'instantané) ;
  - `test_claude_data_cannot_inject_escapes` (point de vigilance 3) : nom de modèle, worktree, agent et dossier contenant `\x1b]0;x\x07` → aucun `\x1b` hors des séquences de couleur produites par meute ;
  - `test_statusline_prints_even_for_unknown_session` ; `test_statusline_records_samples` ; `test_chain_replaces_the_output` ; `test_failing_or_slow_chain_falls_back` (commande `sleep 5` → rendu de meute en moins de 2 s) ;
  - config : `test_default_config_has_statusline_section`.
- [ ] **Étape 2 : échec. Étape 3 : implémenter.** Sélection mutmut.
- [ ] **Étape 4 : comparer à la main** le rendu de meute et celui de `statusline-command.sh` (cloné dans le scratchpad, `jq` requis) sur deux fixtures, `COLUMNS=200` et `COLUMNS=80` ; les seules différences admises sont les trois écarts voulus ; noter le résultat dans le rapport.
- [ ] **Étape 5 : vérification complète ; `/simplify`, `/security-review`, commit.** `git commit -m "feat: port the author's status line and meute ingest statusline"`

---

### Task 8 : `meute.claude` — ligne de commande et `--settings` [sécurité]

**Fichiers :**
- Créer : `src/meute/claude/launch.py`, `src/meute/claude/settings.py`
- Test : `tests/test_claude_settings.py`, `tests/test_claude_launch.py`

**Interfaces :**
- `HOOK_EVENTS: tuple[str, ...]` = les 11 événements de la Task 1.
- `settings_document(meute_command: Sequence[str]) -> JsonObject` : pour chaque événement, la forme validée par le rapport S7, avec la commande `shlex.join([*meute_command, "ingest", "hook", event])` ; `statusLine` : `{"type": "command", "command": shlex.join([*meute_command, "ingest", "statusline"])}` (plus les champs que S7 a montrés nécessaires).
- `write_settings(state_dir: Path, session_id: SessionId, meute_command: Sequence[str]) -> Path` : `<état>/sessions/<id>/settings.json`, dossier `0o700`, fichier `0o600`, écriture atomique.
- `claude_argv(*, claude: Path, settings: Path, session_id: SessionId, permission_mode: str, title: str) -> tuple[str, ...]` : `(str(claude), "--settings", str(settings), "--session-id", session_id, "--permission-mode", permission_mode, f"--name={title}")` (forme validée par S7) ; `permission_mode` hors de `PERMISSION_MODES` → `InvalidInput("unknown permission mode: <mode>")`.
- `find_claude(environ: Mapping[str, str]) -> Path | None` : `shutil.which("claude", path=environ.get("PATH"))`.

- [ ] **Étape 1 : tests qui échouent** : document égal en structure au `settings.json` capturé (Task 1) aux commandes près ; commandes correctement citées pour un `sys.executable` contenant une espace et une apostrophe (`shlex.split` les rend à l'identique) ; permissions des fichiers ; `claude_argv` exact ; mode inconnu ; titre commençant par `-`.
- [ ] **Étape 2 : échec. Étape 3 : implémenter.** Sélection mutmut.
- [ ] **Étape 4 : vérification complète ; `/simplify`, `/security-review`, commit.** `git commit -m "feat(claude): command line and settings file for managed sessions"`

---

### Task 9 : lancer une session Claude (CLI et tableau de bord) [sécurité]

**Fichiers :**
- Modifier : `src/meute/cli/session_launch.py` (ou créer `session_launch_claude.py` si le fichier dépasse 300 lignes), `src/meute/cli/session_commands.py`, `src/meute/core/board_view.py`, `src/meute/tui/board.py`, `src/meute/cli/board_backend.py`, `src/meute/core/config_validate.py` (`claude.stuck_after_minutes`)
- Test : `tests/test_cli_session_claude.py`, `tests/test_board_view_claude.py`, `tests/test_tui_board_claude.py` ; instantanés SVG régénérés (exception autorisée n° 3)

**Interfaces :**
- `ClaudeLaunch(cwd: Path, title: str | None = None, repo_id: RepoId | None = None, permission_mode: str | None = None)` ; `launch_claude(ctx, env, request, environ) -> Session` : comme `launch_bash` (dossier vérifié avant toute écriture, panneau tué si l'écriture échoue), avec `find_claude` (absent → `InvalidInput("claude not found: Claude sessions are disabled; Bash sessions remain available with --kind bash")`), `write_settings`, la commande `claude_argv(...)` (mode : la demande, sinon `ctx.config.claude.permission_mode`), `AgentKind.CLAUDE`, état initial `Unknown()`.
- CLI : `meute session new --kind claude|bash` (**`claude` par défaut**), `--permission-mode <mode>` (Claude seulement ; avec `--kind bash` → `InvalidInput("--permission-mode only applies to Claude sessions")`). `meute session list` : pour une session Claude, la ligne gagne le mode entre crochets à la fin, `  [manual]`, `  [auto]`… ; `--json` : chaque session Claude gagne la clé `"claude"` (`claude_details_to_json`).
- `stuck_after_minutes` : entier ≥ 1, défaut 10, ajouté à `[claude]` dans `DEFAULT_CONFIG` avec le commentaire `# Minutes without any hook before a running session is shown as stuck?`.
- Tableau de bord : action `LaunchClaude(cwd: Path, repo_id: RepoId | None)` ajoutée à `BoardAction` ; `claude_action(entry) -> LaunchClaude` (mêmes règles que `new_action`) ; touche `c` → `perform(claude_action(...))` ; `FOOTER = "↑↓ select · Enter show · c Claude · n Bash · x stop"` ; le backend lance puis affiche la session.

- [ ] **Étape 1 : tests qui échouent** (un faux `claude` minimal dans `tmp_path` : script qui écrit ses arguments dans un fichier puis `sleep 3600`) :
  - `test_new_defaults_to_claude_with_explicit_permission_mode` : arguments reçus exacts (`--permission-mode manual` depuis la config) ; panneau dans `meute-bg` avec `@meute_id` ; settings écrit en `0o600` ;
  - `test_permission_mode_option_wins` ; `test_permission_mode_with_bash_is_refused` ;
  - `test_missing_claude_fails_clearly_and_bash_still_works` (point de vigilance 5) ;
  - `test_session_list_shows_permission_mode` et `--json` avec la clé `claude` ;
  - board : `c` sur un dépôt et sur une session → `LaunchClaude` ; instantanés relus (seul le pied de page change).
- [ ] **Étape 2 : échec. Étape 3 : implémenter**, puis régénérer et relire les SVG (exception n° 3).
- [ ] **Étape 4 : vérification complète ; `/simplify`, `/security-review`, commit.** `git commit -m "feat: launch Claude sessions with an explicit permission mode"`

---

### Task 10 : faux `claude` et essai de bout en bout

**Fichiers :**
- Créer : `tests/fake_claude/claude` (exécutable Python, `#!/usr/bin/env python3`), `tests/test_claude_e2e.py`
- Modifier : `tests/conftest.py` (la fixture `sandbox` met `tests/fake_claude` en tête du `PATH` ; infrastructure seulement)

**Comportement du faux `claude` :**
- `claude --settings <f> --session-id <id> …` : lit `<f>`, rejoue une séquence de fixtures de la Task 1 (choisie par la variable `MEUTE_FAKE_CLAUDE_SCRIPT`, défaut `permission`) en lançant pour chaque hook la commande du fichier (`shlex.split`) avec le JSON sur stdin, `session_id` remplacé par `<id>` ; appelle aussi la statusline ; puis attend (`sleep`) jusqu'à `SIGTERM`, sauf la séquence `exit`, qui sort avec le code 0 après `SessionEnd`.
- Séquences : `permission` (`SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PermissionRequest`), `done` (… `PostToolUse`, `Stop`), `exit` (… `SessionEnd`, sortie 0).
- `claude agents --json` : imprime le contenu de `MEUTE_FAKE_CLAUDE_AGENTS` (un fichier), sinon `[]`.

- [ ] **Étape 1 : tests qui échouent** :
  - `test_claude_session_reaches_permission_requested` : `session new` (Claude par défaut) → attente → `session list` montre `permission` et `[manual]` ;
  - `test_finished_turn_waits_for_reply` (`done` → `waiting for your reply`, `last_message` en base) ;
  - `test_session_end_then_exit_is_exited` (`exit` → `exited`) ;
  - `test_statusline_samples_are_recorded` ;
  - `test_dashboard_shows_claude_states` (le vrai tableau dans un panneau, comme `test_board_e2e.py`) : la ligne de la session affiche `permission`.
- [ ] **Étape 2 : échec. Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète ; `/simplify`, commit.** `git commit -m "test: end-to-end Claude sessions with a fake claude"`

---

### Task 11 : `claude agents --json`, sessions hors de meute et états supposés [sécurité]

**Fichiers :**
- Créer : `src/meute/claude/agents.py`, `src/meute/core/agents.py`, `src/meute/cli/agents_poller.py`
- Modifier : `src/meute/cli/session_refresh.py`, `src/meute/cli/session_commands.py`, `src/meute/core/board_view.py`, `src/meute/cli/board_backend.py`
- Test : `tests/test_agents_parse.py`, `tests/test_agents_rules.py`, `tests/test_agents_poller.py`, `tests/test_cli_session_outside.py`, `tests/test_board_view_outside.py`

**Interfaces :**
- Dans `core/agents.py` (pur) :
  - `AgentInfo(pid: int, cwd: str, kind: str, session_id: str, name: str, status: str)` ; `parse_agents(text: str) -> tuple[AgentInfo, ...]` : liste JSON d'objets ; entrées incomplètes ignorées ; texte illisible → `()` ; ne lève jamais ;
  - `assumed_state(session: Session, agent: AgentInfo | None, *, now: datetime, stuck_after: timedelta) -> SessionState | None` : seulement pour une session Claude vivante dont `last_activity_at` est plus ancien que `stuck_after` ; avec `agent` : `busy` → `Running()`, `waiting` → `WaitingInput()`, `idle` → `Idle()` ; sans `agent`, si l'état est `Running` ou `SubagentRunning` → `MaybeStuck()` ; sinon `None` (aucun changement si l'état déduit est déjà l'état courant) ;
  - `outside_agents(agents, sessions) -> tuple[AgentInfo, ...]` : ceux dont `session_id` n'est ni l'`id` ni le `native_id` d'une session de meute.
- Dans `claude/agents.py` : `run_agents(claude: Path, *, timeout: float = 2.0) -> str | None` (`None` en cas d'échec, de délai ou de code non nul).
- Dans `cli/agents_poller.py` : `AgentsPoller(claude: Path | None, *, every: float = 10.0, monotonic=…)` avec `poll() -> tuple[AgentInfo, ...] | None` : lance `claude agents --json` en `Popen` non bloquant au plus toutes les `every` secondes, récolte le résultat quand le processus est fini (`None` tant que rien de neuf), tue un processus qui dépasse 5 s.
- `refresh` reçoit `agents: Sequence[AgentInfo] | None` (mot-clé, défaut `None` = ne pas consulter) et applique `assumed_state` après la réconciliation ; `Snapshot` gagne `outside: tuple[AgentInfo, ...] = ()`.
- `meute session list` : appelle `run_agents` (si `claude` est trouvé) ; une ligne `outside: {status}  {name}  {display_path(cwd)}` par session hors de meute, après les orphelins ; `--json` gagne la clé `"outside"`.
- Tableau de bord : `BoardData.outside: tuple[AgentInfo, ...] = ()` ; section `Outside meute` (lecture seule, non sélectionnable) après les dépôts, seulement si elle n'est pas vide, une ligne `{name}  {status}  {display_path(cwd)}` ; le backend utilise `AgentsPoller`.
- Au démarrage de `meute board` : `purge_samples(older_than=now - 30 jours)` (§ 13).

- [ ] **Étape 1 : tests qui échouent** : `parse_agents` sur la fixture de la Task 1, sur `""`, `"{}"`, une entrée sans `pid` ; `assumed_state` (table des cas : récent, ancien avec chaque statut, ancien sans agent en `Running`, en `WaitingInput`, session Bash, session terminée) ; `outside_agents` ; poller : pas de second processus avant `every`, résultat récolté, processus lent tué, `claude` absent → toujours `None` ; `session list` avec le faux `claude` et `MEUTE_FAKE_CLAUDE_AGENTS` : ligne `outside:` exacte, et `claude agents` en échec (fichier illisible) → liste normale (point de vigilance 5) ; `board_lines` avec et sans section `Outside meute` (instantané nouveau, les anciens inchangés) ; purge au démarrage du tableau.
- [ ] **Étape 2 : échec. Étape 3 : implémenter.** Sélection mutmut.
- [ ] **Étape 4 : vérification complète ; `/simplify`, `/security-review`, commit.** `git commit -m "feat: sessions outside meute and assumed states from claude agents"`

---

### Task 12 : essai réel, mutations, feuille de route et PR

- [ ] **Étape 1 : essai réel scripté** (accord de l'auteur), sur un serveur tmux jetable et une base sandbox (`XDG_*` dans le scratchpad), dans le dépôt meute (dossier déjà approuvé) : `meute layout sync`, `meute session new --title essai` (vrai `claude`), prompt `Reply with the single word pong.` par `send-keys`, attendre `waiting for your reply` dans `session list`, vérifier un relevé dans `metric_samples` et la statusline affichée dans le panneau (`capture-pane`), puis `session stop --yes`. Noter chaque résultat dans le rapport. Le serveur tmux est tué, `~/.claude/settings.json` et le dépôt sont inchangés (`git status`).
- [ ] **Étape 2 : mutmut** sur `src/meute/core/`, `src/meute/git/`, `src/meute/tmux/parse.py`, `src/meute/tmux/conf.py`, `src/meute/claude/` ; traiter chaque survivant nouveau en TDD ou le justifier ; rapport `docs/dev/mutants/2026-plan-3-python.md`.
- [ ] **Étape 3 : feuille de route** : plan 3 « fait », « Reports issus du plan 3 » (liste « Hors périmètre » ci-dessus), retirer les reports traités (ouverture concurrente, caractères de contrôle, statut de sortie des panneaux, `--kind`).
- [ ] **Étape 4 : vérification complète** (`verify.sh`, profil `ci`, tests des hooks) ; `/simplify` et `/security-review` sur la branche ; revue finale ; corrections.
- [ ] **Étape 5 : commit, push, PR** `Plan 3 (Python): Claude adapter`, assignée à `gaetinux`, avec les exceptions de tests, les exceptions de lint, la mesure `hyperfine` de la Task 5, le rapport S7, l'essai réel et le rapport de mutation ; dernière ligne `🤖 Generated with [Claude Code](https://claude.com/claude-code)`, sans lien de session.
