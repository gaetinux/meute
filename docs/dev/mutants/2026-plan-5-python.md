# Rapport de mutation — plan 5 Python (MCP et contexte composé)

Commande : `rm -rf mutants && uv run mutmut run --max-children 4` puis `uv run mutmut results` (mutmut 3.8.0, 8109 mutants, environ 5 min). Même configuration que les plans précédents (`[tool.mutmut]` de `pyproject.toml`). La liste blanche gagne les tests du plan qui exercent des modules mutés en processus : `test_mcp_data.py`, `test_composed_context.py`, `test_context_arg.py`, `test_claude_mcp_config.py`, `test_config_instructions.py`, `test_db_link_session.py`, et le nouveau `tests/test_mutants_plan5.py`. (`test_task_prompt.py` n'y est plus : le fichier est supprimé avec `core/task_prompt.py`, exception n° 25.) Les tests qui lancent le serveur MCP, la CLI, tmux ou le TUI (`test_mcp_server.py`, `test_mcp_backend*.py`, `test_mcp_stdio.py`, `test_mcp_command.py`, `test_launch_context.py`, `test_project_instructions.py`, `test_task_launch_work_on.py`) ne voient pas les mutants et n'y sont pas ; `meute.mcp` et `meute.cli` ne sont pas dans `source_paths`.

| | mutants | tués | survivants | sans test |
|---|---|---|---|---|
| `main` (fin du plan 4c), même configuration (chiffres du rapport 4c) | 7797 | 7362 | 391 | 44 |
| Plan 5, premier passage | 8109 | 7587 | 418 | 104 |
| Plan 5, après `tests/test_mutants_plan5.py` | 8109 | 7640 | 402 | 67 |

Les 67 mutants « sans test » viennent de fonctions que seuls les tests du TUI ou de la CLI appellent : `project_refs`, `create_repo_project`, `choice_project_id`, `count_overdue` (44, déjà dans le rapport 4c) et `next_live` (23, du plan « stopping the shown session shows the next one », entré dans `main` avant le plan 5 sans que `test_next_live.py` rejoigne la sélection). Aucun n'est dans du code du plan 5. Le premier passage en comptait 37 de plus : `set_project_instructions` et `project_repos`, que seule la CLI exerçait, désormais couvertes par des tests du cœur.

Les 402 survivants gagnent 11 sur `main` (391). Ceux du plan 5 sont 13, justifiés plus bas ; le reste de l'écart est du bruit d'autres fonctions (un survivant de plus ou de moins après chaque passage, les tests lents de la sélection étant sensibles à la charge). Les survivants de `main` sont ceux des plans 1 à 4c, justifiés dans leurs rapports.

## Tests ajoutés (aucun test existant modifié)

Tous dans `tests/test_mutants_plan5.py` (13 tests). Le premier passage laissait 418 survivants et 104 mutants sans test ; 53 mutants de moins sont sortis de ces deux colonnes grâce à ces tests (16 survivants, 37 sans test).

| Test | Mutations tuées |
|---|---|
| `test_the_mcp_config_follows_the_settings_and_a_text_context_precedes_the_name`, `test_a_file_context_uses_the_file_option` | `claude_argv` : condition de `--mcp-config`, son nom (casse, `XX`), sa valeur (`str(None)`) ; `_context_options` : nom de `--append-system-prompt` et de la variante fichier |
| `test_the_mcp_config_file_is_indented_by_two` | `write_mcp_config` : `indent` retiré, `None` ou 3 |
| `test_written_settings_carry_the_allowed_tools` | `write_settings` : `allowed_tools` oublié ou remplacé par `None` |
| `test_non_string_instructions_are_refused_with_their_key` | message de `_instructions` |
| `test_config_get_reads_the_instructions` | clé `claude.instructions` de `_flatten` (casse, `XX`) |
| `test_a_task_summary_without_a_due_says_null` | `task_summary_json` : `due` toujours calculé |
| `test_today_is_read_in_the_zone_of_now_not_the_machine_zone` | `_instant_matches` : fuseau de `now` remplacé par celui de la machine (`astimezone(None)`) ; `now` à UTC+14 pour que le fuseau de la machine ne puisse pas donner la même date |
| `test_linking_to_an_unknown_task_names_the_task` | `link_session_task` : entité et identifiant de `NotFound` |
| `test_project_instructions_are_set_returned_and_cleared`, `test_instructions_of_an_unknown_project` | `set_project_instructions` (23 mutants sans test) : valeur écrite, ligne renvoyée, effacement, `NotFound` |
| `test_a_project_lists_only_its_own_repositories` | `project_repos` (14 mutants sans test) : filtre par projet, colonne lue, projet sans dépôt |

## Survivants restants du plan 5, justifiés (13)

- **Casse du SQL (10)** : `link_session_task` (4), `set_project_instructions` (4), `project_repos` (2). SQLite ignore la casse des mots-clés, des tables et des colonnes.
- **`assert_never` remplacé (2)** : `_context_options` (branche retirée, `assert_never(None)`). Branche inatteignable par construction : le `match` est exhaustif et pyright le vérifie.
- **Mutant équivalent (1)** : `task_summary_json`, `None if (task.due is None) and False else due_text(task.due)`. Pour `due is None`, `due_text(None)` ne trouve aucune branche du `match` et renvoie `None` : même résultat.

## Essai scripté

Faux `claude` (`tests/fake_claude/claude`, script `paste`, en tête du `PATH` ; jamais le vrai), serveur tmux jetable `-L meute-trial-p5-8c1f` (`TMUX_TMPDIR` dans un dossier court sous `/tmp`, la limite des chemins de sockets Unix étant dépassée par le dossier de travail), `HOME`, `XDG_*` (config, data, state, cache) et `SHELL=/bin/sh` épinglés dans un dossier d'essai pour **toutes** les commandes, serveur tmux compris. Un dépôt `git init` neuf `~/git/fresh`, un projet `fresh` avec consignes (`meute project edit fresh --instructions …`), des consignes globales (`meute config set claude.instructions …`) et une tâche `#1`. Le tableau tourne dans son panneau (`meute layout sync`), sans client attaché : les touches sont envoyées par `tmux send-keys`, l'écran lu par `capture-pane`. Ni le serveur `meute` ni `default` n'ont été touchés, même en lecture ; le serveur jetable est tué (`kill-server`, vérifié : « no server running ») et son dossier de socket supprimé.

| Cas | Action | Résultat |
|---|---|---|
| `c` dans un projet avec consignes | `c` sur `fresh` | session `9d5f7951…`, argv enregistré par le faux `claude` : `--settings …/settings.json --mcp-config …/sessions/9d5f7951…/mcp.json --session-id … --permission-mode auto --append-system-prompt "<règle de résolution>\n\nGlobal instructions:\nGlobal rule: be terse.\n\nProject instructions (fresh):\nProject rule: write tests first." --name=fresh` ; pas de ligne de tâche (session sans tâche) |
| `mcp.json` | lecture du fichier | 0600 ; serveur `meute` de type stdio, commande `.venv/bin/python -m meute mcp`, `env` : `MEUTE_SESSION=9d5f7951…` (celle de la session) |
| `settings.json` | lecture | `permissions.allow` : les sept `mcp__meute__task_*`, dans l'ordre de `MEUTE_TOOLS` |
| `L` sur la tâche `#1` | `Tab` (onglet Tâches), `Entrée` (groupe), `Bas`, `L` | session `1533834a…` liée à `#1`, nommée `#1 Fix the thing …` ; octets reçus par le faux `claude` : `ESC[200~Work on task #1.ESC[201~` (collé, sans retour chariot) ; l'argv porte en plus « You are working on task #1. Read it with the `task_read` tool and report your progress with `task_note_add`. » |
| `meute mcp` par le client stdio du SDK (`MEUTE_SESSION=1533834a…`) | `list_tools`, `task_read {id:1}`, `task_note_add {id:1, body}`, `task_set_status {id:1, status:in_progress, expected_version:1}` | sept outils listés ; les trois appels sans `is_error` ; `task_read` renvoie la tâche complète (`version` 1) ; `{"note_id": 1}` ; `{"version": 2}` |
| Effet visible par la CLI | `meute task show 1` | `Status: in progress`, `Version: 2`, note `[…] claude: Trial note from the SDK client` |

Aucun bogue trouvé. Remarques sans correctif : `>today` et `!high` n'ont pas été reconnus par la saisie rapide de `meute task add "Fix the thing @fresh !high >today"` (le titre les garde, priorité `normal`, sans échéance) — la saisie rapide documentée est `title @project !! >tomorrow` ; mon essai a mal tapé la syntaxe, ce n'est pas un défaut du plan 5 ; l'essai du contexte de plus de 8 000 octets avec le fichier est couvert par `tests/test_launch_context.py`, pas rejoué ici.

## À essayer à la main (vrai terminal, vrai Claude)

À copier dans la PR. Dans un vrai terminal, avec le vrai `claude`, sur un dépôt sans importance, après avoir mis une consigne globale (`meute config set claude.instructions "Always answer in French."`) et une consigne de projet (`meute project edit <projet> --instructions "Start every answer with PROJ."`) :

1. **Les outils sont listés** : `c` sur le dépôt, puis `/mcp` dans Claude : `meute` est listé avec 7 outils (`✔ meute — 7 tools`), à côté des serveurs MCP de l'utilisateur, qui restent chargés.
2. **Lecture d'une tâche** : créer une tâche (`a` dans l'onglet Tâches), la lier au dépôt par son projet, `L` : Claude reçoit « Work on task #N. » (collé, non envoyé) ; `Entrée` : Claude appelle `task_read` **sans demande d'autorisation**, même en mode `manual` (`N`, mode `manual`), et résume la tâche.
3. **Ajout d'une note** : demander « add a note saying what you did » : `task_note_add` part sans autorisation ; la note apparaît dans le détail de la tâche (onglet Tâches, ou `meute task show N`) avec l'auteur `claude`.
4. **Changement de statut** : demander « mark the task in progress, then blocked because X » : `task_set_status` met la tâche à `in progress`, puis `blocked` avec la raison ; l'onglet Tâches se met à jour. Provoquer un conflit (modifier la tâche dans le tableau pendant que Claude travaille, puis lui demander de la mettre à `done`) : Claude relit la tâche (version actuelle donnée dans l'erreur) et réessaie.
5. **Le contexte composé est suivi** : demander « what are your instructions about language and the first word? » : Claude cite la consigne globale et celle du projet, et la règle de résolution (un `CLAUDE.md` du dépôt qui les contredit doit être signalé à l'utilisateur, pas tranché). Sur une session sans tâche, la ligne « You are working on task #N » est absente.
6. **Contexte de plus de 8 000 octets** : `meute config set claude.instructions "$(python3 -c 'print("Rule: say PINEAPPLE first. " * 400)')"`, puis `c` : le lancement passe par `--append-system-prompt-file` (vérifier : `<state>/meute/sessions/<id>/context.md` existe en 0600, et `ps` ne montre pas le texte) ; Claude suit la consigne. Remettre une consigne courte et `r` sur une session terminée : le contexte est recalculé et `context.md` disparaît.
7. **Reprise** : `r` sur une session terminée : `/mcp` y liste encore `meute`, et la session garde son lien avec la tâche.
8. **`task_create` et `task_link_session`** : demander à Claude de créer une tâche « follow-up » (elle prend le projet de la session) puis de s'y lier ; `meute task show` la montre, et la session apparaît liée dans le détail.
9. **Base verrouillée** : verrouiller la base un instant (`sqlite3 meute.db "BEGIN EXCLUSIVE;"` dans un autre terminal, sur une copie ou brièvement) et demander `task_read` : l'erreur dit `meute database unavailable: …`, et le serveur répond à l'appel suivant.
10. **Mode étroit et `?`** : l'aide des touches (`?`) de l'onglet Tâches décrit `L` comme collant « Work on task #N. ».
