# meute — Plan 4c Python : lancement depuis le tableau — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Objectif :** `n` relance le type habituel du dépôt, `N` ouvre un formulaire de lancement au-dessus du pied, `r` reprend une session Claude terminée (`claude --resume`), et les panneaux orphelins peuvent être affichés, adoptés ou fermés.

**Architecture :** comme aux plans 4 et 4b, tout ce qui se décide et s'affiche se calcule dans `meute.core` (règle du dernier type, état et transitions du formulaire, cible de la reprise, adoption d'un orphelin) ; `meute.tui` dessine et transmet les touches ; `meute.cli` exécute les actions (tmux, base) dans le backend, les actions lentes dans `BoardWorkers`.

**Stack technique :** existante (Python 3.13, uv, Typer, Textual 8.2, `pytest-textual-snapshot`, `syrupy`, `hypothesis`, `mutmut`) ; aucune dépendance nouvelle ; tmux ≥ 3.2 (`respawn-pane -k -e`).

**Spécification :** `docs/superpowers/specs/2026-10-21-meute-lancement-tableau-design.md` (conception du 4c) ; `docs/superpowers/specs/2026-10-15-meute-design.md`, § 5.4, 6.2 à 6.5. Guide : `docs/dev/developpement-assiste-par-ia.md`.

**Prérequis :** plan 4b mergé (PR #11). Branche : `feat/plan-4c-python` (déjà créée sur `main` à jour, porte la conception).

## Décisions de conception (à relire)

1. **Pas d'action `Launch` unique.** La conception proposait `Launch` à la place de `LaunchBash` et `LaunchClaude` ; on garde ces deux actions et on leur ajoute des champs facultatifs (`title` pour les deux ; `task_id` et `permission_mode` pour Claude). Même effet, et les tests existants qui les construisent restent valables.
2. **Dernier type d'un dépôt** : `BoardData.last_agents` (lu en base, toutes sessions) ; à défaut, la session la plus récente du dépôt parmi `sessions` et `ended` du tableau ; à défaut, Claude. Une session sans dépôt relance son propre type.
3. **Pied inchangé** (`FOOTER` reste `↑↓ select · Enter show · c/n new · x stop · ? keys`) : c'est l'aide `?` qui dit ce que fait `n`. Sur un orphelin, le pied devient `Enter show · a adopt · x close`. Écart à la conception, plus sobre, et sans nouvelle exception sur `FOOTER`.
4. **Détail des orphelins lu à part** : `PANE_FORMAT` ne change pas ; pour chaque panneau orphelin seulement, un `display-message -p -t <pane> "#{pane_current_command}\t#{pane_current_path}"` (comme `_unsettled`). Les orphelins sont rares, et le format des huit champs reste stable.
5. **`meute session list --json`** garde `"orphans"` en liste d'identifiants (`meute_id`), et la sortie texte `orphan: <id>` ne change pas.
6. **Formulaire sans widget de saisie Textual** : un `Static` redessiné à partir de `form_lines` ; le texte se tape à la fin du champ (pas de curseur mobile), `Backspace` efface le dernier caractère, un collage (`events.Paste`) est ajouté après `one_line`. Tout l'état vit dans le cœur.
7. **Projet d'un dépôt** (tâches proposées par le formulaire) : le projet lié par `project_repos` (le plus petit identifiant s'il y en a plusieurs), à défaut le projet qui porte le nom du dépôt (comme `session_project`), à défaut aucun (Task : `none` seulement).
8. **Dossier saisi** : `~` est développé (`expanduser`), les espaces de début et de fin sont retirés, le chemin doit être absolu (`folder must be absolute: <texte>`), puis exister (`folder not found: <texte>`, message de `resolve_folder`).

## Contraintes globales

**Hérité des plans 1 à 4b (inchangé)**
- Frontières d'imports (import-linter) : `meute.core`, `meute.tmux`, `meute.git` stdlib seulement ; `meute.tui` : `meute.core` et `textual` ; seul `meute.cli` assemble.
- Dataclasses gelées, `match` exhaustif terminé par `assert_never`, pas d'`Any`/`cast`/`assert` hors tests, docstrings sur le public de `meute.core`, fichiers de moins de 300 lignes (`board_view.py`, `sessions_view_cards.py` et `board.py` en sont près : les découpages prévus sont dans les tâches), exceptions de lint précises avec ` — raison`.
- Interface en anglais, textes de ce plan copiés mot pour mot ; toute donnée venue de la base, de tmux, de Claude ou de l'utilisateur passe par `printable` (ou `one_line`) avant affichage ; Textual l'affiche avec `Content`, jamais en balisage ; tout argument passé à tmux passe par `Tmux.run` (qui applique `literal_word`).
- Tests tmux sur serveurs jetables seulement (`tmux_server`, `sandbox`) ; aucun test automatique n'appelle le vrai `claude` ; jamais le serveur `meute` ni le tmux `default` de l'utilisateur.
- Le tableau ne bloque jamais sa boucle : reprise, adoption et fermeture tournent dans `BoardWorkers` avec leur propre connexion SQLite, comme l'arrêt.

**Qualité et workflow**
- TDD strict. Ne jamais modifier, supprimer ni désactiver un test existant. **Seules exceptions autorisées par ce plan** (numérotation continue avec le plan 4b), chacune relue et signalée dans le commit et la PR :
  - **n° 20** (Task 2) : `tests/test_board_view.py` et `tests/test_mutants_plan4.py` appellent `new_action(entry, data)` avec les données qu'ils construisent déjà ; l'attente `new_action(RepoEntry(repo=_REPO_2)) == LaunchBash(…)` devient `LaunchClaude(cwd=_REPO_2.path, repo_id=RepoId(2))` (un dépôt sans session lance Claude, § 6.4) ; `tests/test_tui_board.py` : les attentes des tests qui pressent `n` sur un dépôt sans session, même changement. Les autres assertions ne changent pas.
  - **n° 21** (Tasks 2, 4 et 8) : `tests/test_tui_keys_help.py` et les instantanés qui montrent l'aide `?` suivent les nouvelles lignes de `KEYS_HELP` ; `tests/test_tui_ended_enter.py` seulement si un de ses tests montre une session Claude terminée (le texte Bash ne change pas).
  - **n° 22** (Task 5) : `tests/support.py`, `tests/test_tui_board.py`, `tests/test_mutants_plan4.py` construisent `orphans` avec des `Orphan(…)` au lieu de chaînes (même identifiant, même rendu attendu hors instantanés) ; instantanés de la section « Orphans » régénérés et relus.
- Instantanés relus ligne par ligne ; jamais `--snapshot-update` à l'aveugle.
- Chaque tâche se termine par `bash scripts/verify.sh` et un commit ; `/simplify` puis `/security-review` en fin de plan. Commits en anglais terminés par `Co-Authored-By: Claude …`, sans ligne `Claude-Session`. Une PR à la fin, **titre et corps en anglais**, assignée à `gaetinux`.

## Hors périmètre

- Champ worktree de `N`, recommandation de worktree, liste « recent sessions to resume », états sauvegardés : plan 6.
- Vue Sessions sans base (§ 16), largeur en cellules, `paste-buffer -r`, suppression de `quota_lines` / `details_lines` : plus tard (plan 6 ou 4d).

## Points de vigilance (Review Focus)

1. **Reprise d'une conversation que Claude ne retrouve plus** (transcript effacé, `native_id` d'une autre machine) : `claude --resume` s'arrête aussitôt. Le panneau mort reste, la relecture remet la session en `Exited(code)`, rien ne boucle, et un nouvel `r` est possible. Test au Task 3 (faux `claude` en mode `exit`).
2. **Données d'orphelin hostiles** : `@meute_id` qui n'est pas un identifiant (`x;y`, 37 caractères, caractères de contrôle), dossier finissant par `;` ou contenant un saut de ligne, commande `claude\x1b[2J` : rien n'est écrit en base sans identifiant valide, l'affichage passe par `printable`, la fermeture fonctionne quand même. Tests au Task 5 et au Task 6.
3. **Touches répétées** : `r` deux fois sur la même session, `a` deux fois sur le même orphelin, `x` `y` puis `a` pendant la fermeture : une seule action part, aucune erreur visible. Tests au Task 4 et au Task 6.
4. **Relecture du tableau pendant que le formulaire est ouvert** (toutes les 2 s) : les champs saisis, le champ courant et l'avertissement ne bougent pas ; un dépôt supprimé entre-temps donne une erreur lisible au lancement, formulaire gardé. Test au Task 8.
5. **Dossier saisi à la main** : `~/x`, `  /tmp  `, `relative/path`, `/n'existe/pas`, un dossier avec `;` final : les règles de la décision 8, et le lancement reçoit le chemin exact. Tests au Task 7 (cœur) et au Task 8 (lancement).

---

### Task 1 : spike S10 (reprise avec le vrai Claude)

**Fichiers :**
- Créer : `docs/superpowers/spikes/2026-10-21-spike-s10.md`

**S10 (accord explicite de l'auteur requis avant de lancer le vrai `claude`)** : serveur tmux jetable (`-L meute-spike-s10`), `HOME` réel (authentification), un dossier jetable approuvé par l'auteur. Lancer `claude --settings <réglages avec un hook SessionStart qui écrit son JSON d'entrée et $MEUTE_SESSION dans un fichier> --session-id <uuid> --permission-mode manual --name=s10` avec `MEUTE_SESSION=<uuid>`, envoyer un message court, quitter (`C-c` deux fois). Puis, dans un nouveau panneau, `claude --settings <mêmes réglages> --resume <uuid> --permission-mode manual --name=s10` avec le même `MEUTE_SESSION`. Noter : le hook `SessionStart` arrive-t-il, avec quel `source` et quel `session_id` ? `MEUTE_SESSION` est-il transmis ? Les options sont-elles acceptées ensemble ? La conversation est-elle bien reprise ? Essayer aussi `respawn-pane -k` sur le panneau mort du premier lancement. Tuer le serveur jetable.

- [ ] **Étape 1 : demander l'accord ; S10 s'il est donné** (sinon, noter « S10 reporté » : le Task 3 suit la documentation de Claude Code, même `session_id` attendu, et accepte un nouveau `native_id` via `rebinds`).
- [ ] **Étape 2 : compte rendu** (commandes, sorties, décision) ; reporter au Task 3 la forme exacte de la commande et la valeur de `source`.
- [ ] **Étape 3 : commit** `git commit -m "docs: spike S10 (claude --resume under meute)"`

---

### Task 2 : `n` lance le dernier type du dépôt

**Fichiers :**
- Créer : `src/meute/core/board_actions.py` (les dataclasses d'actions et `BoardAction` / `TaskAction`, déplacées de `board_view.py`, qui les réimporte pour que les imports existants restent valables), `src/meute/core/last_agent.py`
- Modifier : `src/meute/core/board_view.py` (`new_action`, `claude_action`, `BoardData.last_agents`, `KEYS_HELP`), `src/meute/core/db/sessions.py` (`last_agent_by_repo`), `src/meute/cli/board_data.py`, `src/meute/cli/board_backend.py` (champs nouveaux de `LaunchBash` / `LaunchClaude` transmis)
- Test : `tests/test_last_agent.py`, `tests/test_db_last_agent.py` ; exception n° 20

**Interfaces :**
- `LaunchBash(cwd, repo_id, title: str | None = None)` ; `LaunchClaude(cwd, repo_id, title: str | None = None, task_id: TaskId | None = None, permission_mode: str | None = None)`. Le backend les passe à `BashLaunch` / `ClaudeLaunch`.
- `last_agent_by_repo(db: Database) -> dict[RepoId, AgentKind]` : pour chaque `repo_id` non nul, l'`agent` de la session au plus grand `(created_at, id)`, une seule requête SQL sans paramètre utilisateur.
- `BoardData.last_agents: Mapping[RepoId, AgentKind]` (vide par défaut), rempli par `load_board_data`.
- `last_agent(data: BoardData, repo_id: RepoId | None, own: AgentKind | None) -> AgentKind` (`core/last_agent.py`) : décision 2 ; `repo_id` nul → `own` s'il est donné, sinon `AgentKind.CLAUDE`.
- `new_action(entry: BoardEntry, data: BoardData) -> LaunchBash | LaunchClaude` : même dossier et dépôt qu'aujourd'hui, type de `last_agent`. **Signature changée** : le seul appelant est `SessionsTab._act` ; les tests qui l'appellent sans `data` sont couverts par l'exception n° 20 (ils passent `board_data()` ou les données qu'ils construisent déjà).
- `KEYS_HELP`, deuxième ligne : `c new Claude session · n new (this repository's last type) · x stop` (exception n° 21 pour `test_tui_keys_help.py`).

- [ ] **Étape 1 : tests qui échouent** : `last_agent_by_repo` (deux dépôts, sessions Bash puis Claude, la plus récente gagne ; égalité de `created_at` départagée par l'`id` ; dépôt nul ignoré) ; `last_agent` (base prioritaire sur les sessions du tableau, sessions du tableau à défaut, Claude à défaut, `own` pour une session sans dépôt) ; `new_action` sur dépôt sans session → `LaunchClaude`, sur session Bash d'un dépôt dont la dernière session est Claude → `LaunchClaude` dans le dossier de la session ; pilote : `n` sur un dépôt dont `last_agents` dit Bash → `LaunchBash`.
- [ ] **Étape 2 : échec. Étape 3 : implémenter**, appliquer l'exception n° 20 et la relire.
- [ ] **Étape 4 : vérification complète ; commit** `git commit -m "feat: n launches the repository's last session type"`

---

### Task 3 : reprise d'une session Claude (backend) **[sécurité]**

**Fichiers :**
- Créer : `src/meute/cli/session_resume.py`
- Modifier : `src/meute/claude/launch.py` (`claude_argv(..., resume: bool = False)`), `src/meute/tmux/panes.py` (`respawn_window`), `src/meute/core/db/sessions.py` (`reopen_session`), `src/meute/cli/session_launch.py` (`session_spawn` partagé), `tests/fake_claude/claude` (accepte `--resume <id>` à la place de `--session-id`)
- Test : `tests/test_session_resume.py`, `tests/test_db_reopen.py`, `tests/test_tmux_respawn.py`

**Interfaces :**
- `claude_argv(*, claude, settings, session_id, permission_mode, title, resume: bool = False)` : avec `resume`, `--resume <session_id>` remplace `--session-id <session_id>` (forme confirmée ou corrigée par le Task 1) ; le reste est identique.
- `respawn_window(tmux: Tmux, pane: PaneId, spawn: Spawn) -> PaneId` : `respawn-pane -k -t <pane> -c <cwd> -e KEY=VAL… -- <commande dans le dossier>` (même enveloppe `_in_folder`), puis les `pane_options` ; renvoie `pane`.
- `reopen_session(db: Database, session_id: SessionId) -> Session` : dans une transaction, refuse une session vivante (`InvalidInput(f'"{title}" is still running')`), sinon `state = 'unknown'`, `exit_code = NULL`, `ended_at = NULL`, `last_activity_at = now`. `NotFound` si elle n'existe pas.
- `resume_session(ctx: CliContext, env: TmuxEnv, session_id: SessionId, environ: Mapping[str, str]) -> Session` : session Claude terminée avec `native_id` (sinon `InvalidInput` avec les textes de la conception), dossier par `resolve_folder`, `claude` par `find_claude` (`CLAUDE_MISSING`), mode = dernier `permission_mode` connu (`get_claude_details`) s'il est dans `PERMISSION_MODES`, sinon celui de la configuration ; nouveaux réglages `write_settings` ; panneau mort de la session → `respawn_window`, sinon `spawn_window` dans `meute-bg` ; puis `reopen_session`. Si `reopen_session` échoue, le panneau lancé est tué (comme `spawn_and_record`) ; si tmux échoue, rien n'est écrit.

- [ ] **Étape 1 : tests qui échouent** : `claude_argv` avec `resume` (argv exact) ; `reopen_session` (terminée → vivante, champs effacés ; vivante → refus, rien écrit ; inconnue → `NotFound`) ; `respawn_window` sur serveur jetable : panneau mort relancé, même `pane_id`, options `@meute_id` et `remain-on-exit` présentes, dossier finissant par `;` reçu tel quel ; `resume_session` avec le faux `claude` : sans panneau → nouvelle fenêtre de `meute-bg`, arguments enregistrés (`MEUTE_FAKE_CLAUDE_ARGS`) avec `--resume <native_id>` et le mode d'origine, session `unknown` puis confirmée par le `SessionStart` du faux `claude` ; avec panneau mort → même `pane_id` ; session Bash, session sans `native_id`, session vivante → `InvalidInput`, rien lancé ; dossier supprimé → `InvalidInput`, état inchangé ; **point de vigilance 1** : faux `claude` en mode `exit` → après relecture, session `Exited`, un second `resume_session` repart.
- [ ] **Étape 2 : échec. Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète ; commit** `git commit -m "feat: resume an ended Claude session with claude --resume"`

---

### Task 4 : touche `r` dans le tableau

**Fichiers :**
- Modifier : `src/meute/core/board_actions.py` (`ResumeSession`), `src/meute/core/board_view.py` (`resume_target`, `ended_text`, `resuming_text`, `KEYS_HELP`), `src/meute/tui/sessions_tab.py`, `src/meute/tui/board_workers.py`, `src/meute/cli/board_backend.py`
- Test : `tests/test_resume_target.py`, `tests/test_tui_resume.py` ; exception n° 21

**Interfaces :**
- `ResumeSession(session_id: SessionId)`.
- `resume_target(entry: BoardEntry, details: Mapping[SessionId, ClaudeDetails]) -> Session | str` : la session à reprendre, sinon le texte du pied : `only Claude sessions resume` ; `"{title}" is still running` ; `"{title}" cannot be resumed: Claude never confirmed its id` (titres par `printable`). Un dépôt → `only Claude sessions resume`.
- `ended_text(title: str, agent: AgentKind = AgentKind.BASH) -> str` : Claude → `"{title}" has ended: r resumes · c starts a new session` ; Bash (défaut, donc les appels existants à un argument gardent leur résultat) → le texte actuel `"{title}" has ended: c starts a new Claude session here`. `ended_notice` passe l'agent de la session.
- `resuming_text(title: str) -> str` : `Resuming "{title}"…`.
- `BoardWorkers.resume(session: Session)` : comme `stop`, ignoré si cette reprise tourne déjà ; le pied affiche `resuming_text` pendant ce temps. Le backend exécute `resume_session` sur sa propre connexion, puis `show_session`.
- `KEYS_HELP` gagne `r resume an ended Claude session` sur la ligne de `x stop`, en gardant les lignes sous 72 colonnes.

- [ ] **Étape 1 : tests qui échouent** : `resume_target` (les quatre cas) ; pilote et faux backend : `r` sur une session Claude terminée envoie `ResumeSession` une fois, **point de vigilance 3** : `r` `r` → une seule action ; `r` sur une session vivante → texte dans le pied, rien envoyé ; `Entrée` sur une session Claude terminée sans panneau → nouveau `ended_text` ; erreur du backend → `Error: …` dans le pied.
- [ ] **Étape 2 : échec. Étape 3 : implémenter**, appliquer l'exception n° 21 et la relire.
- [ ] **Étape 4 : vérification complète ; commit** `git commit -m "feat(tui): r resumes an ended Claude session"`

---

### Task 5 : orphelins décrits et sélectionnables **[sécurité]**

**Fichiers :**
- Créer : `src/meute/core/orphans.py`, `src/meute/core/sessions_view_bottom.py` (`_section`, `_bottom_blocks` et les lignes du bas, déplacés de `sessions_view_cards.py`)
- Modifier : `src/meute/cli/session_refresh.py` (`Snapshot.orphans`), `src/meute/cli/session_commands.py` (JSON et texte inchangés, décision 5), `src/meute/core/board_view.py` (`BoardData.orphans`, `OrphanEntry`), `src/meute/core/sessions_view_cards.py` (`OrphanLine`), `src/meute/core/sessions_view.py`, `src/meute/core/board_sessions.py`, `src/meute/tui/sessions_tab.py` (clic)
- Test : `tests/test_orphans.py`, `tests/test_sessions_orphans.py` ; exception n° 22

**Interfaces :**
- `Orphan(meute_id: str, pane_id: str, command: str, cwd: str, dead: bool)` (`core/orphans.py`).
- `orphan_details(tmux: Tmux, pane: PaneId) -> tuple[str, str] | None` (`cli/session_refresh.py`) : décision 4 ; `None` si le panneau a disparu (`CommandFailed`) ; une ligne sans tabulation → commande seule, dossier vide.
- `Snapshot.orphans` et `BoardData.orphans` : `tuple[Orphan, ...]`, dans l'ordre de `Reconciliation.orphans` (inchangé) ; un panneau disparu entre les deux lectures est omis.
- `orphan_line(orphan: Orphan, home: Path | None) -> str` : `? {command}  {cwd abrégé en ~}  orphan` (`dead` à la place de `orphan` pour un panneau mort), chaque partie par `printable`, ajusté par `fit`.
- `OrphanLine(meute_id: str, spans: StyledLine)` dans `ViewLine`, sélectionnable (`line_key` → `orphan:{meute_id}`) ; `OrphanEntry(orphan: Orphan)` dans `BoardEntry`. `new_action`, `claude_action`, `stop_target`, `resume_target` et `ended_notice` prennent `LaunchEntry = SessionEntry | RepoEntry` (nouvel alias) : `SessionsTab._act` traite un `OrphanEntry` avant eux — `Entrée` → `ShowPane` (Task 6 ; au Task 5, rien), `c`, `n`, `r` → pied `orphan pane: Enter show · a adopt · x close`.
- `sessions_view_cards.py` repasse sous 280 lignes grâce au déplacement.

- [ ] **Étape 1 : tests qui échouent** : `orphan_details` sur serveur jetable (panneau `sleep` marqué à la main avec `@meute_id`, dossier finissant par `;`) ; `refresh` renvoie l'`Orphan` complet, et omet un panneau tué entre-temps ; `orphan_line` (vivant, mort, home abrégé) ; vue : la ligne est sélectionnable, la sélection la garde après relecture, la section se replie ; **point de vigilance 2** : `@meute_id` `x\x1b[2Jy`, commande `claude\x1b[2J`, dossier avec saut de ligne → une seule ligne sans caractère de contrôle.
- [ ] **Étape 2 : échec. Étape 3 : implémenter**, appliquer l'exception n° 22 et relire les instantanés.
- [ ] **Étape 4 : vérification complète ; commit** `git commit -m "feat: orphan panes are described and selectable"`

---

### Task 6 : afficher, adopter et fermer un orphelin **[sécurité]**

**Fichiers :**
- Créer : `src/meute/cli/orphan_actions.py`
- Modifier : `src/meute/core/orphans.py` (`adoption`), `src/meute/core/board_actions.py` (`ShowPane`, `AdoptOrphan`, `CloseOrphan`), `src/meute/core/board_view.py` (textes), `src/meute/cli/session_show.py` (`show_pane` extrait de `show_session`), `src/meute/cli/session_stop.py` (`interrupt_and_kill` extrait de `_interrupt` / `_kill`), `src/meute/cli/board_backend.py`, `src/meute/tui/board_workers.py`, `src/meute/tui/sessions_tab.py`
- Test : `tests/test_orphan_adoption.py`, `tests/test_orphan_actions.py`, `tests/test_tui_orphans.py`

**Interfaces :**
- `adoption(orphan: Orphan, repos: Sequence[Repo]) -> NewSession | str` : refus `not a meute id: only x closes it` si `parse_session_id` échoue ; `dead pane: only x closes it` pour un panneau mort ; sinon `NewSession(id, agent=CLAUDE si command == "claude" sinon BASH, title=nom du dossier (ou "orphan" si vide), cwd, state=Unknown() pour Claude / Running() pour Bash, repo_id=dépôt connu dont le chemin contient le dossier, le plus long)`.
- `ShowPane(pane_id: str)`, `AdoptOrphan(orphan: Orphan)`, `CloseOrphan(meute_id: str, agent: AgentKind)`.
- `show_pane(env: TmuxEnv, pane: PaneInfo) -> None` : la partie tmux de `show_session` (zoom, échange avec la zone principale, accueil tué, focus) ; `show_session` l'appelle puis publie la ligne d'état comme aujourd'hui. Un panneau mort → `InvalidInput("dead pane: nothing to show")`.
- `adopt_orphan(ctx: CliContext, orphan: Orphan) -> Session | None` : `adoption` (refus → `InvalidInput`) ; un `id` déjà en base → `None` sans erreur ; sinon `create_session`.
- `interrupt_and_kill(env: TmuxEnv, meute_id: str, grace: float, *, twice: bool) -> PaneInfo | None` : la séquence de l'arrêt (`C-c`, deux fois pour Claude, puis `kill-pane`) ; `stop_session` l'utilise ; `close_orphan(env, meute_id, agent)` aussi, sans rien écrire en base. Un panneau déjà disparu ne fait rien.
- Touches sur un orphelin : `Entrée` → `ShowPane` ; `a` → `AdoptOrphan` (dans un worker, ignoré si cette adoption tourne) ; `x` → `Close orphan pane "{command}"? y: yes · any other key: no`, puis `y` → `CloseOrphan` dans un worker, pied `Closing "{command}"…` ; refus d'`adoption` → son texte dans le pied. Le pied sur un orphelin : `Enter show · a adopt · x close`.

- [ ] **Étape 1 : tests qui échouent** : `adoption` (Claude, Bash, dépôt le plus long, aucun dépôt, dossier vide, id invalide, mort) ; sur serveur jetable : `adopt_orphan` crée la session, la relecture suivante ne la liste plus comme orpheline et la reconnaît vivante ; deux adoptions → la seconde renvoie `None` ; `close_orphan` tue le panneau d'un `sleep`, rien en base ; `show_pane` met l'orphelin dans la zone principale ; `show_session` garde son comportement (tests existants inchangés) ; pilote : les trois touches, la confirmation, **point de vigilance 3** (`a` `a` → une action ; `a` pendant une fermeture → ignoré) ; **point de vigilance 2** : `x` `y` sur un orphelin à l'id invalide ferme le panneau.
- [ ] **Étape 2 : échec. Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète ; commit** `git commit -m "feat: show, adopt or close an orphan pane"`

---

### Task 7 : formulaire de lancement (cœur)

**Fichiers :**
- Créer : `src/meute/core/launch_form.py`, `src/meute/core/launch_form_view.py`
- Modifier : `src/meute/core/board_view.py` (`BoardData.repo_projects`), `src/meute/core/db/repos.py` (`repo_project_links`), `src/meute/cli/board_data.py`
- Test : `tests/test_launch_form.py`, `tests/test_launch_form_view.py`, `tests/test_db_repo_links.py`

**Interfaces :**
- `FormField` : `Enum` `TYPE, REPO, FOLDER, TITLE, TASK, MODE` ; `TASK` et `MODE` sautés pour Bash.
- `LaunchForm` (figée) : `agent: AgentKind`, `repos: tuple[Repo, ...]` (présélectionné en tête puis par nom), `repo: int | None` (index, `None` = `none`), `folder: str`, `title: str`, `tasks: tuple[Task, ...]`, `task: int | None`, `modes: tuple[str, ...]`, `mode: int`, `field: FormField`, `busy: frozenset[Path]` (dossiers résolus des autres sessions vivantes), `error: str | None`.
- `open_form(data: BoardData, entry: BoardEntry | None, *, default_mode: str, now: datetime) -> LaunchForm` : valeurs préremplies de la conception ; `modes` = `PERMISSION_MODES` triés avec `default_mode` en tête ; tâches = tâches ouvertes du projet du dépôt (décision 7, `BoardData.repo_projects`), dans l'ordre de `sort_for_display`.
- `move(form, step: int) -> LaunchForm` (champ suivant ou précédent, en boucle) ; `choose(form, step: int, data: BoardData, now: datetime) -> LaunchForm` (sur TYPE, REPO, TASK, MODE ; changer de dépôt remplace `folder` par son chemin, sauf `none`, et recalcule `tasks` avec `task = None`) ; `type_text(form, text: str) -> LaunchForm` et `erase(form) -> LaunchForm` (sur FOLDER et TITLE seulement, `one_line` appliqué) ; chaque transition efface `error`.
- `form_action(form: LaunchForm, home: Path) -> LaunchBash | LaunchClaude | str` : décision 8 sur le dossier (texte d'erreur sinon ; l'existence est vérifiée au lancement par `resolve_folder`) ; titre vide → `None` ; Claude : `task_id`, `permission_mode`.
- `shares_folder(form: LaunchForm, home: Path) -> bool` : le dossier développé et résolu est dans `busy`.
- `form_lines(form: LaunchForm, *, home: Path, width: int) -> list[StyledLine]` (`launch_form_view.py`) : la maquette de la conception, mot pour mot — titre `── New session ` complété de `─` (`ACCENT`), libellés sur 10 colonnes (`Type`, `Repo`, `Folder`, `Title`, `Task`, `Mode`), choix entre `◂ ` et ` ▸`, champ courant en `TITLE`, modes risqués (`RISKY_MODES`) en `WARN`, tâche `#{id} {title}` ajustée, `⚠ another live session works in this folder` (`WARN`) si `shares_folder`, `Error: {error}` (`HIGH`) si `error`, puis `Enter launch · Tab next · ←→ choose · Esc cancel` (`DIM`). Tout texte venu des données par `printable`.
- `repo_project_links(db: Database) -> dict[RepoId, ProjectId]` : le plus petit `project_id` de `project_repos` par dépôt ; `BoardData.repo_projects` ajoute le repli par nom (décision 7) dans `load_board_data`.

- [ ] **Étape 1 : tests qui échouent** : préremplissage sur une session, un dépôt, rien ; `choose` sur chaque champ, changement de dépôt ; Bash saute Task et Mode ; **point de vigilance 5** : `~/x`, `  /tmp  `, `relative/path` (erreur exacte), chemin vide ; `form_action` Claude et Bash ; `shares_folder` ; propriété `hypothesis` : toute suite de `move` / `choose` / `type_text` / `erase` garde des index valides et ne lève jamais ; instantanés `syrupy` de `form_lines` (Claude avec avertissement, Bash, erreur) à 72 colonnes, et à 60 colonnes sans dépassement.
- [ ] **Étape 2 : échec. Étape 3 : implémenter.** Sélection mutmut.
- [ ] **Étape 4 : vérification complète ; commit** `git commit -m "feat(core): launch form state and lines"`

---

### Task 8 : formulaire `N` dans le tableau

**Fichiers :**
- Créer : `src/meute/tui/launch_form.py` (`LaunchFormPanel`, un `Static` docké au-dessus du pied)
- Modifier : `src/meute/tui/sessions_tab.py` (`N`, routage des touches), `src/meute/tui/board.py` (compose le panneau ; le garde sous 300 lignes en déplaçant le routage des saisies dans `src/meute/tui/board_input.py` si besoin), `src/meute/cli/board_backend.py`
- Test : `tests/test_tui_launch_form.py`

**Interfaces :**
- `N` dans l'onglet Sessions ouvre `open_form` sur l'entrée sélectionnée ; tant qu'il est ouvert : `tab` / `down` → `move(+1)`, `shift+tab` / `up` → `move(-1)`, `left` / `right` → `choose(∓1)`, `backspace` → `erase`, un caractère imprimable → `type_text`, `events.Paste` → `type_text`, `escape` → ferme, `enter` → `form_action` : un texte → `error` affiché, formulaire ouvert ; une action → envoyée au backend. Aucune autre touche n'atteint les contrôleurs (ni `x`, ni `q`, ni `Tab` d'onglet). Un clic ailleurs ne ferme pas le formulaire et ne lui vole pas les touches.
- Lancement réussi → formulaire fermé, nouvelle session affichée (le backend fait déjà `show_session`) ; `MeuteError` → formulaire ouvert, `error` = le message, saisie gardée.
- Relecture du tableau pendant l'ouverture : le formulaire n'est pas reconstruit ; seul `busy` est recalculé.
- `KEYS_HELP` gagne `N choose what to launch` (exception n° 21 déjà ouverte au Task 4 pour ce fichier de test).

- [ ] **Étape 1 : tests qui échouent** (pilote, faux backend) : `N`, `right` sur Type → Bash, Task et Mode disparaissent ; saisie du titre et `enter` → `LaunchBash(title=…)` ; Claude avec tâche et mode → `LaunchClaude` exact ; dossier relatif → erreur, rien envoyé ; backend qui lève `MeuteError("folder not found: /x")` → formulaire ouvert, erreur, saisie gardée ; `x`, `q`, `Tab` tapés dans le formulaire n'arrêtent, ne détachent ni ne changent d'onglet ; **point de vigilance 4** : relecture forcée pendant la saisie → champs et champ courant inchangés ; **point de vigilance 5** : dossier finissant par `;` transmis tel quel ; instantanés `pytest-textual-snapshot` du tableau avec le formulaire à 60, 72 et 100 colonnes.
- [ ] **Étape 2 : échec. Étape 3 : implémenter.** Relire les instantanés.
- [ ] **Étape 4 : vérification complète ; commit** `git commit -m "feat(tui): N opens the launch form"`

---

### Task 9 : documentation, mutation, relectures et PR

**Fichiers :**
- Modifier : `docs/superpowers/specs/2026-10-15-meute-design.md` (§ 5.4, 6.4, 6.5 : décisions 1 à 8, ce qui reste au plan 6), `docs/superpowers/specs/2026-10-21-meute-lancement-tableau-design.md` (décisions 1, 3, 4 et 5 qui l'ajustent), `docs/superpowers/plans/2026-10-15-meute-v1-roadmap.md` (4c fait, reports), `README.md` (touches `n`, `N`, `r`, `a`)
- Créer : `docs/dev/mutants/2026-plan-4c-python.md`

- [ ] **Étape 1 : mutation** : ajouter les nouveaux tests à la sélection mutmut de `pyproject.toml`, `uv run mutmut run --max-children 4`, `uv run mutmut results` ; tuer les survivants utiles dans `tests/test_mutants_plan4c.py`, justifier les autres dans le rapport.
- [ ] **Étape 2 : `/simplify` sur la branche** (src et tests, sans instantanés ni docs), puis **`/security-review`** (`respawn-pane` et sa commande, `--resume`, données d'orphelin venues de tmux, adoption en base, dossier saisi). Corriger, en TDD.
- [ ] **Étape 3 : essai scripté** sur serveur jetable avec le faux `claude` : `n` sur un dépôt neuf (Claude), `N` en Bash avec titre, `r` sur une session terminée (avec et sans panneau mort), orphelin créé à la main puis affiché, adopté, et un second fermé ; tableau des résultats dans le rapport de mutation. Liste d'essais manuels pour l'auteur (vrai Claude, vrai terminal) dans la PR.
- [ ] **Étape 4 : vérification complète ; commit** `git commit -m "docs: plan 4c mutation report, spec and roadmap"` ; pousser la branche ; PR `feat: launch, resume and adopt from the board (plan 4c)` assignée à `gaetinux`, **titre et corps en anglais**, avec les exceptions n° 20 à 22 et la liste d'essais manuels.
