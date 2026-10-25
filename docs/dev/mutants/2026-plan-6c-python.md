# Rapport de mutation — plan 6c Python (préparation de la V1)

Commande : `rm -rf mutants && uv run mutmut run --max-children 4` puis `uv run mutmut results` (mutmut 3.8.0, 9760 mutants, environ 9 min). Même configuration que les plans précédents (`[tool.mutmut]` de `pyproject.toml`) : `src/meute/core/` est déjà dans `source_paths`, donc `core/doctor.py`, `read_schema_version` (`core/db/schema.py`), `launch_project_id` (`core/session_project.py`) et la purge de `session_events` (`core/db/claude_sessions.py`) sont mutés sans changement. La liste blanche gagne les tests du plan qui exercent le cœur en processus : `test_doctor_core.py`, `test_db_schema_readonly.py`, `test_launch_project_choice.py`, `test_purge_events.py` (la purge sur une base temporaire, et le démarrage du tableau par `CliRunner` avec une purge qui échoue), et le nouveau `tests/test_mutants_plan6c.py`. Les tests qui passent par tmux, des sous-processus ou la CLI de `doctor` (`test_launch_project.py`, `test_launch_project_orphan.py`, `test_cli_doctor.py`, `test_cli_doctor_files.py`) ne voient pas les mutants et n'y sont pas ; `meute.cli` n'est d'ailleurs pas muté (`cli/doctor.py`, `cli/launch_project.py`).

| | mutants | tués | survivants | sans test |
|---|---|---|---|---|
| Fin du plan 6b (chiffres du rapport 6b) | 9447 | 8930 | 450 | 67 |
| Plan 6c, premier passage | 9760 | 9189 | 499 | 72 |
| Plan 6c, après `tests/test_mutants_plan6c.py` | 9760 | 9234 | 459 | 67 |

Le plan ajoute 313 mutants. Au premier passage, 49 survivants étaient dans son code (39 dans `core/doctor.py`, 8 dans `read_schema_version`, 2 dans la purge) ; `launch_project_id` n'en laissait aucun. Les 5 mutants « sans test » de plus sont ceux de `capture_board` (`core/state_capture.py`), née du dernier refactor du plan 6b (`777c672`), après sa passe de mutation : seuls la CLI et le tableau l'appelaient. Ils sont désormais tués, et les 67 « sans test » restants sont exactement ceux de `main`. Les 450 autres survivants sont exactement ceux du rapport 6b, justifiés dans les rapports des plans 1 à 6b.

## Tests ajoutés (aucun test existant modifié)

Tous dans `tests/test_mutants_plan6c.py` (17 cas). Ils tuent 45 mutants du premier passage.

| Test | Mutations tuées |
|---|---|
| `test_tmux_lines_are_named_tmux`, `test_git_lines_are_named_git`, `test_claude_lines_are_named_claude`, `test_a_missing_option_line_is_named_options`, `test_database_lines_are_named_database` | le nom d'une ligne de `doctor` (`None`, `XXtmuxXX`, `TMUX`…) faussé dans une branche `fail` ou `warn` (36) : les tests du plan ne vérifiaient que le niveau ou le texte de ces branches, et l'instantané de la CLI, qui montre les noms, ne voit pas les mutants |
| `test_a_closed_database_in_a_read_only_folder_is_read` | `read_schema_version` : le mode `mode=ro&immutable=1` remplacé par `None` ou mis en majuscules (2). Une ouverture qui n'est pas `immutable` d'une base WAL fermée doit créer `-wal` et `-shm` ; dans un dossier en lecture seule elle échoue (`attempt to write a readonly database`), et le test le voit. Après coup, une ouverture en lecture et écriture ne laisse aucun fichier : le test du plan (`test_wal_database_leaves_no_new_file`) ne pouvait pas la distinguer |
| `test_the_wal_of_a_vanished_writer_is_left_as_it_is` | `read_schema_version` : `mode=ro` (base avec `-wal`) faussé en `XXmode=roXX` ou `MODE=RO` (2), c'est-à-dire une ouverture en lecture et écriture : à sa fermeture, elle verse le `-wal` laissé par un écrivain disparu dans la base et l'efface. Le test copie une base ouverte (comme un écrivain tombé la laisse) et vérifie que rien ne change |
| `test_capture_board_captures_in_the_board_order` | `capture_board` : ses arguments supprimés ou remplacés par `None` (5, « sans test ») |

## Survivants restants du plan 6c, justifiés (9)

- **Casse du SQL (2)** : la suppression de `session_events` de `purge_samples` en minuscules ou en majuscules. SQLite ne distingue pas la casse des mots-clés ni des identifiants ; mutants équivalents, comme aux plans précédents.
- **`uri=True` de `read_schema_version` (3)** : `uri=None`, `uri=False` ou l'argument retiré. Le SQLite de Python est compilé avec `SQLITE_USE_URI` : une chaîne `file:` est lue comme une URI dans tous les cas. Mutants équivalents sur cette plateforme ; l'argument reste, pour un SQLite compilé autrement.
- **`XXmode=ro&immutable=1XX` (1)** : la requête devient `XXmode=ro` (paramètre inconnu, ignoré) et `immutable=1XX`, que SQLite lit comme vrai (il ne garde que le nombre en tête) ; une base `immutable` n'est jamais écrite. Mutant équivalent.
- **Préfixe des versions illisibles (2)** : `shown_version(output, "XXXX")` au lieu de `""` dans `_unreadable` et pour la version de claude. Le texte ne change que pour une sortie qui commence par `XXXX` ; quasi équivalents, sans intérêt à fixer.
- **Première ligne vide de `parse_version` (1)** : `""` remplacé par `"XXXX"` pour une sortie vide ; aucune version ne se lit dans `XXXX`, le résultat reste `None`. Mutant équivalent.

## Essai scripté

Faux `claude` (`tests/fake_claude/claude`, script `done`, en tête du `PATH`, devant `.venv/bin` ; jamais le vrai), précédé d'une enveloppe d'essai qui répond seulement à `--version` (`2.1.302 (Claude Code)`) et à `--help` (les six options), le faux `claude` n'y répondant pas. Serveur tmux jetable `-L meute-trial-p6c-b80f8b6f` (`TMUX_TMPDIR` dans un dossier court `/tmp/claude-1000/t6c.cuPi`), `HOME`, `XDG_*` (config, data, state, cache), `SHELL=/bin/sh`, `GIT_CONFIG_NOSYSTEM=1` et l'identité Git épinglés dans un dossier d'essai pour **toutes** les commandes, serveur tmux compris. Deux dépôts `git init` neufs, `~/git/alpha` et `~/git/beta` (un commit chacun), et un dossier `~/notes`. Le tableau tourne dans son panneau (`meute layout sync`), sans client attaché : touches par `tmux send-keys`, écran lu par `capture-pane`, base lue en lecture seule (`mode=ro`) sauf pour les deux écritures SQL de l'essai. Ni le serveur `meute` ni `default` n'ont été touchés, même en lecture ; le serveur jetable est tué (`kill-server`, vérifié : « no server running », aucun processus restant) et les dossiers d'essai supprimés par leur chemin exact.

| Cas | Action | Résultat |
|---|---|---|
| 1. `doctor` sur une machine neuve, faux `claude` seul | `meute doctor` (`HOME` vide, aucun dossier XDG) | `ok tmux 3.5a`, `ok git 2.47.3`, `warn claude unreadable version:` (le faux `claude` écrit son refus sur stderr), `fail options claude --help does not list: --settings, --mcp-config, --session-id, --resume, --permission-mode, --append-system-prompt`, `ok config … (absent: defaults are used)`, `warn database …: created at the first start`, `ok state …`, `ok server tmux server meute-trial-p6c-b80f8b6f: not running (meute starts it)`, la `note`, `3 problems found` ; code 1, en 0,17 s. `find` avant et après : **rien n'est créé** |
| 1 bis. Même machine, avec l'enveloppe | `meute doctor` | `ok claude 2.1.302 (Claude Code)`, `ok options claude --help lists every option meute uses`, le reste inchangé, `1 problem found` (le `warn` de la base) ; code 0 ; rien n'est créé |
| 2. `meute` puis `c` dans `alpha` | `meute layout sync`, puis `c` sur la ligne `alpha` de `Without session` | `meute project list` vide avant, `alpha` après ; `meute project show alpha` : `repos: alpha …/git/alpha` ; la session a `project_id = 1`, `project_repos = [(1, 1)]` ; la carte est sous `▼ alpha · 1 live` |
| 2 bis. Second lancement dans `alpha` | `meute session new --kind bash` dans `~/git/alpha` | même projet (`project_id = 1`), aucun nouveau projet |
| 3. `L` sur une tâche d'un autre projet | `meute project add api`, `meute task add "Fix login @api"`, son `repo_id` mis sur `beta` en SQL (aucune commande ne fixe le dépôt d'une tâche), puis `Tab`, `→`, `↓`, `L` | la session `#1 Fix login` démarre dans `~/git/beta` avec `project_id` = `api` ; `meute project list` : `alpha`, `api`, **pas de `beta`** ; `project_repos` inchangé ; la carte est sous `▼ api · 1 live` |
| 3 bis. Lancement ordinaire ensuite dans `beta` | `meute session new --kind bash` dans `~/git/beta` | le projet `beta` est créé et lié à `beta` (`api` n'était pas lié au dépôt, conforme à la règle) |
| 3 ter. Dossier hors dépôt | `meute session new --kind bash` dans `~/notes` | `project_id` vide, aucun projet créé |
| 4. Événement vieilli | `created_at` de l'événement 1 mis à maintenant − 31 jours, celui de l'événement 2 à − 29 jours (SQL), puis un nouveau tableau (`respawn-pane -k` du panneau du tableau) | 10 lignes de `session_events` avant, 9 après : l'événement de 31 jours **a disparu**, celui de 29 jours reste ; les 2 sessions restent |
| 5. `doctor` avec tout en place | `meute doctor`, serveur, base WAL ouverte par le tableau | huit `ok` (`config …/config.toml`, `database …/meute.db (schema 5)`, `server …: running, 2 sessions`), la `note`, aucune ligne de fin ; **code 0** ; aucun fichier ajouté à côté de la base |

Constats de l'essai, à trancher par le contrôleur :

1. **`running, <n> sessions` compte les sessions tmux**, pas les sessions de meute : avec deux, puis cinq sessions de meute, la ligne dit toujours `running, 2 sessions` (`meute` et `meute-bg`). Conforme au code (`list-sessions`) et à la conception (« serveur tmux `meute` en marche : `running, <n> sessions` »), mais un utilisateur lira sans doute le nombre de ses sessions. Piste : `running, 2 tmux sessions`, ou compter les panneaux étiquetés.
2. **`unreadable version:` vide** : un `claude` qui n'écrit rien sur stdout donne une ligne qui finit par `:`. Le texte fixé est respecté ; il ne dit pas que la sortie était vide.
3. **Dépôt d'une tâche** : rien n'écrit `tasks.repo_id` (ni commande, ni touche, ni outil MCP) ; `L` prend le dépôt de la tâche, sinon le premier dépôt de son projet, sinon celui qui porte son nom. Avec `L`, le cas « tâche de `api` lancée dans `web` » demande donc l'écriture SQL de l'essai ; en pratique, il vient du formulaire `N` (dépôt `web`, tâche de `api`), qui suit le même chemin (`launch_claude` avec `task_id`).
4. **Regroupement de deux dépôts** : aucune commande ne lie un dépôt d'un autre nom à un projet (seuls `create_repo_project`, par le nom, et la saisie `@dépôt` écrivent `project_repos`). Les deux dépôts d'un projet ne se rejoignent que s'ils portent le même nom dans deux racines. Signalé dans le README et la feuille de route.

## À essayer à la main (vrai terminal, vrai Claude)

À copier dans la PR. Dans un vrai terminal, avec le vrai `claude` :

1. **`meute doctor` sur sa machine** : chaque ligne est juste (versions de tmux, git, claude ; `options` en `ok` ; chemins en `~/…` ; `server` `running` si meute tourne, `not running` sinon) ; le code de sortie (`echo $?`) vaut 0 ; aucun fichier n'apparaît (`ls ~/.local/share/meute` avant et après). Puis, pour voir un `fail`, `PATH=/usr/bin:/bin meute doctor` (claude introuvable : `fail claude not found: Claude sessions are disabled`, pas de ligne `options`, code 1).
2. **Premier lancement dans un dépôt** : `c` sur un dépôt sans projet : la session reste dans le groupe du même nom, `meute project list` montre le projet, `meute project show <nom>` liste le dépôt ; le filtre `this project` de l'onglet Tâches et `M-t` (projet par défaut) le prennent ; un second `c` ne crée rien de plus. Un worktree (`N`, `Worktree new`) rejoint le même projet.
3. **Regroupement de deux dépôts dans un projet** : deux clones du même nom dans deux racines (`~/git/web` et `~/work/web`, `meute config set repos.roots '["~/git", "~/work"]'`) : un lancement dans l'un crée `web` et le lie aux deux ; un lancement dans l'autre le reprend. Puis `N`, dépôt `web`, une tâche du projet `api` : la session va sous `api`, aucun projet `web` n'est créé s'il n'existait pas. Dire si l'absence d'une commande pour lier un dépôt d'un autre nom (constat 4) gêne.
4. **Purge** : après un mois d'usage, le tableau démarre sans délai visible, et les sessions, tâches et états restent (seuls les relevés et les événements de plus de 30 jours partent).
5. **README** : le lire du début à la fin comme un nouvel utilisateur, de `uv tool install` à `meute doctor` puis `meute`.
