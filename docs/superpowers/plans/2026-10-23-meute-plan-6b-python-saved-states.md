# meute — Plan 6b Python : reprise et états sauvegardés — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Objectif :** on retrouve ses sessions en une touche après une journée ou un redémarrage (`O`, `meute state open`). `S` et `meute state save` gardent des ensembles de sessions, le tableau tient `last` à jour, et la CLI reprend une session Claude récente.

**Architecture :** comme aux plans précédents :
- ce qui se décide est dans `meute.core`, pur et sur la stdlib seule : le modèle d'un état, son JSON, les noms, la rétention, ce qu'on capture d'un tableau et les textes ;
- la base gagne la table `saved_states` (migration 005) et son module `meute.core.db.saved_states` ;
- `meute.cli` assemble : il capture, met `last` à jour depuis le backend du tableau, rouvre un état et porte les commandes `meute state` ;
- `meute.tui` ajoute `S`, `O` et le panneau de la liste.

**Stack technique :** l'existant (Python 3.13, uv, Typer, Textual 8.2, `syrupy`, `hypothesis`, `mutmut`). Aucune nouvelle dépendance.

**Spécification :**
- conception de ce plan : `docs/superpowers/specs/2026-10-23-meute-saved-states-design.md` ;
- spécification générale : `docs/superpowers/specs/2026-10-15-meute-design.md`, § 6.5, § 6.6 et § 13 ;
- guide : `docs/dev/developpement-assiste-par-ia.md`.

**Prérequis :** le plan 6a est mergé (PR #14). La branche `feat/plan-6b-python` a été créée sur `main` à jour (166fc28) et porte la conception (671981f).

## Décisions de conception (à relire)

1. **L'ordre d'un état est celui du tableau.** Il est calculé à partir de la donnée déjà lue, avec `board_sessions(data, ViewState())`, comme le fait `board_order` (`cli/session_next.py`), sans deuxième lecture.
2. **`last` est mis à jour dans `CliBoardBackend._read`**, juste après `load_board_data`, par `cli/last_state.py`.
   - La dernière liste écrite est relue en base au premier passage.
   - Rien n'est écrit si la liste des ids n'a pas changé ou si elle est vide.
   - Une écriture de cette connexion ne change pas sa propre `data_version` (SQLite), donc elle ne relance pas de relecture.
3. **Le tableau lit la liste des états par `BoardData.saved_states`**, un tuple vide par défaut, rempli par `load_board_data`. `BoardBackend` ne change pas, et les faux backends des tests existants restent valides.
4. **`S` et la réouverture sont deux actions du tableau**, `SaveState()` et `ReopenState(name)`, exécutées par `CliBoardBackend._perform`. La réouverture passe par `BoardWorkers` ; la sauvegarde est rapide et se fait sur le fil de l'interface, comme `n`.
5. **`sessions_tab.py` (298 lignes) est découpé.** Les touches `S` et `O` et l'état de la liste vont dans `tui/saved_states_panel.py`, que l'onglet appelle. `board_backend.py` (285 lignes) délègue `SaveState` et `ReopenState` à `cli/state_actions.py`.
6. **La réouverture réutilise l'existant :** `resume_session` (Claude), `launch_bash` (Bash) et `show_session` (la session affichée). Elle ne crée aucune variante de ces fonctions.
7. **`recent_days` passe par la configuration chargée**, `ctx.config.ui.recent_days`. `RECENTLY_ENDED` disparaît de `cli/board_data.py`.

## Contraintes globales

**Hérité des plans 1 à 6a (inchangé)**
- **Frontières d'imports** (import-linter) : `meute.core`, `meute.tmux` et `meute.git` n'utilisent que la stdlib et ne s'importent pas entre eux. `meute.tui` n'importe ni `meute.tmux` ni `meute.git`. Seul `meute.cli` assemble.
- **Code :**
  - dataclasses gelées, `match` exhaustif terminé par `assert_never` ;
  - pas d'`Any`, de `cast` ni d'`assert` hors des tests ;
  - docstrings sur tout le public de `meute.core` ;
  - fichiers de moins de 300 lignes ;
  - exceptions de lint précises, suivies de ` — raison`.
- **Textes :**
  - interface en anglais, textes de la conception copiés mot pour mot ;
  - toute donnée affichée passe par `printable` ou `shown_path` (`meute.core.paths`) ;
  - tout argument passé à tmux passe par `Tmux.run`.
- **Tests :**
  - tmux uniquement sur des serveurs jetables (`tmux_server`, `sandbox`) ;
  - le faux `claude` (`tests/fake_claude/claude`), jamais le vrai ;
  - ni le serveur `meute`, ni le serveur tmux `default`, **même en lecture seule** ;
  - jamais de modification de `~/.claude/settings.json` ni de `~/.claude.json`.

**Propre au plan 6b**
- **Valeurs :** `recent_days` va de 1 à 365, 7 par défaut. Il y a `RETAINED = 10` états nommés, plus `LAST = "last"`, réservé. Un nom fait 60 caractères au plus.
- **Nom horodaté :** `YYYY-MM-DD HH:MM`, en heure locale (`local_now(ctx)`).
- **Textes exacts** (conception) :
  - `resumable`, `no conversation id`, `Resumed: <id court> <titre>` ;
  - `state name is empty`, `last is kept by the board`, `no saved state named <nom>` ;
  - `already running`, `folder not found: <chemin>` ;
  - `reopened <n> · skipped <m>`, et `  <titre>: <raison>` pour chaque session ignorée ;
  - `state saved: <nom>`, `reopening <nom>…`, `no saved state` ;
  - `<nom>  <n> sessions  <âge>`, avec `1 session` au singulier ;
  - `Saved: <nom> (<n> sessions)`, `Remove saved state "<nom>"? [y/N]`, `Removed: <nom>` ;
  - `S save the open sessions · O reopen a saved state` (ligne de l'aide).
- **JSON de `meute state list --json` :** `{"states": [{"name", "created_at", "sessions"}]}`.
- **JSON de `meute session recent --json` :** `{"sessions": [{"id", "title", "cwd", "ended_at", "resumable"}]}`.

**Qualité et workflow**
- **TDD strict.** Ne jamais modifier, supprimer ni désactiver un test existant. Les seules exceptions demandées par ce plan prolongent la numérotation du plan 6a. **Elles sont à autoriser par l'auteur à la relecture du plan.** Chacune est signalée dans le commit et dans la PR :
  - **n° 29** (Task 7) : les tests et instantanés qui montrent l'aide `?` des sessions (`KEYS_HELP`) gagnent la ligne `S save the open sessions · O reopen a saved state`, placée après la ligne de `W`. Rien d'autre ne change.
  - **n° 30** (Task 1), seulement si un tel test existe : un test ou instantané qui liste toutes les clés de configuration, par exemple `meute config get` sans clé, gagne `ui.recent_days = 7`. Rien d'autre ne change.
- **Instantanés :** relus ligne par ligne, jamais de `--snapshot-update` à l'aveugle. Avec xdist, la mise à jour se fait avec `-n0`.
- **Fin de tâche :** chaque tâche se termine par `bash scripts/verify.sh` et un commit.
- **Commits :** en anglais, terminés par `Co-Authored-By: Claude …`, sans ligne `Claude-Session`.
- **PR :** une seule, à la fin, **titre et corps en anglais**, assignée à `gaetinux`.

## Hors périmètre

- **Non prévu ici :**
  - les conversations Claude démarrées hors de meute ;
  - un écran dédié aux sessions récentes ;
  - le choix du nom dans le tableau ;
  - l'historique d'un shell.
- **Plan 6c :** projets créés automatiquement, `meute doctor`, purge de `session_events`, README final.

## Points de vigilance (Review Focus)

1. **Un redémarrage de la machine.** Le tableau démarre, et toutes les sessions sont `Unreachable` : `last` doit garder la liste d'avant. Test au Task 4, avec la liste vide vue au premier passage.
2. **Un état ancien ou abîmé.** Le JSON d'un état peut contenir un champ manquant, un id illisible ou un `agent` inconnu, par exemple écrit à la main en SQL. L'état s'ouvre avec les entrées valides, et rien ne lève. Test au Task 3 (propriété `hypothesis`) et au Task 5.
3. **Rouvrir deux fois de suite.** Le second passage ne lance rien : toutes les sessions Claude sont vivantes, et chaque Bash a une Bash vivante dans son dossier, d'où `already running`. Test au Task 5.
4. **Un nom étrange.** Un nom de 61 caractères, avec un saut de ligne, une séquence d'échappement, des espaces seuls ou `LAST` en majuscules. Le nom est nettoyé ou refusé avec le texte exact, et rien d'illisible ne s'affiche. Tests au Task 3 et au Task 6. `last` est comparé tel quel : `LAST` est un nom ordinaire.
5. **Rouvrir pendant qu'une autre question est ouverte** dans le tableau, ou pendant qu'une réouverture tourne. Rien ne part en double, et la question ouverte garde la main, comme au plan 6a (R19). Test au Task 7.

---

### Task 1 : `recent_days`

**Fichiers :**
- Modifier :
  - `src/meute/core/config.py` : `UiConfig.recent_days: int = 7`, et dans `DEFAULT_CONFIG`, sous `[ui]`, `# Ended sessions shown by e (and meute session recent), in days.` puis `recent_days = 7` ;
  - `src/meute/core/config_validate.py` : `_int(ui, "ui.recent_days", 7, 1)` avec une borne haute de 365, et la clé dans `_flatten` ;
  - `src/meute/cli/board_data.py` : `recently_ended` prend `days: int`, et `RECENTLY_ENDED` est supprimé.
- Test : `tests/test_recent_days.py`

**Interfaces :**
- Produit :
  - `UiConfig.recent_days` ;
  - `recently_ended(ctx, shown, now)`, qui lit `ctx.config.ui.recent_days` ;
  - `recent_ended_sessions(ctx, now) -> tuple[Session, ...]` dans `cli/board_data.py`, qui donne les sessions Claude terminées depuis moins de `recent_days` jours, la plus récente d'abord, pour le Task 2.

- [ ] **Étape 1 : écrire les tests, qui doivent échouer.**
  - `ui.recent_days` vaut 7 par défaut.
  - `meute config set ui.recent_days 14` est accepté, puis relu.
  - `0`, `366` et `"x"` sont refusés avec le message habituel de `_int`.
  - Une session terminée il y a 8 jours est montrée avec 14, et cachée avec 7.
- [ ] **Étape 2 : vérifier l'échec, puis lancer toute la suite.** Un test qui liste toutes les clés relève de l'exception n° 30 ; tout autre échec est un défaut.
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète, puis commit** `git commit -m "feat: recent_days sets how long ended sessions stay on the board"`

---

### Task 2 : `meute session recent` et `meute session resume`

**Fichiers :**
- Modifier : `src/meute/cli/session_commands.py`, et déplacer `stop` dans `src/meute/cli/session_stop_command.py` si le fichier dépasse 300 lignes.
- Test : `tests/test_cli_session_recent.py`

**Interfaces :**
- Consomme : `recent_ended_sessions` (Task 1), `claude_details_by_session`, `resume_session(ctx, env, session_id, environ)`, `find_session(db, prefix)` et `age_text`.
- Produit : les commandes `recent [--json]` et `resume <id>`.

- [ ] **Étape 1 : écrire les tests, qui doivent échouer.**
  - **`recent` :** une ligne par session, `<id court>  <titre>  <~dossier>  <âge>  resumable|no conversation id`. Les instantanés `syrupy` couvrent le texte et `--json`, la plus récente d'abord. Les sessions Bash et vivantes sont exclues. Le titre et le dossier passent par `printable`.
  - **`resume` :** avec le sandbox et le faux `claude`, elle donne `Resumed: <id court> <titre>`. Une session vivante ou une session Bash donnent les erreurs de `resume_session`, au mot près.
- [ ] **Étape 2 : vérifier l'échec.**
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète, puis commit** `git commit -m "feat: meute session recent and meute session resume"`

---

### Task 3 : modèle d'un état et table `saved_states`

**Fichiers :**
- Créer :
  - `src/meute/core/saved_state.py` ;
  - `src/meute/core/db/sql/005_saved_states.sql` ;
  - `src/meute/core/db/saved_states.py` ;
  - `tests/test_saved_state.py`, `tests/test_db_saved_states.py`.

**Interfaces :**
- **Les types, dans `meute.core.saved_state` :**
  - `SavedSession` est une dataclass gelée, kw_only, avec les champs `session_id: SessionId`, `agent: AgentKind`, `cwd: Path`, `native_id: str | None`, `title: str`, `task_id: TaskId | None`, `repo_id: RepoId | None` et `displayed: bool` ;
  - `SavedState` a les champs `name: str`, `created_at: datetime` et `sessions: tuple[SavedSession, ...]`.
- **Les constantes :** `LAST = "last"`, `RETAINED = 10`, `NAME_LIMIT = 60`.
- **Le JSON :**
  - `sessions_json(sessions) -> str` produit un tableau JSON compact ;
  - `parse_sessions(text: str) -> tuple[SavedSession, ...]` ne lève jamais et ignore toute entrée invalide. Le `session_id` passe par `parse_session_id` et doit être sous sa forme exacte. Le `cwd` doit être absolu, et l'`agent` faire partie des valeurs d'`AgentKind`.
- **Les noms :**
  - `state_name(text: str) -> str` applique `one_line(text.strip(), NAME_LIMIT)`. Il lève `InvalidInput("state name is empty")` pour un nom vide, et `InvalidInput("last is kept by the board")` pour `last`, comparé tel quel ;
  - `stamp_name(now: datetime) -> str` donne `now.strftime("%Y-%m-%d %H:%M")`.
- **Les textes :**
  - `reopen_text(reopened: int, skipped: Sequence[tuple[str, str]]) -> list[str]` produit la ligne de compte, puis `  <titre>: <raison>` pour chaque session ignorée ;
  - `state_line(state, now) -> str` produit `<nom>  <n> sessions  <âge>`.
- **La migration 005 :** `CREATE TABLE saved_states (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, sessions TEXT NOT NULL);`
- **Le module de base, `meute.core.db.saved_states` :**
  - `save_state(db, name, sessions) -> SavedState`. Il fait un upsert sur `name` qui renouvelle `created_at`. Si `name != LAST`, il supprime les états nommés au-delà de `RETAINED`, du plus ancien au plus récent, sans compter `last`. Le tout se fait dans une seule transaction ;
  - `list_states(db) -> tuple[SavedState, ...]` renvoie `last` d'abord, puis les autres du plus récent au plus ancien ;
  - `get_state(db, name) -> SavedState`, qui lève `NotFound` avec le texte `no saved state named <nom>` ;
  - `delete_state(db, name) -> None`, qui lève `NotFound` de la même façon.

- [ ] **Étape 1 : écrire les tests, qui doivent échouer.**
  - **Le JSON.** L'aller-retour `parse_sessions(sessions_json(x)) == x` est vérifié par `hypothesis`, et `parse_sessions` ne lève jamais, quel que soit le texte. Un instantané fige le JSON. Une entrée avec `agent: "zsh"`, une sans `cwd` et une avec un id en majuscules sont chacune ignorées (**point de vigilance 2**).
  - **Les noms (point de vigilance 4).** Le nom de 61 caractères est coupé, `"a\nb"` est mis sur une ligne, `"   "` et `last` sont refusés avec le texte exact, et `LAST` est accepté.
  - **La base.**
    - Une base vide puis une base de la version 4 passent toutes deux la migration, avec la sauvegarde `meute.db.bak-4`.
    - 11 sauvegardes laissent 10 états nommés, `last` restant à part.
    - Sauver sous le même nom remplace l'état et le fait remonter en tête.
    - L'ordre de `list_states` est vérifié.
    - `get_state` et `delete_state` lèvent `NotFound` sur un nom inconnu, avec le texte exact.
- [ ] **Étape 2 : vérifier l'échec.**
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète, puis commit** `git commit -m "feat(core): saved states and their table"`

---

### Task 4 : capture et état `last`

**Fichiers :**
- Créer : `src/meute/core/state_capture.py`, `src/meute/cli/last_state.py`, `tests/test_state_capture.py`, `tests/test_last_state.py`
- Modifier :
  - `src/meute/cli/board_backend.py`, dans `_read` (décision 2) ;
  - `src/meute/cli/board_data.py` : `BoardData.saved_states` (décision 3), rempli par `list_states` ;
  - `src/meute/core/board_view.py` : le champ `saved_states: tuple[SavedState, ...] = ()`.

**Interfaces :**
- `capture(data: BoardData, order: Sequence[SessionId]) -> tuple[SavedSession, ...]` (cœur). Elle garde les sessions vivantes de `data.sessions`, dans l'ordre de `order`. Elle prend `native_id` dans `data.details`, et `displayed` dans la ligne de session.
- `board_session_order(data: BoardData) -> tuple[SessionId, ...]` (cœur), la règle de `board_order` appliquée à une donnée déjà lue. `cli/session_next.board_order` s'en sert aussi.
- `LastState(db)` (cli) a une méthode `update(sessions: tuple[SavedSession, ...]) -> bool`. Elle écrit `last` seulement si les ids diffèrent de la dernière liste écrite **et** que la liste n'est pas vide. La dernière liste est lue en base au premier appel. La méthode renvoie `True` quand elle a écrit.

- [ ] **Étape 1 : écrire les tests, qui doivent échouer.**
  - **`capture` :** l'ordre, l'exclusion des sessions terminées, le `native_id`, le `displayed`, et une session Bash sans détails.
  - **`LastState` :**
    - une première liste est écrite ;
    - la même liste n'est pas réécrite ;
    - une liste vide n'est jamais écrite ;
    - **point de vigilance 1 :** une base qui a déjà un `last` à 3 sessions, suivie d'un premier appel avec une liste vide (redémarrage), garde `last` intact ;
    - un ordre changé est réécrit.
  - **Le backend :** une relecture qui voit une nouvelle session vivante met `last` à jour, et `load()` porte `saved_states`.
  - **Non-régression :** les tests existants du backend passent sans changement.
- [ ] **Étape 2 : vérifier l'échec.**
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète, puis commit** `git commit -m "feat: the board keeps the last state of its live sessions"`

---

### Task 5 : rouvrir un état

**Fichiers :**
- Créer : `src/meute/cli/state_reopen.py`, `tests/test_state_reopen.py`

**Interfaces :**
- `reopen_state(ctx: CliContext, env: TmuxEnv, environ: Mapping[str, str], state: SavedState) -> ReopenReport`, avec `ReopenReport(reopened: int, skipped: tuple[tuple[str, str], ...])` (le titre et la raison de chaque session ignorée).
- **Les règles, dans l'ordre**, telles que les fixe le tableau « Rouvrir un état » de la conception :
  1. **Session vivante :** si la session de même id est vivante, elle est ignorée avec `already running`.
  2. **Session Claude :** `get_session` puis le `native_id`. S'il manque, ou si la ligne est absente (`NotFound`), elle est ignorée avec `no conversation id`. Sinon, `resume_session` est appelée, et l'erreur qu'elle lève devient la raison de l'écart.
  3. **Session Bash :** une session Bash vivante dans le même dossier résolu (`resolved`, `meute.core.paths`) donne `already running`. Sinon, `launch_bash(BashLaunch(cwd, title, repo_id))` est appelée.
  4. **Dossier disparu :** il donne `folder not found: <shown_path>`. Il est vérifié avant toute tentative de lancement.
  5. **Erreurs attrapées :** toute `MeuteError`, et les `ENVIRONMENT_ERRORS` traduites, deviennent une session ignorée avec leur message. Les sessions suivantes continuent.
  6. **Session affichée :** à la fin, `show_session` reçoit la session marquée `displayed`. Pour une Bash, c'est la nouvelle session. Elle doit avoir été rouverte, ou tourner déjà. Une erreur à ce stade est ignorée, et le compte rendu reste celui de la réouverture.

- [ ] **Étape 1 : écrire les tests, qui doivent échouer** (sandbox, faux `claude`).
  - Chaque ligne du tableau de la conception est couverte.
  - **Point de vigilance 3 :** rouvrir deux fois de suite donne `reopened 0 · skipped N` au second passage, avec `already running` pour toutes les sessions.
  - **Point de vigilance 2 :** un état dont une entrée a été écrite à la main en SQL avec un `agent` inconnu s'ouvre avec les autres entrées.
  - La session affichée est remise dans la zone principale.
  - Un `claude` absent fait échouer la reprise de la session Claude, et la session Bash est quand même rouverte.
- [ ] **Étape 2 : vérifier l'échec.**
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète, puis commit** `git commit -m "feat: reopen a saved state"`

---

### Task 6 : commandes `meute state`

**Fichiers :**
- Créer : `src/meute/cli/state_commands.py`, `tests/test_cli_state.py`
- Modifier : `src/meute/cli/__init__.py` (la sous-application `state`)

**Interfaces :**
- **`save [nom]`.** Elle capture comme le tableau : `load_board_data`, puis `board_session_order` et `capture`. Sans nom, elle prend `stamp_name(local_now(ctx))`. Elle répond `Saved: <nom> (<n> sessions)`, avec `1 session` au singulier.
- **`list [--json]`.** Une ligne par état, produite par `state_line`.
- **`open <nom>`.** Elle passe par `get_state`, puis `reopen_state`, et affiche les lignes de `reopen_text`. Le code de sortie est 0, et 1 avec `no saved state named <nom>`.
- **`rm <nom> [--yes]`.** Elle passe par `confirmed` (`cli/confirm.py`) avec `Remove saved state "<nom>"? [y/N]`, puis répond `Removed: <nom>`.
- **Affichage.** Toute donnée affichée passe par `printable`.

- [ ] **Étape 1 : écrire les tests, qui doivent échouer.**
  - Chaque commande, avec ses textes exacts et des instantanés pour `list` (texte et JSON).
  - `save` sans session vivante donne `Saved: <nom> (0 sessions)`.
  - **Point de vigilance 4 :** `save $'a\x1b[2Jb'` enregistre un nom affiché proprement.
  - `rm` sans confirmation ne supprime rien.
  - `open` sur un nom inconnu sort avec le code 1.
- [ ] **Étape 2 : vérifier l'échec.**
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète, puis commit** `git commit -m "feat: meute state save, list, open and rm"`

---

### Task 7 : `S` et `O` dans le tableau

**Fichiers :**
- Créer :
  - `src/meute/tui/saved_states_panel.py` ;
  - `src/meute/cli/state_actions.py`, qui sert `SaveState` et `ReopenState` pour le backend ;
  - `tests/test_tui_saved_states.py`.
- Modifier :
  - `src/meute/core/board_actions.py` : `SaveState()` et `ReopenState(name: str)` ;
  - `src/meute/cli/board_backend.py` ;
  - `src/meute/tui/sessions_tab.py` (décision 5) ;
  - `src/meute/tui/board_workers.py` : `reopen(name)` et `is_reopening()` ;
  - `src/meute/core/board_view.py` : `KEYS_HELP` (exception n° 29).

**Interfaces :**
- **`S`.** Elle exécute `SaveState()`. Le backend prend `stamp_name`, capture la dernière donnée lue, et sauve. Le pied affiche `state saved: <nom>`.
- **`O`.** Elle ouvre le panneau à partir de `data.saved_states`.
  - `↑` et `↓` déplacent la sélection, `Entrée` lance `BoardWorkers.reopen(name)`, et toute autre touche ferme le panneau.
  - Le panneau s'affiche au-dessus du pied, sur le modèle du formulaire `N`. Il montre une ligne par état, produite par `state_line`, ou `no saved state`.
  - Une relecture garde le nom sélectionné.
- **Pendant la réouverture.** Le pied affiche `reopening <nom>…`, puis la ligne de compte de `reopen_text`. Un second `Entrée` pendant ce temps est ignoré.
- **Questions déjà ouvertes (point de vigilance 5).** Une question ouverte (stop, close, removal) garde la main : `O` et `S` sont ignorées tant qu'elle est en attente.

- [ ] **Étape 1 : écrire les tests, qui doivent échouer** (`Pilot`, avec un faux backend qui enregistre les actions).
  - `S` envoie `SaveState()` et affiche le texte de confirmation.
  - La liste montre `last` en tête, puis les autres états.
  - Les touches `↑`, `↓` et `Entrée` envoient `ReopenState`. `Échap` ferme le panneau.
  - Sans état, le panneau affiche `no saved state`.
  - Le texte `reopening …` s'affiche, puis le compte rendu.
  - Un second `Entrée` est ignoré.
  - **Point de vigilance 5 :** `O` pendant une question `Stop "…"?` ne fait rien.
  - Des instantanés SVG en largeur normale et étroite.
- [ ] **Étape 2 : vérifier l'échec**, puis adapter les tests de l'exception n° 29.
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète, puis commit** `git commit -m "feat(tui): S saves and O reopens a saved state"`

---

### Task 8 : documentation, mutation, essai, relectures et PR

**Fichiers :**
- Modifier :
  - `README.md` : `S`, `O`, `meute state`, `meute session recent` et `resume`, et `recent_days` ;
  - la spécification générale : retirer « Reste au plan 6 » au § 6.5, et faire renvoyer le § 6.6 à la conception ;
  - la feuille de route : 6b fait, et « Reports issus du plan 6b » ;
  - la conception : « Écarts constatés à la réalisation » ;
  - `pyproject.toml` : la sélection de mutmut gagne les tests du cœur de ce plan.
- Créer : `docs/dev/mutants/2026-plan-6b-python.md`

- [ ] **Étape 1 : la documentation.**
- [ ] **Étape 2 : la mutation.** Lancer `rm -rf mutants && uv run mutmut run --max-children 4`, puis `uv run mutmut results`. Tuer les survivants utiles dans `tests/test_mutants_plan6b.py`, et justifier les autres.
- [ ] **Étape 3 : l'essai scripté** (serveur tmux jetable, faux `claude`, `HOME` et `XDG_*` épinglés). Il enchaîne :
  1. deux sessions Claude et une Bash, puis `S` et `meute state list` ;
  2. `x` sur tout : `last` est gardé ;
  3. `kill-server` du serveur jetable, puis un nouveau tableau, puis `O`, `last` et `Entrée` : tout revient, avec la session affichée ;
  4. `meute state open` une seconde fois : tout est `already running` ;
  5. `meute session recent`, puis `meute session resume`.
- [ ] **Étape 4 : `/simplify`, puis `/security-review`** sur toute la branche. Appliquer les constats, puis faire une vérification complète.
- [ ] **Étape 5 : commit, push, puis la PR**, en anglais et assignée à `gaetinux`. Elle liste les exceptions n° 29 et n° 30, les écarts, les limites et les essais manuels.
