# meute — Plan 4 Python : vue Sessions et interface transparente — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Objectif :** le tableau de bord devient la vraie vue Sessions (regroupement, « needs attention », quotas et projection, détail de la session sélectionnée), on passe d'une session à l'autre sans connaître tmux (souris, `M-n` / `M-N`, une touche pour se détacher), et tmux devient invisible : barre d'état meute, bordures discrètes, messages masqués.

**Architecture :** tout ce qui s'affiche se calcule dans `meute.core` (modèle de vue pur, testé en texte), Textual ne fait que dessiner et transmettre les touches et les clics. Les actions lentes (arrêt d'une session) partent dans un worker de Textual avec leur propre connexion SQLite. La configuration tmux générée porte la transparence (souris, barre d'état, bordures, raccourcis `M-n` / `M-N`) ; la barre d'état affiche une option `@meute_status` que meute met à jour.

**Stack technique :** existante (Python 3.13, uv, Typer, Textual 8.2, `pytest-textual-snapshot`, `syrupy`, `hypothesis`, `mutmut`) ; aucune dépendance nouvelle ; tmux ≥ 3.2 (3.5a en local, 3.4 en CI).

**Spécification :** `docs/superpowers/specs/2026-10-15-meute-design.md`, § 3.1 (vue Sessions, quotas), 4.5, 5.1, 5.2, 6.1, 6.5, 7.4, 10, 16, 17 ; la Task 1 y ajoute le § 5.6 « Interface transparente » (décision de l'auteur du 2026-10-18). Guide : `docs/dev/developpement-assiste-par-ia.md`. Feuille de route : `docs/superpowers/plans/2026-10-15-meute-v1-roadmap.md` (reports des plans 2 et 3).

**Prérequis :** plans 1 à 3 mergés (PR #7, #8, #9). Branche : `feat/plan-4-python`, créée depuis `main`.

## Décisions de conception (à relire)

1. **Le plan 4 de la feuille de route est coupé en deux.** Ce plan livre la vue Sessions et l'interface transparente ; la vue Tâches (§ 9.5) devient le plan 4b, rédigé après celui-ci. Les deux ensemble dépasseraient vingt tâches.
2. **Regroupement par projet, à défaut par dépôt.** Les projets ne sont créés automatiquement qu'au plan 6 ; d'ici là, une session sans projet est rangée sous le nom de son dépôt, et une session sans dépôt sous `Other`.
3. **« Needs attention »** = `PermissionRequested`, `WaitingInput` et `MaybeStuck`. Les sessions terminées n'en font pas partie (elles sont repliées, § 3.1).
4. **Un clic sur une ligne du tableau affiche la session** (comme `Entrée`) ; la souris est active partout (décision de l'auteur) : tmux transmet les clics à l'application de la zone principale, et la sélection de texte se fait avec `Shift`, ce que l'écran d'accueil dit.
5. **Se détacher** : la touche `q` du tableau (et `M-q` partout) détache le client sans rien arrêter. `ctrl+q` reste la touche de Textual qui quitte le tableau lui-même ; elle n'est plus annoncée.
6. **Arrêter une session Claude** envoie `C-c` deux fois (Claude demande une seconde pression pour sortir), puis attend la grâce de 5 s du § 6.5 ; un Bash reçoit toujours un seul `C-c`. L'arrêt tourne dans un worker : le tableau reste utilisable et affiche `Stopping "<title>"…`.
7. **L'état Git des sessions** (§ 4.5, § 11 : branche, `*`, ↑↓) reste au plan 6 avec les worktrees ; la colonne n'apparaît pas encore.

## Contraintes globales

**Hérité des plans 1 à 3 (inchangé)**
- Frontières d'imports (import-linter) : `meute.core`, `meute.tmux`, `meute.git` stdlib seulement ; `meute.tui` : `meute.core` et `textual` ; `meute.ingest` : `meute.core` seulement ; seul `meute.cli` assemble.
- Dataclasses gelées, `match` exhaustif terminé par `assert_never`, pas d'`Any`/`cast`/`assert` hors tests, docstrings sur le public de `meute.core`, fichiers de moins de 300 lignes, exceptions de lint précises avec ` — raison`.
- Interface en anglais, textes de ce plan copiés mot pour mot ; toute donnée venue de la base ou de Claude passe par `printable` avant d'être affichée (Textual l'affiche avec `Content`, jamais en balisage).
- Tests tmux sur serveurs jetables seulement (fixtures `tmux_server`, `sandbox`, `TMUX_TMPDIR` propre à chaque exécution) ; aucun test n'appelle le vrai `claude` (le faux est en tête du `PATH` du bac à sable).
- Le tableau de bord ne bloque jamais sa boucle : rien de plus lent qu'une requête SQLite ou un appel `tmux` court n'y tourne en direct.

**Qualité et workflow**
- TDD strict. Ne jamais modifier, supprimer ni désactiver un test existant. **Seules exceptions autorisées par ce plan**, chacune relue et signalée dans le commit et la PR :
  1. Task 5 : les instantanés du tableau (`tests/__snapshots__/test_tui_board/*.raw`, `tests/__snapshots__/test_board_view*.ambr`) et les tests qui fixent le texte exact de `FOOTER`, de `NO_SESSIONS` ou des titres de section sont mis à jour pour la nouvelle vue ; les tests de comportement des touches (`Entrée`, `c`, `n`, `x` puis `y`, flèches) ne changent pas et doivent passer ;
  2. Task 7 : l'instantané de la configuration tmux (`tests/__snapshots__/test_tmux_conf.ambr`) est régénéré et relu ligne par ligne contre le texte de la Task 7 ;
  3. Task 9 : `tests/test_welcome.py::test_welcome_text_uses_configured_keys` suit le nouveau texte d'accueil.
- Instantanés relus ligne par ligne ; jamais `--snapshot-update` à l'aveugle.
- Chaque tâche se termine par `bash scripts/verify.sh`, une passe de simplification et, pour les tâches **[sécurité]**, une passe de sécurité ; commits en anglais terminés par `Co-Authored-By: Claude …`, sans ligne `Claude-Session`. Une PR à la fin, assignée à `gaetinux`.

## Hors périmètre (inscrit dans la feuille de route à la Task 11)

- Vue Tâches (§ 9.5) : plan 4b.
- État Git des sessions, worktrees, reprise et « recent sessions to resume », états sauvegardés, projets créés automatiquement : plan 6.
- Actions sur les panneaux orphelins (adopter, fermer) : plan 4b, avec les actions du détail.
- MCP et contexte composé : plan 5.

## Points de vigilance (Review Focus)

1. **Clic ou touche pendant qu'un arrêt tourne.** Le worker d'arrêt ne doit ni bloquer le tableau, ni partager la connexion SQLite du fil principal (`sqlite3` refuse une connexion utilisée depuis un autre fil), ni laisser lancer un second arrêt de la même session. Test au Task 6.
2. **Peu ou pas de relevés de quota.** La projection exige au moins deux relevés de la fenêtre 5 h sur les 30 dernières minutes et une pente positive ; sinon rien n'est affiché. Un reset passé, un pourcentage qui baisse (nouveau cycle) ou des relevés au même instant ne doivent ni lever ni afficher une heure absurde. Test au Task 3.
3. **Liste qui change sous la sélection.** Un regroupement replié, un filtre « needs attention » activé ou une session qui disparaît ne doivent jamais laisser la sélection sur une ligne d'en-tête ni hors de la liste. Test au Task 4.
4. **Raccourcis globaux et tmux de l'utilisateur.** `M-n`, `M-N` et `M-q` sont configurables (`[keys]`) et validés comme les autres (`[A-Za-z0-9-]{1,20}`), car ils vont dans la configuration générée. Test au Task 7.
5. **Mode étroit.** Sous le seuil, `M-o` ne doit pas sortir le tableau du plein écran (report du plan 2) ; `Entrée` bascule vers la fenêtre de la session et `M-p` revient. Test au Task 8.

---

### Task 1 : spécification et feuille de route

**Fichiers :**
- Modifier : `docs/superpowers/specs/2026-10-15-meute-design.md` (nouveau § 5.6, précisions aux § 3.1, 5.1, 6.5, 10), `docs/superpowers/plans/2026-10-15-meute-v1-roadmap.md`

Contenu à écrire, en français, au ton de la spécification :
- **§ 5.6 Interface transparente** : souris active (clic sur une ligne du tableau = afficher la session, clic sur un panneau = focus, molette = défilement ; sélection de texte avec `Shift`) ; la barre d'état de tmux est remplacée par une ligne meute (session affichée, nombre de sessions « needs attention », quota 5 h) ; bordures réduites à une ligne discrète ; `q` dans le tableau et `M-q` partout détachent sans rien arrêter ; les messages et alertes de tmux sont masqués ; le préfixe tmux reste utilisable mais n'est plus nécessaire. Décision de l'auteur, 2026-10-18.
- § 3.1 / § 10 : « needs attention » = permission demandée, réponse attendue, `stuck?` ; regroupement par projet, à défaut par dépôt, à défaut `Other`, en attendant le plan 6.
- § 6.5 : l'arrêt d'une session Claude envoie deux `C-c`.
- Feuille de route : le plan 4 devient « Vue Sessions et interface transparente » (ce plan), une ligne « 4b — Vue Tâches » est ajoutée ; dans « Reports issus du plan 3 », noter que `/clear` a été vérifié avec le vrai Claude par l'auteur (2026-10-18).

- [ ] **Étape 1 : écrire ces sections. Étape 2 : relire que rien ne contredit les § 5.1 à 5.5. Étape 3 : commit** `git commit -m "docs: transparent interface (spec 5.6) and plan 4 split"`

---

### Task 2 : « needs attention » et navigation `M-n` / `M-N` (cœur)

**Fichiers :**
- Créer : `src/meute/core/attention.py`
- Test : `tests/test_attention.py`

**Interfaces :**
- `needs_attention(state: SessionState) -> bool` : vrai pour `PermissionRequested`, `WaitingInput`, `MaybeStuck` seulement (`match` exhaustif).
- `attention_count(sessions: Sequence[Session]) -> int`.
- `next_attention(order: Sequence[Session], current: SessionId | None, *, backwards: bool = False) -> Session | None` : parmi les sessions de `order` (ordre d'affichage) qui demandent l'attention, celle qui suit `current` (ou la précède), en boucle ; `current` absent ou inconnu → la première (ou la dernière) ; aucune → `None` ; si `current` est la seule, elle-même.

- [ ] **Étape 1 : tests qui échouent** : `test_needs_attention` (paramétré sur les 11 états, liste explicite) ; `test_next_attention_wraps_both_ways` (A, B, C dont B et C demandent l'attention : après B → C, après C → B, en arrière après B → C) ; `test_next_attention_from_a_quiet_or_unknown_session` ; `test_no_session_needs_attention` ; propriété `hypothesis` : le résultat, s'il existe, demande toujours l'attention.
- [ ] **Étape 2 : échec. Étape 3 : implémenter.** Sélection mutmut.
- [ ] **Étape 4 : vérification complète ; commit** `git commit -m "feat(core): sessions that need attention and their order"`

---

### Task 3 : quotas et projection (§ 7.4)

**Fichiers :**
- Créer : `src/meute/core/quota_view.py`
- Modifier : `src/meute/core/db/samples.py` (`quota_history`)
- Test : `tests/test_quota_view.py`, `tests/test_db_samples.py` (tests nouveaux seulement)

**Interfaces :**
- `quota_history(db, *, since: datetime) -> list[tuple[datetime, float]]` : `(created_at, five_hour_pct)` des relevés de quota à partir de `since`, pourcentage connu seulement, par date croissante.
- `projected_limit(samples: Sequence[tuple[datetime, float]], *, resets_at: datetime | None, now: datetime) -> datetime | None` : régression linéaire (moindres carrés) sur les relevés des 30 dernières minutes avant `now`, **après le dernier reset** (un pourcentage qui baisse ouvre un nouveau cycle : seuls les relevés depuis la baisse comptent) ; au moins deux relevés d'instants distincts et une pente strictement positive ; l'heure où la droite atteint 100 %, si elle est postérieure à `now` et antérieure à `resets_at` (ou `resets_at` inconnu) ; sinon `None`.
- `QuotaLine(five_hour_pct: float | None, five_hour_resets_at: datetime | None, seven_day_pct: float | None, seven_day_resets_at: datetime | None, limit_at: datetime | None, peak: str)` et `quota_lines(line: QuotaLine, *, local: tzinfo) -> list[str]`, textes exacts :
  - `5h {n}% · resets {HH:MM}` puis, si `limit_at`, ` · limit around {HH:MM} at this rate` ;
  - `7d {n}% · resets {Ddd HH:MM}` (jour abrégé anglais, `Mon`… `Sun`) ;
  - la ligne des heures pleines, texte de `statusline_render` sans les séquences de couleur (exposer une fonction publique `peak_text(now, quotas, local) -> str` dans `statusline_render.py`, que le rendu de la statusline réutilise) ;
  - une partie inconnue est omise ; pourcentages arrondis comme la statusline.
- `quota_level(pct: float) -> str` : `"ok"` sous 50, `"warn"` de 50 à 80 exclu, `"high"` au-delà (la TUI en fait vert / orange / rouge, § 7.4).

- [ ] **Étape 1 : tests qui échouent** (point de vigilance 2) : projection sur une montée régulière (40 % → 50 % en 20 min → limite dans 1 h 40, avant un reset dans 3 h → l'heure exacte) ; limite après le reset → `None` ; un seul relevé, deux relevés au même instant, pente nulle ou négative → `None` ; baisse au milieu (nouveau cycle) → seule la partie après la baisse ; relevés de plus de 30 min ignorés ; textes exacts des lignes (fuseau Europe/Paris) ; `quota_level` aux bornes 49,9 / 50 / 79,9 / 80 ; propriété : `projected_limit` ne lève jamais et renvoie `None` ou un instant entre `now` et `resets_at`.
- [ ] **Étape 2 : échec. Étape 3 : implémenter.** Sélection mutmut.
- [ ] **Étape 4 : vérification complète ; commit** `git commit -m "feat(core): quota lines and limit projection"`

---

### Task 4 : modèle de vue Sessions (cœur)

**Fichiers :**
- Créer : `src/meute/core/sessions_view.py`
- Test : `tests/test_sessions_view.py` (+ instantanés `syrupy`)

**Interfaces :**
- Consomme : `SessionRow` et `BoardData` (`board_view.py`), `needs_attention` (Task 2), `ClaudeDetails`, `StatuslineData`, `Repo`, `Project`, `display_path`, `printable`, `state_label`.
- `SessionInfo(row: SessionRow, details: ClaudeDetails | None, metrics: StatuslineData | None, group: str)` ; `group_name(session, *, projects: Mapping[ProjectId, str], repos: Mapping[RepoId, Repo]) -> str` (projet, sinon dépôt, sinon `Other`).
- `ViewState(collapsed: frozenset[str] = frozenset(), attention_only: bool = False, show_ended: bool = False)`.
- `SessionsView(lines: tuple[ViewLine, ...])` avec `ViewLine` = union de `HeaderLine(group: str, text: str)`, `SessionLine(session_id: SessionId, text: str, attention: bool)`, `RepoLine(repo_id: RepoId, text: str)`, `InfoLine(text: str)` (non sélectionnable) ; `build_view(infos: Sequence[SessionInfo], repos: Sequence[Repo], outside: Sequence[AgentInfo], orphans: Sequence[str], state: ViewState, *, now: datetime, home: Path | None) -> SessionsView`.
- Règles et textes exacts :
  - groupes par ordre alphabétique sans casse, `Other` en dernier ; en-tête `{group}  {n} live · {durée} · ${coût:.2f}` (durée et coût : somme des derniers relevés des sessions du groupe, parties omises si inconnues ; durée `{h}h{mm}` ou `{m}m`) ; replié : en-tête suivi de ` (collapsed)` et aucune ligne de session ;
  - ligne de session : `▶ ` ou deux espaces, `!` si elle demande l'attention sinon une espace, puis `{title}  {state_label}  {âge}  {ctx}%  ${coût}  [{mode}]` (âge depuis `last_activity_at` : `now`, `{m}m`, `{h}h`, `{d}d` ; `ctx`, coût et mode omis s'ils sont inconnus ; coût seulement au-dessus de 0,10 comme la statusline) ;
  - sessions terminées (non vivantes) : cachées sauf `show_ended`, avec une ligne d'information `{n} ended (e to show)` en bas du groupe ;
  - `attention_only` : seules les sessions qui demandent l'attention, groupes vides omis ; si aucune : `InfoLine("Nothing needs your attention.")` ;
  - en bas : `Repositories` puis les dépôts sans session vivante (`{name} ({kind})  + session`), puis `Outside meute` et `Orphans` comme aujourd'hui (seulement s'ils ne sont pas vides).
- `selectable(view) -> tuple[int, ...]` (index des `SessionLine` et `RepoLine`) et `keep_selection(old_key: str | None, view, fallback: int) -> int` : la sélection suit la session ou le dépôt ; sinon l'index borné à la liste sélectionnable (point de vigilance 3).
- `details_lines(info: SessionInfo, *, now: datetime, home: Path | None) -> list[str]` : `Folder`, `Model`, `Mode`, `Permission` (seulement si une permission attend : `Waiting for: {pending_permission}`), `Last tool`, `Last reply` (une ligne, 200 caractères au plus), `Context` / `Cost` / `Duration` ; parties inconnues omises ; tout passe par `printable`.

- [ ] **Étape 1 : tests qui échouent** : instantanés de `build_view` (trois groupes, une session par état intéressant, un groupe replié, des sessions terminées cachées puis montrées, filtre « needs attention » avec et sans résultat, dépôts sans session, sections Outside et Orphans) ; `group_name` (projet, dépôt, aucun) ; textes exacts d'une ligne de session et d'un en-tête ; `keep_selection` quand la session sélectionnée est repliée, filtrée, disparue, ou quand la liste devient vide (point de vigilance 3) ; `details_lines` avec et sans permission en attente ; un titre et un message de Claude contenant `\x1b[2J` sortent neutralisés.
- [ ] **Étape 2 : échec. Étape 3 : implémenter.** Sélection mutmut.
- [ ] **Étape 4 : vérification complète ; commit** `git commit -m "feat(core): sessions view model with groups, attention and details"`

---

### Task 5 : la vue Sessions dans le tableau de bord

**Fichiers :**
- Modifier : `src/meute/tui/board.py` (découper en `board.py` et `tui/sessions_pane.py` si le fichier dépasse 300 lignes), `src/meute/core/board_view.py` (données en plus), `src/meute/cli/board_backend.py`
- Test : `tests/test_tui_sessions.py` (comportement et rendu) ; instantanés existants mis à jour (exception n° 1)

**Interfaces :**
- `BoardData` gagne, avec des valeurs par défaut vides pour garder les constructeurs existants : `details: Mapping[SessionId, ClaudeDetails]`, `metrics: Mapping[SessionId, StatuslineData]`, `projects: Mapping[ProjectId, str]`, `quota: QuotaLine | None`, `now: datetime | None`.
- Le backend remplit ces champs à chaque relecture (une requête groupée pour les détails, `latest_metrics` par session vivante, `list_projects`, `latest_quota` + `quota_history(since=now-30 min)` + `projected_limit` + `peak_text`).
- Affichage : en haut les lignes de quota (`quota_lines`, pourcentages colorés selon `quota_level`), puis la vue (`build_view` ; le `[mode]` d'une session en `auto`, `bypassPermissions` ou `dontAsk` est coloré en orange, § 6.2), puis, sous un séparateur, le détail de la session sélectionnée (`details_lines`), puis le pied :
  `↑↓ select · Enter show · c Claude · n Bash · x stop · a attention · e ended · q detach`.
- Touches nouvelles : `a` bascule `attention_only` ; `e` bascule `show_ended` ; `space` (ou `←`/`→`) replie et déplie le groupe de la ligne sélectionnée ; `q` → action `Detach()` (ajoutée à `BoardAction`, le backend lance `tmux detach-client`) ; la sélection saute les lignes non sélectionnables. Les touches existantes gardent leur effet.
- Souris : un clic sur une `SessionLine` la sélectionne et l'affiche (`ShowSession`), sur une `RepoLine` la sélectionne, sur un en-tête replie ou déplie le groupe ; la molette fait défiler la liste.
- `[ui]` gagne `show_details = true` (le détail peut être caché sur un petit écran) — validé comme booléen.

- [ ] **Étape 1 : tests qui échouent** (`app.run_test`, faux backend comme dans `tests/test_tui_board.py`) : `a`, `e`, `space` sur un en-tête ; `q` → `Detach` ; un clic sur une ligne de session → `ShowSession` de cette session ; un clic sur un en-tête replie le groupe ; la sélection ne tombe jamais sur un en-tête ; le détail suit la sélection ; rendu à 60 et 100 colonnes (`snap_compare`).
- [ ] **Étape 2 : échec. Étape 3 : implémenter**, puis mettre à jour les instantanés et tests listés à l'exception n° 1 en relisant chaque différence (les tests de comportement des touches existantes restent inchangés et verts).
- [ ] **Étape 4 : vérification complète ; commit** `git commit -m "feat(tui): sessions view with groups, attention, quotas and details"`

---

### Task 6 : arrêt en tâche de fond et arrêt rapide de Claude [sécurité]

**Fichiers :**
- Modifier : `src/meute/cli/session_stop.py`, `src/meute/tui/board.py`, `src/meute/cli/board_backend.py`
- Test : `tests/test_session_stop_claude.py`, `tests/test_tui_stop_worker.py`, `tests/test_board_backend_stop.py`

**Interfaces :**
- `stop_session` : pour une session `AgentKind.CLAUDE`, envoie `C-c`, attend 0,3 s, renvoie `C-c`, puis la boucle de grâce existante (5 s) ; pour Bash, inchangé.
- `BoardBackend` gagne `perform_in_background(self, action: BoardAction) -> None`, appelé depuis un worker de Textual (`run_worker(..., thread=True)`) ; l'implémentation CLI ouvre **sa propre** `Database` (même chemin, `busy_timeout` 5000) pour la durée de l'action, puis la ferme ; le fil principal ne touche jamais cette connexion.
- `BoardApp` : `StopSession` passe par le worker ; pendant l'arrêt, le pied affiche `Stopping "{title}"…` et un second `x` sur la même session est ignoré ; à la fin, relecture forcée ; une erreur s'affiche avec `error_text`. Les autres actions restent directes.

- [ ] **Étape 1 : tests qui échouent** : avec le faux `claude` (étendu : un premier `C-c` est ignoré, le second fait sortir avec le code 0, après avoir envoyé `SessionEnd`), `session stop --yes` sur une session Claude se termine en moins de 2 s et la session est `exited` ; le tableau reste réactif pendant un arrêt lent (faux backend qui bloque 1 s dans `perform_in_background` : une touche `j` est traitée avant la fin) ; second `x` ignoré ; aucune connexion SQLite partagée entre fils (le faux backend vérifie l'identité du fil) ; l'erreur d'un arrêt s'affiche.
- [ ] **Étape 2 : échec. Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète ; passes de simplification et de sécurité ; commit** `git commit -m "feat: stop sessions in the background, Claude with a double C-c"`

---

### Task 7 : configuration tmux transparente et barre d'état meute [sécurité]

**Fichiers :**
- Modifier : `src/meute/tmux/conf.py`, `src/meute/core/config_validate.py` et `src/meute/core/config.py` (`[keys]`), `src/meute/cli/board_backend.py`, `src/meute/cli/session_show.py`
- Créer : `src/meute/core/status_line.py`
- Test : `tests/test_tmux_conf.py` (tests nouveaux), instantané régénéré (exception n° 2), `tests/test_status_line.py`, `tests/test_config.py` (tests nouveaux)

**Interfaces :**
- `[keys]` gagne `next_attention = "M-n"`, `previous_attention = "M-N"`, `detach = "M-q"`, validés comme les autres (point de vigilance 4), dans `DEFAULT_CONFIG` après `focus_main` avec le commentaire `# Next / previous session that needs attention, and detach without stopping anything.`
- `Keys` (tmux) gagne les trois champs ; `LayoutSpec` gagne `attention_command: tuple[str, ...]` (meute appelé comme `sync_command`, avec `session next` / `session previous` ajoutés par `render_config`).
- Lignes ajoutées par `render_config`, dans cet ordre, après les lignes existantes de barre d'état (qui changent comme indiqué) :

```
set -g mouse on
set -g status-left ""
set -g status-right "#{@meute_status}"
set -g status-right-length 120
set -g status-style "bg=default,fg=colour245"
set -g window-status-format ""
set -g window-status-current-format ""
set -g pane-border-lines single
set -g pane-border-style "fg=colour238"
set -g pane-active-border-style "fg=colour238"
set -g visual-activity off
set -g visual-bell off
set -g visual-silence off
set -g bell-action none
set -g display-time 1000
bind -n M-n run-shell -b "<attention_command> 'session' 'next'"
bind -n M-N run-shell -b "<attention_command> 'session' 'previous'"
bind -n M-q detach-client
```

  (`<attention_command>` et les touches selon `spec`, cités comme la commande de synchronisation : `_sh_quote`, `format_literal`, double `_tmux_escape` ; la ligne `status-left "[meute] "` actuelle disparaît.)
- `status_text(displayed: str | None, attention: int, five_hour_pct: float | None) -> str` (`status_line.py`) : `▶ {title}` si une session est affichée, puis ` · {n} need attention` si `n > 0`, puis ` · 5h {p}%` si connu ; passe par `printable` ; tmux l'affiche par `#{@meute_status}` (pas de réexpansion des formats, vérifié au plan 2) ; le backend du tableau met `@meute_status` à jour quand ce texte change, et `show_session` aussi.

- [ ] **Étape 1 : tests qui échouent** : instantané de `render_config` relu contre le bloc ci-dessus ; la configuration est acceptée par un serveur de test (`source-file`), `list-keys -T root` contient `M-n`, `M-N`, `M-q`, et `show-options -g mouse` vaut `on` ; une touche refusée (`"M-n \\; kill-server"`) → `InvalidInput` ; `status_text` (paramétré) ; le backend ne réécrit pas `@meute_status` quand le texte est inchangé.
- [ ] **Étape 2 : échec. Étape 3 : implémenter**, puis régénérer et relire l'instantané (exception n° 2).
- [ ] **Étape 4 : vérification complète ; passes de simplification et de sécurité ; commit** `git commit -m "feat(tmux): transparent interface and meute status line"`

---

### Task 8 : `meute session next|previous` et mode étroit [sécurité]

**Fichiers :**
- Modifier : `src/meute/cli/session_commands.py`, `src/meute/tmux/conf.py` (liaison `M-o`), `src/meute/cli/session_show.py`
- Test : `tests/test_cli_session_next.py`, `tests/test_tmux_narrow.py`

**Interfaces :**
- `meute session next` / `meute session previous` (commandes cachées) : `refresh`, ordre d'affichage de la vue (Task 4, `ViewState()` par défaut), `next_attention` depuis la session affichée (`@meute_id` du panneau principal), puis `show_session` ; aucune → rien, code 0, et `tmux display-message "Nothing needs your attention."` sur le client.
- `M-o` : `bind -n {focus_main} if-shell -F "#{window_zoomed_flag}" "" "select-pane -t '=meute:main.{left}'"` — en mode étroit (fenêtre zoomée), `M-o` ne fait rien ; sinon comme avant (report du plan 2). L'instantané de la Task 7 est mis à jour en conséquence dans cette tâche (même exception n° 2).

- [ ] **Étape 1 : tests qui échouent** : trois sessions (faux `claude`), deux demandent l'attention → `session next` affiche la première, encore une fois la seconde, puis la première (boucle) ; `previous` en sens inverse ; aucune → code 0 et rien ne change ; mode étroit (fenêtre de 100 colonnes) : exécuter la commande liée à `M-o` (lue par `list-keys -T root M-o`, lancée avec `tmux … run-shell` ou recopiée) laisse `window_zoomed_flag` à 1 (point de vigilance 5).
- [ ] **Étape 2 : échec. Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète ; passes de simplification et de sécurité ; commit** `git commit -m "feat: jump between sessions that need attention; keep narrow mode zoomed"`

---

### Task 9 : écran d'accueil

**Fichiers :**
- Modifier : `src/meute/cli/welcome.py`, `tests/test_welcome.py` (exception n° 3)

Texte exact (`{…}` = touches configurées) :

```
meute

Pick a session in the dashboard and press Enter, or click it.
{focus_board}: dashboard · {focus_main}: main area
{next_attention} / {previous_attention}: next / previous session that needs attention
{detach} or q in the dashboard: detach, everything keeps running
Hold Shift to select text with the mouse.
```

- [ ] **Étape 1 : mettre à jour le test existant pour ce texte (exception n° 3) et le voir échouer. Étape 2 : implémenter. Étape 3 : vérification complète ; commit** `git commit -m "feat: welcome screen explains the transparent interface"`

---

### Task 10 : essai réel scripté et tests de mutation

- [ ] **Étape 1 : essai** sur un serveur tmux jetable avec le faux `claude` (pas le vrai : l'essai interactif avec le vrai Claude est laissé à l'auteur) : `layout sync`, deux sessions Claude, l'une passe en permission → la barre d'état (`show-options -gv @meute_status`) contient `1 need attention` ; `meute session next` l'affiche ; `capture-pane` du tableau montre l'en-tête de groupe, le `!` et le détail ; `x` puis `y` dans le tableau (par `send-keys`) arrête la session en moins de 2 s sans figer le tableau. Noter chaque résultat.
- [ ] **Étape 2 : mutmut** (même configuration que le plan 3, nouveaux fichiers de tests en processus ajoutés à la sélection) ; survivants nouveaux traités en TDD (`tests/test_mutants_plan4.py`) ou justifiés ; rapport `docs/dev/mutants/2026-plan-4-python.md`.
- [ ] **Étape 3 : vérification complète** (`verify.sh`, profil `ci`, tests des hooks, suite sous tmux 3.4 si le binaire local est disponible) ; commit `git commit -m "test: strengthen plan 4 tests after mutmut"`

---

### Task 11 : feuille de route, revues et PR

- [ ] **Étape 1 : feuille de route** : plan 4 « fait », « Reports issus du plan 4 » (liste « Hors périmètre »), retirer des reports des plans 2 et 3 ce qui est traité (`M-o` en mode étroit, arrêt qui fige le tableau, `M-n` / `M-N`, compteur de la barre d'état, couleur du mode de permission — affiché dans la ligne de session).
- [ ] **Étape 2 : `/simplify` et `/security-review` sur la branche, revue finale, une vague de corrections.**
- [ ] **Étape 3 : commit, push, PR** `Plan 4 (Python): sessions view and transparent interface`, assignée à `gaetinux`, avec les exceptions de tests, les exceptions de lint, l'essai scripté, le rapport de mutation et ce qui reste à essayer à la main (souris, `M-n`, détacher et rattacher, mode étroit) ; dernière ligne `🤖 Generated with [Claude Code](https://claude.com/claude-code)`, sans lien de session.
