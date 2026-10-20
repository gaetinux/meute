# meute — Plan 4b Python : passe visuelle, vue Tâches et saisie rapide globale — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Objectif :** le tableau prend l'allure validée sur maquette (direction C2 : onglets, barres de quota, encadré « Needs you », fiches de session, 72 colonnes) ; un onglet Tâches liste, regroupe et édite les tâches ; `M-t` note une tâche de partout dans une fenêtre tmux ; `L` lance Claude sur une tâche et colle son texte sans l'envoyer.

**Architecture :** comme au plan 4, tout ce qui s'affiche se calcule dans `meute.core`. Les lignes deviennent des suites de segments typés par un **rôle** (titre, atténué, alerte…) ; `meute.tui` traduit les rôles en styles Textual et ne fait que dessiner et transmettre touches et clics. `board.py` délègue chaque onglet à un contrôleur (`sessions_tab.py`, `tasks_tab.py`). La fenêtre `M-t` est une petite application Textual lancée par `tmux display-popup` ; le collage dans Claude passe par un tampon tmux chargé depuis un fichier privé puis `paste-buffer -p`.

**Stack technique :** existante (Python 3.13, uv, Typer, Textual 8.2, `pytest-textual-snapshot`, `syrupy`, `hypothesis`, `mutmut`) ; aucune dépendance nouvelle (`difflib` pour la suggestion de projet) ; tmux ≥ 3.2 (`display-popup`).

**Spécification :** `docs/superpowers/specs/2026-10-19-meute-vue-taches-design.md` (conception du 4b et section « Maquettes validées ») ; `docs/superpowers/specs/2026-10-15-meute-design.md`, § 5, 5.6, 9.2, 9.3, 9.5, 9.6, 10. Maquettes : https://claude.ai/artifact/Fj3aTuYiaTyfhJLEbY4ib3 (C2, Onglet Tâches, Fenêtre M-t). Guide : `docs/dev/developpement-assiste-par-ia.md`.

**Prérequis :** plan 4 mergé (PR #10). Branche : `feat/plan-4b-python` (déjà créée, rebasée sur `main`, porte la conception).

## Décisions de conception (à relire)

1. **Segments et rôles.** Une ligne de vue est un tuple de `Span(text, role)` ; le texte brut (`plain`) reste ce que testent les tests du cœur, les rôles ce que teste la TUI. Cela remplace le repérage par position (`risky_mode_span`) du plan 4.
2. **Formats gardés.** Les nombres gardent les formats actuels de l'interface (`62%`, `1h19`, `4m ago`, `$4.40`, `6pm`) ; les espaces des maquettes (`62 %`, `1 h 19`) étaient de la typographie française.
3. **Branche dans la fiche** seulement quand elle est connue : `worktree_branch` de la statusline. Pas d'état Git ni de PR avant le plan 6 et la V1.1.
4. **Projet d'une session** (filtre « this project », projet par défaut de `M-t`) : son `project_id`, à défaut le projet qui porte le nom de son dépôt, à défaut aucun. Les projets ne sont créés automatiquement qu'au plan 6.
5. **« Without session » replié par défaut** seulement au-delà de 5 dépôts : peu de dépôts restent visibles directement, et le tableau vide garde de quoi lancer une session.
6. **Pas de « + N more »** dans les groupes de tâches : la liste défile, comme la vue Sessions.
7. **Reports rapides** : `+1h` = maintenant + 1 h ; `tonight 6pm` = aujourd'hui 18:00, ou demain si 18:00 est passé ; `tomorrow 9am` = demain 9:00 ; `Monday 9am` = le premier lundi 9:00 strictement après maintenant ; `clear` retire l'échéance. Heures murales du fuseau local (comme `parse_due`).
8. **Le collage** passe par un fichier privé (`0600`, dossier d'état) chargé par `tmux load-buffer`, jamais par un argument de commande : tmux couperait un argument finissant par `;` et n'interprète rien dans un fichier.

## Contraintes globales

**Hérité des plans 1 à 4 (inchangé)**
- Frontières d'imports (import-linter) : `meute.core`, `meute.tmux`, `meute.git` stdlib seulement ; `meute.tui` : `meute.core` et `textual` ; seul `meute.cli` assemble.
- Dataclasses gelées, `match` exhaustif terminé par `assert_never`, pas d'`Any`/`cast`/`assert` hors tests, docstrings sur le public de `meute.core`, fichiers de moins de 300 lignes, exceptions de lint précises avec ` — raison`.
- Interface en anglais, textes de ce plan copiés mot pour mot ; toute donnée venue de la base, de Claude ou de l'utilisateur passe par `printable` (ou `one_line`) avant d'être affichée ou collée ; Textual l'affiche avec `Content`, jamais en balisage.
- Tests tmux sur serveurs jetables seulement (`tmux_server`, `sandbox`) ; aucun test automatique n'appelle le vrai `claude` ; jamais le serveur `meute` ni le tmux `default` de l'utilisateur.
- Le tableau ne bloque jamais sa boucle : un lancement sur tâche (attente de Claude jusqu'à 10 s) tourne dans un worker avec sa propre connexion SQLite, comme l'arrêt.
- Toute écriture de tâche passe par `update_task` / `delete_task` / `add_note` / `create_task` de `meute.core.db` avec la `version` lue et l'acteur `Actor(author=Author.USER, channel=Channel.TUI)`.

**Qualité et workflow**
- TDD strict. Ne jamais modifier, supprimer ni désactiver un test existant. **Seules exceptions autorisées par ce plan** (numérotation continue avec le plan 4), chacune relue et signalée dans le commit et la PR :
  - **n° 9** (Task 3) : les instantanés de la vue Sessions (`tests/__snapshots__/test_sessions_view.ambr`, `test_board_view*.ambr`) et les tests qui fixent le texte exact des lignes de session, d'en-tête de groupe, de quotas ou des sections du bas (`test_sessions_view.py`, `test_quota_view.py::…lines…`, `test_tui_board.py` pour les textes de lignes). Les tests de comportement (touches, sélection, repli, clics) ne changent pas et doivent passer.
  - **n° 10** (Task 4) : `tests/test_config.py::…` qui fixe `(60, 120)` passe à `(72, 120)` ; instantanés `tests/__snapshots__/test_tui_board/*.raw`, `test_tui_sessions/*.raw` et ceux de `test_focus_cues.py` régénérés pour le nouveau rendu.
  - **n° 11** (Task 5) : les tests qui fixent `KEYS_HELP` (`test_tui_keys_help.py`) suivent la nouvelle liste (ligne `Tab`).
  - **n° 12** (Task 12) : l'instantané de la configuration tmux (`test_tmux_conf.ambr`) gagne la ligne `M-t` ; `test_welcome.py` si l'accueil cite la touche.
- Instantanés relus ligne par ligne ; jamais `--snapshot-update` à l'aveugle.
- Chaque tâche se termine par `bash scripts/verify.sh` et un commit ; `/simplify` sur la branche en fin de plan, `/security-review` en fin de plan (SQL, sous-processus, collage tmux, entrée utilisateur). Commits en anglais terminés par `Co-Authored-By: Claude …`, sans ligne `Claude-Session`. Une PR à la fin, assignée à `gaetinux`.

## Hors périmètre

- Formulaire `N`, « dernier type utilisé » de `n`, actions sur les panneaux orphelins, reprise `claude --resume` : plan 4c.
- État Git des sessions (branche ordinaire, `*`, ↑↓), projets créés automatiquement : plan 6. État des PR : V1.1.
- Contexte composé (§ 8) à la place du texte collé : plan 5.

## Points de vigilance (Review Focus)

1. **Texte collé dans Claude.** Un titre, une description ou une note contenant `ESC [201~` terminerait le collage et ferait taper la suite comme des touches (y compris `Entrée`) ; un texte finissant par `;` ou contenant `#{…}` ne doit rien déclencher dans tmux. `task_prompt` passe tout par `printable(keep_newlines=True)` et le chargement se fait par fichier. Tests au Task 7 et au Task 13.
2. **Liste de tâches qui change sous la sélection** (tâche terminée, filtre changé, groupe replié, tâche supprimée ailleurs) : la sélection ne doit jamais rester sur un en-tête déplié ni hors de la liste. Propriété `hypothesis` au Task 6.
3. **Échéances extrêmes et textes hostiles** : échéance en 2099 ou dépassée de huit mois, titre de 500 caractères ou avec caractères de contrôle, 500 tâches : la ligne tient dans la largeur, rien ne lève, le rendu reste sous 100 ms. Tests au Task 6 et au Task 9.
4. **Conflit de version pendant une édition** : une tâche modifiée par Claude (MCP) ou la CLI pendant que la ligne de saisie est ouverte → « modified in the meantime », la tâche est relue, le texte saisi est gardé dans la ligne. Test au Task 10.
5. **`M-t` dans des conditions limites** : en mode étroit, pressé deux fois, sans session affichée, base verrouillée. La fenêtre s'ouvre (taille bornée par tmux), une seule à la fois, le projet par défaut vaut « none: floating », une erreur garde la fenêtre ouverte avec le texte. Tests au Task 12.

---

### Task 1 : spikes S8 et S9

**Fichiers :**
- Créer : `docs/superpowers/spikes/2026-10-20-spikes-s8-s9.md`

**S8 (accord explicite de l'auteur requis avant de lancer le vrai `claude`)** : dans un serveur tmux jetable (`-L meute-spike-s8`, `HOME` réel nécessaire pour l'authentification, aucun hook meute), lancer `claude`, attendre son invite, écrire `#12 Title\n\nLine one\nLine two;` dans un fichier `0600`, `tmux load-buffer -b s8 <fichier>` puis `tmux paste-buffer -p -d -b s8 -t <pane>`. Noter : le texte apparaît-il entier dans la saisie, non envoyé ? Combien de temps après le hook `SessionStart` la saisie accepte-t-elle un collage (essayer 0 s, 0,5 s, 1 s après l'apparition de l'invite) ? Les retours à la ligne arrivent-ils en `\r` ? Tuer le serveur jetable ensuite.

**S9** : la fenêtre n'existe pas encore ; mesurer avec `hyperfine --warmup 3 -r 20` un script jetable (dans le dossier de travail temporaire, pas dans le dépôt) qui importe `meute.cli.context` et `textual.widgets`, ouvre la base et lance une application Textual minimale (un `Input`) qui se ferme au premier rendu (`call_after_refresh(self.exit)`), puis le même script dans `tmux display-popup -E` sur un serveur jetable. Seuil : moins de 400 ms du raccourci au champ utilisable ; au-delà, le repli de la conception (saisie dans le tableau) remplace le Task 12.

- [ ] **Étape 1 : S9, puis S8 si l'auteur a donné son accord** (sinon, noter « S8 reporté » et garder pour le Task 13 un délai par défaut de 1 s après `SessionStart`).
- [ ] **Étape 2 : rédiger le compte rendu** (commandes, mesures, décision) et reporter dans le Task 13 le délai mesuré (`PASTE_DELAY_SECONDS`) et la forme des retours à la ligne.
- [ ] **Étape 3 : commit** `git commit -m "docs: spikes S8 (bracketed paste in Claude) and S9 (popup start-up)"`

---

### Task 2 : segments, rôles, barres de quota et ligne d'onglets (cœur)

**Fichiers :**
- Créer : `src/meute/core/styled.py`, `src/meute/core/board_header.py`
- Modifier : `src/meute/core/quota_view.py`
- Test : `tests/test_styled.py`, `tests/test_board_header.py`, `tests/test_quota_bars.py`

**Interfaces :**
- `Role(Enum)` : `PLAIN, TITLE, DIM, ACCENT, KIND, RUNNING, IDLE, ATTENTION, RISKY, OK, WARN, HIGH, LATE, BLOCKED, REVIEW, TAB_ACTIVE, TAB`.
- `Span(text: str, role: Role = Role.PLAIN)` gelée ; `StyledLine = tuple[Span, ...]` ; `plain(line: StyledLine) -> str` ; `fit(left: StyledLine, right: StyledLine, width: int) -> StyledLine` : `left`, des espaces, puis `right` collé au bord droit ; si tout ne tient pas, `left` est coupé et finit par `…` pour laisser `right` et une espace ; si `right` seul ne tient pas, il est omis et `left` coupé à `width`.
- `quota_bar(pct: float) -> str` : 10 cases, `round(pct / 10)` pleines (`█`), bornées à 0 et 10, le reste `░`.
- `quota_bar_lines(line: QuotaLine, *, local: tzinfo) -> list[StyledLine]` : `5h {bar} {n}%  resets {HH:MM}` puis ` · limit ~{HH:MM}` (rôle `RISKY`) ; `7d {bar} {n}%  resets {Ddd HH:MM}` puis ` · {peak}` ; barre et pourcentage au rôle de `quota_level` (`ok`→`OK`, `warn`→`WARN`, `high`→`HIGH`) ; le texte des heures creuses au rôle `OK`, des heures pleines au rôle `WARN` ; `peak` seul sur sa ligne s'il n'y a pas de 7 d ; parties inconnues omises.
- `Tab(Enum)` : `SESSIONS, TASKS` ; `tabs_line(active: Tab, *, overdue: int, totals: str, width: int) -> StyledLine` : ` Sessions ` et ` Tasks ` (actif au rôle `TAB_ACTIVE`, l'autre `TAB`), puis ` {overdue}!` au rôle `HIGH` quand `overdue > 0`, et `totals` (rôle `DIM`) aligné à droite par `fit`.
- `sessions_totals(live: int, duration_ms: int | None, cost: float | None) -> str` : `{live} live`, puis ` · {duration_text}` et ` · ${cost:.2f}` quand connus ; `tasks_totals(open_: int, overdue: int) -> str` : `{open} open · {overdue} overdue` (`· {overdue} overdue` omis à 0).

- [ ] **Étape 1 : tests qui échouent** : `fit` (cas qui tient, coupe avec `…`, `right` trop long, largeur 0) et propriété `hypothesis` : `len(plain(fit(...))) == width` dès que `width ≥ 1` et que `left` est non vide ; `quota_bar` à 0, 4,9, 5, 62, 100, 130, -3 ; textes exacts de `quota_bar_lines` (fuseau Europe/Paris, 62 % reset 00:10 limite 21:13 ; 28 % reset vendredi 03:00, heures creuses) et rôles des segments ; `tabs_line` à 72 colonnes, actif Sessions puis Tasks, avec et sans retards.
- [ ] **Étape 2 : échec. Étape 3 : implémenter.** Ajouter les trois fichiers de test à `pytest_add_cli_args_test_selection` de `[tool.mutmut]`.
- [ ] **Étape 4 : vérification complète ; commit** `git commit -m "feat(core): styled lines, quota bars and the tabs line"`

---

### Task 3 : fiches de session, « Needs you » et blocs de projet (cœur)

**Fichiers :**
- Modifier : `src/meute/core/sessions_view.py`, `src/meute/core/sessions_view_text.py`, `src/meute/core/board_sessions.py`
- Créer si `sessions_view.py` dépasse 300 lignes : `src/meute/core/sessions_view_cards.py`
- Test : `tests/test_sessions_cards.py` (nouveau) ; exception n° 9 pour les tests existants qui fixent les textes

**Interfaces :**
- Chaque variante de `ViewLine` porte `spans: StyledLine` et `band: bool` (fond « attention ») ; une propriété `text` renvoie `plain(spans)` pour les appelants existants.
- Nouvelles variantes : `CardLine(session_id: SessionId, spans, band)` (lignes 2 et 3 d'une fiche, non sélectionnables ; un clic sélectionne leur session) ; `RefLine(session_id, spans)` (renvoi dans le projet, non sélectionnable ; un clic sélectionne la fiche de « Needs you ») ; `SectionLine(section: str, spans, collapsed: bool)` pour `Needs you`, `Without session`, `Outside meute`, `Orphans` (sélectionnable quand repliée, comme `HeaderLine`).
- `HeaderLine` gagne `repo_id: RepoId | None` (le dépôt du groupe quand il est connu : celui de la première session du groupe).
- `build_view(…, width: int)` et `board_sessions(data, state, width: int = 72)` : les lignes sont calculées pour `width`.
- `attention_reason(info: SessionInfo) -> str` : `permission: {pending_permission}` (ou `permission requested` sans outil connu), `waiting for your reply`, `stuck?`.

Textes exacts (`{…}` omis quand inconnu, séparateur ` · `) :
- En-tête de groupe : `▼ {name}` (`TITLE`), ` ◆ {kind}` (`KIND`), ` · {n} live · {cost}` (`DIM`) et, à droite par `fit`, `+ session` (`RUNNING`) quand `repo_id` est connu ; replié : `▶ {name} …` sans `+ session`.
- Fiche ligne 1 : `  {sym} {title}  {state}  {age}` : `●` `RUNNING` pour un état vivant sans attention, `○` `IDLE` pour les autres, `!` `ATTENTION` ; titre `TITLE` ; âge `{age_text} ago`, ou `now`.
- Fiche ligne 2 : `    {duration} · {cost} · {ctx}% · {model} · {mode}` (`DIM`, contexte au rôle de `quota_level`, mode risqué `RISKY`) ; omise si tout est inconnu.
- Fiche ligne 3 : `    └ {branch} · {last_tool}` (`DIM`, branche = `metrics.worktree_branch`) ; omise si tout est inconnu.
- « Needs you » : section en tête quand une session demande l'attention (hors filtre `a`, qui garde son comportement) : `Needs you ({n})` (`ATTENTION`), puis une fiche par session dont la ligne 1 est `  ! {title} · {group} · {reason}`, toutes les lignes `band=True`. Dans son groupe, la session n'a plus qu'une `RefLine` : `  ! {title}  ↑ needs you`.
- Bas de liste : `  + {n} ended (e to show)` ; `▶ Without session ({n})` / `▼ Without session ({n})` (repliée par défaut au-delà de `REPOS_FOLDED_ABOVE = 5` dépôts) suivie des dépôts `  {repo_line}` ; `▼ Outside meute ({n})` ; `▼ Orphans ({n})`. Une ligne vide sépare les blocs.
- `risky_mode_span` disparaît (remplacé par le rôle `RISKY`) ; `line_entry`, `line_info`, `line_group`, `keep_selection`, `selectable` gardent leurs signatures ; `line_info` renvoie aussi la session d'une `CardLine` ou d'une `RefLine`.

- [ ] **Étape 1 : tests qui échouent** (`tests/test_sessions_cards.py`) : fiche complète et fiches à moitié inconnues (lignes omises) ; session en permission → section « Needs you » en tête, `RefLine` dans son groupe, une seule ligne sélectionnable pour elle ; filtre `a` inchangé ; « Without session » replié à 6 dépôts, déplié à 5 ; sélection jamais sur une `CardLine` ni une `RefLine` (propriété `hypothesis` sur des listes de sessions aux états tirés au hasard, après repli et dépli aléatoires) ; titre de 300 caractères avec `\x1b` : la ligne fait `width` colonnes et ne contient pas `\x1b`.
- [ ] **Étape 2 : échec. Étape 3 : implémenter.** Puis lancer la suite : les tests qui fixent les anciens textes échouent ; les mettre à jour un par un **au titre de l'exception n° 9 seulement** et relire chaque instantané ; tout test de comportement qui échoue est un bug du code, pas du test.
- [ ] **Étape 4 : vérification complète ; commit** `git commit -m "feat(core): session cards, needs-you section and project blocks"` (corps : liste des tests touchés au titre de l'exception n° 9).

---

### Task 4 : rendu de la vue Sessions et largeur 72

**Fichiers :**
- Modifier : `src/meute/tui/sessions_pane.py`, `src/meute/tui/board.py`, `src/meute/core/config.py` (défaut et commentaire du modèle de fichier), `src/meute/tui/sessions_cursor.py` (largeur)
- Test : `tests/test_tui_styles.py` (nouveau) ; exception n° 10

**Interfaces :**
- `ROLE_STYLES: Mapping[Role, str]` dans `sessions_pane.py` (palette des maquettes) : `TITLE "bold #f2f2f2"`, `DIM "#8a8a8a"`, `ACCENT "#3b8eea"`, `KIND "#4fc1e9"`, `RUNNING "#23d18b"`, `IDLE "#8a8a8a"`, `ATTENTION "bold #f16c6c"`, `RISKY "#e8912d"`, `OK "#23d18b"`, `WARN "#e5c07b"`, `HIGH "bold #f16c6c"`, `LATE "#f16c6c"`, `BLOCKED "#e8912d"`, `REVIEW "#c678dd"`, `TAB_ACTIVE "bold #0c0c0c on #3b8eea"`, `TAB "#8a8a8a"`, `PLAIN ""`. Fond des lignes `band` : `on #2a1416`. Sélection : `on #264f78` avec le focus, `BLURRED_SELECTED_STYLE` (`on #444444`) sans.
- `styled_content(line: StyledLine) -> Content` ; `view_content` colore chaque segment, applique le fond des `band`, et la sélection sur la ligne choisie **et** les `CardLine` de la même session.
- La ligne d'onglets remplace `#title` (`tabs_line(Tab.SESSIONS, …)`) ; sans le focus, l'onglet actif passe au rôle `TAB` souligné (`underline`), pour garder le repère de focus du § 5.6.
- Les quotas utilisent `quota_bar_lines`. Le détail s'ouvre par un filet `─ {title} ───…` au rôle `ACCENT` et ne garde que `Reply`, `Folder`, `Waiting for` (étiquettes alignées sur 8 colonnes, rôle `DIM`).
- `SessionsCursor` reçoit la largeur (`resize(width: int)`) ; `BoardApp.on_resize` la transmet et redessine.
- `UiConfig.board_width` vaut 72 par défaut ; le modèle de configuration dit `board_width = 72`.

- [ ] **Étape 1 : tests qui échouent** : `styled_content` donne au segment `RISKY` le style orange (`Content.spans`) ; une ligne `band` sélectionnée porte la sélection et non le fond rouge ; la sélection d'une session couvre ses trois lignes ; `Config().ui.board_width == 72` (nouveau test) ; instantanés `pytest-textual-snapshot` nouveaux : `test_sessions_cards_72_columns`, `test_sessions_needs_you_100_columns`, `test_sessions_blurred_72_columns`.
- [ ] **Étape 2 : échec. Étape 3 : implémenter.** Puis régénérer, au titre de l'exception n° 10 seulement, les instantanés du tableau et de `test_focus_cues.py` et le test `(60, 120)` ; relire chaque rendu contre la maquette C2.
- [ ] **Étape 4 : essai visuel** sur un serveur jetable (`--kind bash` seulement) avec `script` pour attacher un client ; capture `tmux capture-pane -e -p` jointe au compte rendu. **Vérification complète ; commit** `git commit -m "feat(tui): card layout, palette and 72-column board"`

---

### Task 5 : onglets dans le tableau

**Fichiers :**
- Créer : `src/meute/tui/sessions_tab.py`, `src/meute/tui/tasks_tab.py` (vide pour l'instant : une ligne `No tasks yet.`)
- Modifier : `src/meute/tui/board.py`, `src/meute/core/board_view.py` (`KEYS_HELP`)
- Test : `tests/test_tui_tabs.py` ; exception n° 11

**Interfaces :**
- `Tab` (Task 2) ; `BoardApp._tab: Tab`, `Tab` (la touche) bascule, un clic sur le nom d'un onglet dans la ligne d'onglets le choisit.
- Contrôleur commun (protocole `TabController` dans `board.py`) : `handle_key(key: str) -> BoardAction | None`, `click(y: int, x: int) -> BoardAction | None`, `lines() -> Content`, `details() -> Content | None`, `footer() -> str`, `keys_help() -> str`, `rebuild(data: BoardData, width: int) -> None`. `SessionsTab` reprend **sans changement de comportement** la logique de `board.py` (curseur, `_act`, `_click`, `_show`, confirmation d'arrêt) ; `board.py` garde le chargement, les workers, le pied et l'aiguillage, et passe sous 250 lignes.
- `KEYS_HELP` gagne la ligne `Tab tasks · q detach` à la place de `q detach` sur la troisième ligne : `a attention only · e ended sessions · Tab tasks · q detach`.

- [ ] **Étape 1 : tests qui échouent** : `Tab` bascule et revient ; un clic sur ` Tasks ` choisit l'onglet ; dans l'onglet Tâches, `x`, `c`, `n` ne font rien ; la sélection de l'onglet Sessions est la même après un aller-retour.
- [ ] **Étape 2 : échec. Étape 3 : déplacer d'abord la logique dans `SessionsTab` (tous les tests existants passent sans retouche), puis ajouter les onglets.** Mettre à jour le test de `KEYS_HELP` au titre de l'exception n° 11.
- [ ] **Étape 4 : vérification complète ; commit** `git commit -m "feat(tui): Sessions and Tasks tabs on the board"`

---

### Task 6 : modèle de l'onglet Tâches (cœur)

**Fichiers :**
- Créer : `src/meute/core/tasks_view.py`, `src/meute/core/task_line.py`
- Test : `tests/test_tasks_view.py`, `tests/test_task_line.py` (+ instantanés `syrupy`)

**Interfaces :**
- `TaskScope(Enum)` : `ALL, THIS_PROJECT, FLOATING` ; `Grouping(Enum)` : `URGENCY, PROJECT`.
- `TasksState(scope=ALL, grouping=URGENCY, collapsed=frozenset({"no_due", "done_today"}))` gelée (clés de groupe : `Bucket.value` ou `project:{id}` / `floating`).
- `TaskGroupLine(group: str, spans, collapsed: bool, band: bool)`, `TaskLine(task_id: TaskId, spans, band: bool)`, `TaskInfoLine(spans)` ; `TasksLine` leur union.
- `TasksView(lines: tuple[TasksLine, ...], open_count: int, overdue_count: int)`.
- `build_tasks_view(tasks: Sequence[Task], state: TasksState, *, now: datetime, project: ProjectRef | None, width: int) -> TasksView`.
- `filters_line(state: TasksState, project: ProjectRef | None, width: int) -> StyledLine` : ` all `, `this project ({name})` ou `this project (none)`, `floating`, l'actif au rôle `TAB_ACTIVE`, et `f: filter` à droite (`DIM`).
- `due_short(task: Task, now: datetime) -> tuple[str, Role] | None` : bloquée → `blocked: {reason}` (`BLOCKED`) ; en retard → `{age} late` pour un instant (`2h late`, `3d late`) et `yesterday` / `{n}d late` pour une date (`LATE`) ; aujourd'hui → l'heure (`6pm`) ou `today` (`DIM`) ; à venir → `format_due` (`DIM`) ; `Review` sans échéance → `in review` (`REVIEW`) ; sinon `None`.
- `task_line(task: Task, now: datetime, width: int) -> StyledLine` : `  {symbol} {marker:<2} {title}` puis `  @{project}` (`KIND`) ou `  (floating)` (`DIM`), et `due_short` à droite par `fit` ; symbole au rôle du statut (`·` `DIM`, `»` `RUNNING`, `✕` `BLOCKED`, `◎` `REVIEW`, `✓` `OK`), `!!` et `!` au rôle `HIGH` / `WARN`.
- Groupes par urgence dans l'ordre de `Bucket`, titre `▼ {label} ({n})` / `▶ …`, « Overdue » en `ATTENTION` et `band=True` pour lui et ses tâches ; par projet : noms triés sans casse, `Floating` en dernier ; tâches triées par `sort_for_display`. Groupes vides omis. Aucune tâche : `No tasks. Press a to add one.` ; « this project » sans projet : `No project for the displayed session.`
- `tasks_selectable`, `tasks_line_key` (`task:{id}`, `group:{key}` si replié) et `keep_tasks_selection(old_key, view, fallback) -> int` : mêmes règles que `keep_selection` de la vue Sessions.

- [ ] **Étape 1 : tests qui échouent** : regroupement et ordre sur `NOW` de `tests/support.py` ; filtres (dont « this project » sans projet) ; compteurs ; replis par défaut ; `due_short` aux bornes (minuit, hier, échéance en 2099, retard de huit mois) ; propriété `hypothesis` du point de vigilance 2 (tâches, filtre, regroupement et replis tirés au hasard : la sélection gardée est `-1` ou une ligne sélectionnable) ; titre de 500 caractères avec caractères de contrôle : ligne de `width` colonnes, échéance gardée ; 500 tâches construites en moins de 100 ms.
- [ ] **Étape 2 : échec. Étape 3 : implémenter.** Ajouter les fichiers de test à la sélection mutmut.
- [ ] **Étape 4 : vérification complète ; commit** `git commit -m "feat(core): tasks tab model with filters, groups and due texts"`

---

### Task 7 : détail de tâche, reports rapides et texte collé (cœur)

**Fichiers :**
- Créer : `src/meute/core/task_detail.py`, `src/meute/core/task_postpone.py`, `src/meute/core/task_prompt.py`
- Test : `tests/test_task_detail.py`, `tests/test_task_postpone.py`, `tests/test_task_prompt.py`

**Interfaces :**
- `task_detail_lines(task: Task, *, notes: Sequence[Note], sessions: Sequence[Session], repo: Repo | None, now: datetime, home: Path | None, width: int) -> list[StyledLine]`, sept lignes au plus :
  - `─ #{id} {title} ` complété de `─` jusqu'à `width` (`ACCENT`) ;
  - `Status   {status_text} · priority {priority} · due {format_due} ({due_short})` (parties inconnues omises, retard en `LATE`) ;
  - `Project  {name}` ou `Project  floating`, puis ` · repo {display_path}` si `repo` ;
  - `About    {première ligne de la description}` si non vide (`one_line`, coupé à la largeur) ;
  - `Notes    {HH:MM} {body}` pour les deux notes les plus récentes, la seconde alignée sous la première ; heure si la note est d'aujourd'hui, sinon `{Mon DD}` ;
  - `Sessions {sym} {title} {state}` séparées par ` · ` (sessions liées, symboles de la fiche).
- `Postpone(Enum)` : `HOUR = "+1h"`, `TONIGHT = "tonight 6pm"`, `TOMORROW = "tomorrow 9am"`, `MONDAY = "Monday 9am"`, `CLEAR = "clear"` ; `postpone(choice: Postpone, now: datetime) -> Due | None` selon la décision 7 (heure murale du fuseau de `now`, trou d'heure d'été décalé d'une heure comme `parse_due`).
- `task_prompt(task: Task, notes: Sequence[Note]) -> str` : `#{id} {title}`, puis, si non vide, une ligne vide et la description, puis, s'il y a des notes, une ligne vide, `Notes:` et une ligne `- {body}` par note, de la plus ancienne à la plus récente ; chaque partie passe par `printable(…, keep_newlines=True)` ; pas de retour à la ligne final.

- [ ] **Étape 1 : tests qui échouent** : détail complet et minimal (instantané `syrupy`) ; `postpone` le mercredi 10:30 (`NOW`), à 18:30, à 23:59, le lundi à 8:00 et à 9:00, la veille du passage à l'heure d'été (2026-03-28 et 29, Europe/Paris), `CLEAR` → `None` ; `task_prompt` exact sur une tâche à description multiligne et deux notes ; **point de vigilance 1** : titre `x\x1b[201~\r` et note `y;` → le résultat ne contient ni `\x1b` ni `\r`, et finit par `y;`.
- [ ] **Étape 2 : échec. Étape 3 : implémenter.** Sélection mutmut.
- [ ] **Étape 4 : vérification complète ; commit** `git commit -m "feat(core): task details, quick postpones and the Claude prompt text"`

---

### Task 8 : données et actions de tâches du tableau **[sécurité]**

**Fichiers :**
- Modifier : `src/meute/core/board_view.py` (`BoardData`, actions), `src/meute/cli/board_data.py`, `src/meute/cli/board_backend.py`, `src/meute/core/status_line.py`, `src/meute/cli/status_publish.py`
- Créer : `src/meute/core/db/task_reads.py`, `src/meute/core/session_project.py`
- Test : `tests/test_db_task_reads.py`, `tests/test_session_project.py`, `tests/test_board_backend_tasks.py`, `tests/test_status_line_overdue.py`

**Interfaces :**
- `latest_notes(db: Database, *, per_task: int = 2) -> dict[TaskId, list[Note]]` (une requête, fonction de fenêtre `ROW_NUMBER() OVER (PARTITION BY task_id ORDER BY created_at DESC, id DESC)`, paramètres liés) ; `project_repo_ids(db: Database, project_id: ProjectId) -> list[RepoId]` (table `project_repos`, par `repo_id`).
- `session_project(session: Session, *, projects: Sequence[ProjectRef], repos: Mapping[RepoId, Repo]) -> ProjectRef | None` (décision 4).
- `BoardData` gagne `tasks: tuple[Task, ...] = ()` (ouvertes et terminées aujourd'hui : `list_tasks(TaskFilter(include_done=True))` filtré par `bucket_of`), `notes: Mapping[TaskId, tuple[Note, ...]]`, `project_refs: tuple[ProjectRef, ...] = ()`, `displayed_project: ProjectRef | None = None`.
- Actions (union `TaskAction`, ajoutée à `BoardAction`) : `CreateTask(text: str, project: ProjectRef | None)`, `ChangeTask(task_id: TaskId, version: int, patch: TaskPatch)`, `AddNote(task_id: TaskId, body: str)`, `DeleteTask(task_id: TaskId, version: int)`, `LaunchOnTask(task_id: TaskId)` (exécutée au Task 13 ; ici elle lève `InvalidInput("not available yet")`). `CreateTask` analyse `text` par `parse_quick_add` à l'heure du backend ; `@nom` inconnu → `InvalidInput("unknown project: {nom}")` ; `@none` → tâche volante.
- `VersionConflict` remonte tel quel (c'est un `MeuteError`) : la TUI en fait le message du Task 10.
- `status_text(displayed, attention, five_hour_pct, overdue: int = 0)` : ajoute `{overdue} overdue` en dernière partie ; `publish_status` reçoit `overdue`.

- [ ] **Étape 1 : tests qui échouent** : `latest_notes` (trois notes → les deux dernières, ordre, tâches sans note absentes) ; `project_repo_ids` ; `session_project` (par id, par nom de dépôt, aucun) ; backend sur base en mémoire : créer avec et sans `@projet`, `@none`, projet inconnu refusé sans rien écrire, changement avec version périmée → `VersionConflict`, suppression, note, acteur `user/tui` dans l'historique ; `status_text(..., overdue=2)` finit par ` · 2 overdue`, et `overdue=0` ne change rien (les tests existants passent sans retouche).
- [ ] **Étape 2 : échec. Étape 3 : implémenter.** Sélection mutmut pour les tests du cœur.
- [ ] **Étape 4 : vérification complète ; commit** `git commit -m "feat: task data and actions for the board, overdue count in the status line"`

---

### Task 9 : onglet Tâches, lecture

**Fichiers :**
- Créer : `src/meute/tui/tasks_cursor.py`, `src/meute/tui/tasks_pane.py`
- Modifier : `src/meute/tui/tasks_tab.py`, `src/meute/core/board_view.py` (`TASKS_FOOTER`, `TASKS_KEYS_HELP`)
- Test : `tests/test_tui_tasks.py` (+ instantanés)

**Interfaces :**
- `TasksCursor` (modèle de `SessionsCursor`) : `↑↓`/`jk`, `f` fait défiler `ALL → THIS_PROJECT → FLOATING → ALL`, `g` bascule le regroupement, `Space ← →` replient, `Entrée` sur un en-tête replié le déplie.
- `TasksTab` : lignes d'onglets (`tabs_line(Tab.TASKS, …, totals=tasks_totals(...))`), ligne de filtres, liste, puis détail (`task_detail_lines`) sous un filet ; `Entrée` sur une tâche dont une session liée est vivante affiche la plus récente (`ShowSession`), sinon rien.
- `TASKS_FOOTER = "a add · s status · p priority · d postpone · e edit · o note · L Claude · ? keys"` ; `TASKS_KEYS_HELP` (4 lignes) :
  `↑↓ select · Enter show its session · Space ←→ fold · f filter · g group`
  `a add · s status · p priority · d postpone · e title · D description`
  `@ project · o note · L launch Claude on it · Del delete · Tab sessions`
  `? or Esc close this list`
- Le nombre de retards de la ligne d'onglets se voit aussi depuis l'onglet Sessions (`Tasks 2!`).

- [ ] **Étape 1 : tests qui échouent** : navigation, filtres, regroupement, repli ; `Entrée` sur une tâche liée à une session vivante → `ShowSession` ; instantanés `test_tasks_tab_60_columns`, `test_tasks_tab_100_columns`, `test_tasks_tab_empty` ; 500 tâches : `rebuild` puis dessin en moins de 100 ms sur le pilote Textual.
- [ ] **Étape 2 : échec. Étape 3 : implémenter.** Relire les instantanés contre la maquette « Onglet Tâches ».
- [ ] **Étape 4 : vérification complète ; commit** `git commit -m "feat(tui): tasks tab with filters, groups and details"`

---

### Task 10 : onglet Tâches, édition

**Fichiers :**
- Créer : `src/meute/tui/task_input.py`
- Modifier : `src/meute/tui/tasks_tab.py`, `src/meute/tui/board.py` (ligne de saisie et liste de choix docquées au-dessus du pied)
- Test : `tests/test_tui_task_edit.py`

**Interfaces :**
- `TaskInput` : un `Input` Textual (une ligne, préfixe `› `) et une `OptionList` courte, masqués hors édition. Pendant l'édition, `BoardApp.on_key` ne traite que `escape` (annule) ; `Entrée` valide. Les touches tapées n'atteignent jamais les contrôleurs.
- Touches sur une tâche : `s` → choix `todo · in progress · blocked · review · done` (`blocked` demande ensuite la raison, `Blocked reason: `) ; `p` → `urgent · high · normal · low` ; `d` → les cinq `Postpone` ; `e` → titre prérempli (`Title: `) ; `D` → description préremplie (`Description: `, une ligne) ; `@` → nom du projet (`Project (none: floating): `) ; `o` → `Note: ` ; `Del` → pied `Delete #{id} "{title}"? y: yes · any other key: no`. `a` (même sans tâche choisie) → `New task: ` avec, sous la ligne, l'aperçu du Task 11 (`quick_preview`), projet par défaut = `displayed_project`.
- Erreurs : `VersionConflict` → pied `#{id} was modified in the meantime: reloaded`, données relues, **la ligne reste ouverte avec le texte saisi** ; `InvalidInput` → `Error: …`, ligne ouverte.

- [ ] **Étape 1 : tests qui échouent** (pilote Textual et faux backend) : chaque touche envoie la bonne action avec la `version` lue ; `blocked` passe par la raison ; `Échap` n'envoie rien ; taper `x` ou `q` dans la ligne n'arrête ni ne détache rien ; **point de vigilance 4** : le faux backend lève `VersionConflict` au premier envoi → message, rechargement, texte gardé, second `Entrée` réussi ; `Del` puis `n` n'efface rien, `Del` puis `y` envoie `DeleteTask`.
- [ ] **Étape 2 : échec. Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète ; commit** `git commit -m "feat(tui): edit tasks from the tasks tab"`

---

### Task 11 : aperçu de la saisie rapide (cœur)

**Fichiers :**
- Créer : `src/meute/core/quick_preview.py`
- Test : `tests/test_quick_preview.py`

**Interfaces :**
- `ProjectChoice` : `Named(project: ProjectRef)`, `Displayed(project: ProjectRef)`, `Floating(explicit: bool)`, `UnknownProject(name: str, suggestion: str | None)`.
- `QuickPreview(title: str | None, project: ProjectChoice, priority: Priority, due: Due | None, error: str | None)` ; `can_create` vrai sans erreur.
- `quick_preview(text: str, *, now: datetime, default: ProjectRef | None, projects: Sequence[ProjectRef]) -> QuickPreview` : `parse_quick_add` ; `@none` (sans casse) → `Floating(explicit=True)` ; `@nom` → projet de ce nom (sans casse) ou `UnknownProject` avec `difflib.get_close_matches(nom, noms, n=1, cutoff=0.6)` ; sans `@` → `Displayed(default)` ou `Floating(explicit=False)`. Erreurs : titre vide → `empty title` ; projet inconnu → `unknown project` ; texte vide → aucune erreur, `title=None`.
- `preview_lines(preview: QuickPreview, now: datetime) -> list[StyledLine]` : `Title     {title}` (`TITLE`) ; `Project   {name}` (`KIND`) + `  (displayed session · @none: floating)` (`DIM`) pour `Displayed`, `Project   floating` (+ `  (no displayed session)` si non explicite), `Project   @{name}: unknown project` (`HIGH`) + ` ({suggestion}?)` ; `Priority  {value}` (au rôle `HIGH` / `WARN`, omise si `normal`) ; `Due       {format_due}` (omise sans échéance) ; puis `Enter create · Esc cancel` (`DIM`) ou `Cannot create: fix the project or use @none · Esc cancel` (`HIGH`), `Cannot create: empty title · Esc cancel`.

- [ ] **Étape 1 : tests qui échouent** : les deux exemples des maquettes (`Relire la PR #11 !! >tomorrow` avec projet affiché ; `Appeler le support @infar >tonight` avec les projets `infra`, `mods` → suggestion `infra`) ; `@none`, `@NONE` ; jeton `>bientôt` gardé dans le titre ; texte vide ; propriété : `quick_preview` ne lève jamais.
- [ ] **Étape 2 : échec. Étape 3 : implémenter.** Sélection mutmut.
- [ ] **Étape 4 : vérification complète ; commit** `git commit -m "feat(core): quick entry preview with project suggestion"`

---

### Task 12 : fenêtre `M-t` **[sécurité]**

**Fichiers :**
- Créer : `src/meute/tui/quick_task.py`, `src/meute/cli/task_quick.py`
- Modifier : `src/meute/tmux/conf.py` (`Keys.quick_task = "M-t"`, `quick_task_command`), `src/meute/core/config.py`, `src/meute/core/config_validate.py` (`keys.quick_task`), `src/meute/cli/tmux_env.py` (passe la commande), `src/meute/cli/__init__.py` (importe `task_quick` comme les autres modules de commandes ; la commande est déclarée sur `task_app`)
- Test : `tests/test_tui_quick_task.py`, `tests/test_cli_task_quick.py`, `tests/test_tmux_conf_quick.py` ; exception n° 12

**Interfaces :**
- `QuickTaskBackend` (protocole, dans `quick_task.py`) : `context() -> QuickContext(now, default: ProjectRef | None, projects: tuple[ProjectRef, ...])`, `create(text: str) -> Task` (lève `MeuteError`).
- `QuickTaskApp(backend)` : un cadre (`border: solid #3b8eea`, rouge `#f16c6c` quand l'aperçu a une erreur ou qu'une création échoue), en-tête `New task` (`ACCENT`) et à droite `in {projet}` (`DIM`) ou `floating`, le champ `› `, l'aperçu `preview_lines` mis à jour à chaque frappe ; `Entrée` crée si `can_create` et quitte avec le code 0 ; sinon ou en cas d'erreur, la fenêtre reste ouverte avec le texte et `Error: {message}` ; `Échap` quitte sans rien écrire.
- `meute task quick` (cachée) : ouvre le contexte, trouve la session affichée (`ID_OPTION` du panneau principal du serveur meute), en déduit `default` par `session_project` (Task 8), lance `QuickTaskApp` ; l'acteur des créations est `user/tui`.
- Configuration tmux : `bind -n {quick_task} display-popup -E -w 76 -h 12 -T "" "{commande}"`, la commande quotée pour `sh` et pour tmux comme `_run_shell` (fonction commune extraite, `#` doublés). `[keys] quick_task` validé par `_TMUX_KEY`, documenté dans le modèle de configuration ; commentaire « Quick task from anywhere ».

- [ ] **Étape 1 : tests qui échouent** : pilote Textual sur un faux backend — frappe → aperçu, `Entrée` crée et quitte, `Entrée` sur un projet inconnu ne crée rien et rend la bordure rouge, `MeuteError("database is locked")` → fenêtre ouverte, texte gardé, message ; `Échap` ; instantanés `test_quick_task_ok` et `test_quick_task_unknown_project` à 76 × 12 ; configuration : ligne exacte pour `M-t` et pour une touche configurée `M-T`, touche invalide `M-t;x` refusée par la validation ; **point de vigilance 5** sur serveur jetable : `display-popup` lancé deux fois → une seule fenêtre (la seconde commande échoue ou ne fait rien, sans erreur visible pour l'utilisateur), client de 60 colonnes → la fenêtre s'ouvre, sans session affichée → aperçu `floating (no displayed session)`.
- [ ] **Étape 2 : échec. Étape 3 : implémenter.** Régénérer `test_tmux_conf.ambr` au titre de l'exception n° 12 et le relire.
- [ ] **Étape 4 : essai sur serveur jetable** (bac à sable, `script` pour attacher un client, `send-keys M-t`, saisie, `Enter`, puis `meute task list` montre la tâche). **Vérification complète ; commit** `git commit -m "feat: M-t quick task popup from anywhere"`

---

### Task 13 : « launch Claude on this task » et collage **[sécurité]**

**Fichiers :**
- Modifier : `src/meute/tmux/panes.py` (`paste_text`), `src/meute/cli/session_launch_claude.py` (`ClaudeLaunch.task_id`), `src/meute/cli/board_backend.py` (`LaunchOnTask`), `src/meute/tui/board.py` et `tasks_tab.py` (worker, `L`), `tests/fake_claude/claude` (mode `paste`, aide de test)
- Créer : `src/meute/cli/task_launch.py`
- Test : `tests/test_tmux_paste.py`, `tests/test_task_launch.py`, `tests/test_tui_task_launch.py`

**Interfaces :**
- `paste_text(tmux: Tmux, pane: PaneId, text: str, *, private_dir: Path) -> None` : fichier temporaire `0600` dans `private_dir` (`tempfile.mkstemp`), `load-buffer -b meute-paste-{pane sans %} {fichier}`, `paste-buffer -p -d -b … -t {pane}`, fichier supprimé dans un `finally`.
- `task_launch_folder(task: Task, repos: Mapping[RepoId, Repo], project_repos: Sequence[RepoId]) -> Path` : dépôt de la tâche, à défaut le premier dépôt de son projet ; sinon `InvalidInput("#{id} has no repository: set one on the task or its project")`.
- `launch_on_task(ctx, env, task_id, environ, *, monotonic, sleep) -> bool` : lance Claude (titre `one_line(f"#{id} {title}", 40, ellipsis=True)`, `task_id` enregistré dans la session, dépôt de `task_launch_folder`), l'affiche, attend que `claude_details` de la session ait un `native_id` (hook `SessionStart`) en relisant toutes les 0,2 s jusqu'à `READY_TIMEOUT_SECONDS = 10.0`, attend `PASTE_DELAY_SECONDS` (valeur du Task 1), colle `task_prompt(task, notes)` sans `Entrée` ; renvoie `False` si Claude n'est pas prêt à temps (la session reste lancée). Connexion SQLite propre au worker, comme `_stop`.
- TUI : `L` dans l'onglet Tâches lance l'action dans un worker ; pied `Launching Claude on #{id}…`, puis `#{id}: prompt not pasted (Claude not ready after 10 s)` quand le résultat est `False`. Le statut de la tâche ne change pas.
- Faux `claude`, mode `MEUTE_FAKE_CLAUDE_SCRIPT=paste` : rejoue `_START`, active le collage entre crochets (`\x1b[?2004h`), passe le terminal en mode brut et ajoute tout ce qu'il lit au fichier `MEUTE_FAKE_CLAUDE_INPUT`.

- [ ] **Étape 1 : tests qui échouent** : `paste_text` sur serveur jetable avec un `cat -v` dans le panneau : texte multiligne finissant par `;` et contenant `#{pane_id}` arrivé tel quel, aucun fichier laissé dans `private_dir` ; `task_launch_folder` (trois cas) ; `launch_on_task` avec le faux `claude` en mode `paste` : le fichier d'entrée vaut exactement `\x1b[200~` + texte (retours à la ligne sous la forme relevée au Task 1) + `\x1b[201~`, **sans `\r` ni `\n` après le marqueur de fin** ; faux `claude` sans `SessionStart` (mode `end`) et horloge simulée → `False` après 10 s, session présente ; tâche sans dépôt → `InvalidInput`, rien lancé ; **point de vigilance 1** de bout en bout : un titre contenant `\x1b[201~` n'ajoute aucun marqueur de fin supplémentaire dans le fichier d'entrée.
- [ ] **Étape 2 : échec. Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète ; commit** `git commit -m "feat: launch Claude on a task and paste its text without sending it"`

---

### Task 14 : documentation, mutation, relectures et PR

**Fichiers :**
- Modifier : `docs/superpowers/specs/2026-10-15-meute-design.md` (§ 9.5 et 9.6 : décisions 4, 5 et 7, formats gardés, collage par fichier), `docs/superpowers/plans/2026-10-15-meute-v1-roadmap.md` (plan 4b fait, ce qui reste au 4c), `src/meute/cli/welcome.py` si l'accueil liste les raccourcis globaux (`M-t`), `README.md` (raccourcis)
- Créer : `docs/dev/mutants/2026-plan-4b-python.md`

- [ ] **Étape 1 : mutation** : `uv run mutmut run --max-children 4` puis `uv run mutmut results` ; tuer les survivants utiles par des tests dans `tests/test_mutants_plan4b.py`, justifier les autres dans le rapport (même forme que `2026-plan-4-python.md`).
- [ ] **Étape 2 : `/simplify` sur la branche** (src et tests, sans instantanés ni docs), puis **`/security-review`** (SQL de `task_reads.py`, `display-popup` et sa commande, `paste_text` et son fichier, texte collé, entrées de la ligne de saisie). Corriger, en TDD.
- [ ] **Étape 3 : essai scripté** sur serveur jetable avec le faux `claude` : onglets, création par `a` et par `M-t`, `s`, `d`, `Del`, `L` en mode `paste` ; tableau des résultats dans le rapport de mutation, comme au plan 4. Liste d'essais manuels pour l'auteur (vrai Claude, vrai terminal) dans la description de la PR.
- [ ] **Étape 4 : vérification complète ; commit** `git commit -m "docs: plan 4b mutation report, spec and roadmap"` ; pousser la branche ; PR `feat: visual pass, tasks tab and M-t quick entry (plan 4b)` assignée à `gaetinux`, corps en français avec les exceptions n° 9 à 12 et la liste d'essais manuels.
