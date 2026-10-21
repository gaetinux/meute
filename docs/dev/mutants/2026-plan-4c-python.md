# Rapport de mutation — plan 4c Python (lancement depuis le tableau)

Commande : `rm -rf mutants && uv run mutmut run --max-children 4` puis `uv run mutmut results` (mutmut 3.8.0, 7797 mutants, environ 4 min). Même configuration que les plans précédents (`[tool.mutmut]` de `pyproject.toml`). La liste blanche gagne les fichiers du plan qui exercent des modules mutés en processus : `test_db_last_agent.py`, `test_last_agent.py`, `test_launch_form_busy.py`, `test_orphan_adoption.py`, `test_resume_target.py`, `test_db_reopen.py` (`test_launch_form.py`, `test_launch_form_view.py` et `test_db_repo_links.py` y étaient depuis les tâches 7 et 8) et le nouveau `tests/test_mutants_plan4c.py`. Les tests qui lancent tmux, `meute.cli` ou le TUI (`test_session_resume.py`, `test_orphan_actions.py`, `test_orphans.py`, `test_tmux_respawn.py`, `test_tui_*.py`, `test_sessions_orphans.py`) ne voient pas les mutants et n'y sont pas.

| | mutants | tués | survivants | sans test |
|---|---|---|---|---|
| `main` (fin du plan 4b), même configuration | 7059 | 6641 | 367 | 51 |
| Plan 4c, premier passage | 7797 | 7310 | 443 | 44 |
| Plan 4c, après `tests/test_mutants_plan4c.py` | 7797 | 7362 | 391 | 44 |

Les 51 puis 44 mutants « sans test » viennent de fonctions que seuls les tests du TUI ou de la CLI appellent (`choice_project_id`, `count_overdue`, `create_repo_project`, `project_refs`) : ils datent d'avant le plan 4c, aucun n'est dans du code du plan. Comparés par fonction à `main`, les survivants gagnent 24 (367 vers 391) ; les 24 sont justifiés ci-dessous. Les 367 de `main` sont ceux des plans 1 à 4b, déjà justifiés dans leurs rapports.

## Tests ajoutés (aucun test existant modifié)

Tous dans `tests/test_mutants_plan4c.py` (17 tests). Le premier passage laissait 443 survivants, dont 52 de moins après ces tests.

| Test | Mutations tuées |
|---|---|
| `test_an_unknown_default_mode_is_not_offered` | `_modes` : mode par défaut absent de `PERMISSION_MODES` (condition toujours vraie, `tuple(None)`) |
| `test_repositories_with_the_same_name_are_ordered_by_path` | clé de tri de `open_form` (chemin remplacé par `None`) |
| `test_moving_from_a_field_the_type_hides_starts_at_the_first_field` | `move` : champ absent des champs visibles (Bash sur `TASK`), indice de départ |
| `test_every_choice_and_edit_clears_the_error`, `test_choosing_another_repository_forgets_the_task`, `test_erase_drops_only_the_last_character` | `error=None` retiré de `choose`, `_choose_repo`, `type_text`, `erase` ; `task=None` retiré de `_choose_repo` ; `[:-1]` devenu `[:+1]` |
| `test_typed_text_keeps_one_space_at_each_edge` | les six mutants de `_clean` (espace de début et de fin) |
| `test_a_bash_launch_carries_its_title` | `title` oublié ou mis à `None` dans `form_action` (Bash) |
| `test_a_row_without_room_keeps_its_whole_value_and_role`, `test_the_current_field_label_is_titled_and_the_others_are_dim` | bornes `room > 0`, rôle de la valeur et du libellé de `_choice` |
| `test_a_claude_form_without_a_task_says_none`, `test_a_folder_not_canonical_is_shown_as_typed` | texte `none` de `_task_text`, `_folder_text` |
| `test_the_warning_expands_a_typed_home_and_is_a_warning` | `home` passé à `shares_folder`, rôle `WARN` de l'avertissement |
| `test_an_orphan_line_says_command_folder_and_state` | `orphan_line` : dossier vide, `dead` / `orphan` |
| `test_an_orphan_line_of_the_view_names_its_orphan`, `test_an_orphan_line_without_its_orphan_gives_no_entry` | `line_entry` sur une ligne d'orphelin (9 mutants), `_orphan_item` (`meute_id`), `line_key` |
| `test_repo_project_links_pair_each_repository_with_its_own_project` | `repo_project_links` : colonne lue pour le dépôt (identifiants de dépôt et de projet différents) |

Les tests existants de ces comportements (`test_sessions_orphans.py`, `test_orphans.py`, `test_tui_launch_form.py`) passent par le TUI ou tmux et ne sont pas vus par mutmut ; les nouveaux appellent le cœur directement.

## Survivants restants du plan 4c, justifiés (24 de plus que `main`)

- **`assert_never` retiré ou remplacé par `assert_never(None)` (14 de plus)** : `ended_text`, `_launch_place`, `resume_target`, et les branches `OrphanLine` de `line_key`, `line_entry` et `line_info`. Branche inatteignable par construction : le `match` est exhaustif et pyright le vérifie.
- **Casse du SQL (12)** : `last_agent_by_repo` (6), `reopen_session` (4), `repo_project_links` (2). SQLite ignore la casse des mots-clés, tables et colonnes. (`link_repo`, 2, est dans le même cas et était déjà compté sur `main`.)
- **Mutants équivalents (6 de plus que `main`, compensés par `new_action` et `parse_session_id`, qui n'y sont plus)** :
  - `open_form` (3) : `repo_id = ""` ou `task_id = ""` au lieu de `None`, et la branche `OrphanEntry() | None` retirée. Aucun dépôt ni tâche n'a l'identifiant `""`, et le `match` retombe sur les mêmes valeurs ;
  - `choose` (1) : `index - step` au lieu de `index + step` pour le type. Il n'y a que deux types, donc `±1` modulo 2 donne le même résultat ;
  - `_expanded` (2) : `~` seul avec `home / text[2:]` donne `home / ""`, soit `home` ; la condition `text != "~"` (toujours vraie ou comparée à un autre texte) ne change donc pas le chemin ;
  - `form_lines` (1) : `max(width - len(_HEADING), 1)` au lieu de `0` ; la ligne est ensuite coupée à `width`, le trait en trop disparaît.

## Essai scripté

Faux `claude` (`tests/fake_claude/claude`, en tête du `PATH` ; jamais le vrai), serveur tmux jetable `meute-test-t9-plan4c` (`-L`, `TMUX_TMPDIR` sous le dossier de travail de l'essai, `HOME` et `XDG_*` dans ce dossier, `SHELL=/bin/sh`), deux dépôts `git init` neufs sous `~/git` (`fresh` et `other`). Le tableau tourne dans son panneau (`meute layout sync`), sans client attaché : les touches sont envoyées par `tmux send-keys` dans ce panneau, l'écran lu par `capture-pane`, l'état par `meute session list` et `list-panes`. Ni le serveur `meute` ni `default` n'ont été utilisés (une seule lecture de `tmux -L meute list-sessions`, après la fin de l'essai, pour vérifier qu'il n'avait pas bougé) ; le serveur jetable est tué et son dossier supprimé à la fin.

| Cas | Touches | Résultat |
|---|---|---|
| `n` sur un dépôt neuf | `n` sur `fresh` (aucune session) | une session **Claude** `fresh` naît (`repo_id` 1, `cwd` du dépôt) ; le faux `claude` la fait passer en `permission` ; la section « Without session » ne garde que `other` |
| `N` en Bash avec un titre | `N` sur `other`, `→` (Bash), `Tab` ×3, `my shell`, `Entrée` | le formulaire montre `Type ◂ Bash ▸`, `Repo ◂ other ▸`, `Folder ~/git/other`, `Title my shell` et masque Task et Mode ; la session Bash `my shell` tourne dans `~/git/other` et s'affiche dans la zone principale |
| `r` sur une session terminée, sans panneau | `x`, `y` sur la session Claude, `e` pour montrer les terminées, `r` | la session passe `exited`, son panneau disparaît ; après `r`, **même id** (`940bca6a…`), nouveau panneau `%4`, état `permission` (le faux `claude` a reçu `--resume`, `SessionStart` avec `source=resume`) |
| `r` avec un panneau mort | session Claude lancée avec `MEUTE_FAKE_CLAUDE_SCRIPT=exit` (le faux `claude` quitte aussitôt), puis `r` | avant : `exited`, panneau `%5` mort ; après : même id, **même panneau `%5`**, vivant (`dead=0`), état `permission` |
| orphelin créé à la main, affiché | `new-window` dans `meute-bg` + `set-option -p @meute_id aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa` ; la section `Orphans (2)` liste `? sh  ~/git/other  orphan` ; `Entrée` | le pied devient `Enter show · a adopt · x close` ; le panneau `%6` est dans `meute:main` |
| orphelin adopté | `a` | `meute session list` montre `aaaaaaaa  other  running  ~/git/other` ; la section n'a plus que l'autre orphelin ; `session list --json` ne le liste plus dans `orphans` |
| second orphelin fermé | `x`, puis `y` (« Close orphan pane "sh"? ») | le panneau `%7` disparaît de tmux ; la section `Orphans` disparaît ; rien n'est écrit en base |
| nettoyage | `kill-server`, dossier supprimé | le serveur n'existe plus ; les sockets `meute` et `default` n'ont pas bougé |

Aucun bogue trouvé pendant l'essai. Un écart noté, sans correctif : sur l'écran capturé, rien n'indique dans le texte quelle ligne est sélectionnée (le marqueur `▶` est celui de la session affichée) ; l'essai a repéré la sélection par le titre de la fiche du bas.

## À essayer à la main (vrai terminal, vrai Claude)

À copier dans la PR. Dans un vrai terminal, avec le vrai `claude`, sur un dépôt sans importance :

1. **`n` sur un dépôt neuf** : le tableau lance Claude dans ce dépôt ; ensuite, lancer un Bash dans ce même dépôt (`N`, type Bash), puis `n` sur le dépôt : il lance Bash (dernier type du dépôt). `c` lance toujours Claude.
2. **`N` en Claude** : choisir un dépôt, une tâche du projet et un mode (`plan` par exemple) ; la session démarre avec ce mode (`/status` dans Claude) et le texte de la tâche est collé sans être envoyé. Taper un dossier avec `~`, un dossier inexistant, un chemin relatif et un dossier vide : les messages du formulaire restent lisibles et la saisie est gardée.
3. **Avertissement** : ouvrir `N` sur un dossier où une session vit déjà : `⚠ another live session works in this folder` s'affiche, et le lancement reste possible.
4. **`r` avec le vrai Claude** : arrêter une session (`x`, `y`) après un échange, appuyer sur `r` : Claude reprend la conversation (le message d'origine est affiché) et la session garde son titre, son dépôt et sa tâche. Refaire avec un panneau mort (laisser Claude se terminer seul avec `/exit`) : le panneau est réutilisé à la même place.
5. **`r` sur une conversation introuvable** : effacer le transcript de la session (`~/.claude/projects/…/<id>.jsonl`), puis `r` : Claude s'arrête aussitôt, la session repasse en `exited` et `r` est de nouveau possible, sans boucle.
6. **Touches répétées** : `r` deux fois de suite, `a` deux fois sur le même orphelin, `x` `y` puis `a` pendant la fermeture : une seule action part, aucune erreur visible.
7. **Orphelins** : lancer à la main un Claude marqué (`tmux set-option -p @meute_id <uuid>` sur un panneau de `meute-bg`) : l'adopter par `a`, vérifier que le prochain hook lui donne un `native_id` et qu'il passe à `idle` ou `running` ; fermer un orphelin Claude par `x` (double `C-c`).
8. **Terminal étroit** (mode étroit, moins de 100 colonnes) : le formulaire `N` tient dans le tableau et reste lisible.
9. **Relecture** : laisser le formulaire `N` ouvert plus de 2 s, pendant qu'une session change d'état : la saisie, le champ courant et l'avertissement ne bougent pas.
10. **Commande d'un vrai panneau Claude** : relever `tmux -L meute display-message -p -t <panneau> '#{pane_current_command}'` sur un panneau où tourne le vrai Claude : la commande peut être `node` (ou un nom de version) plutôt que `claude`. Marquer ce panneau en orphelin (point 7) et l'adopter par `a` : noter s'il est adopté comme Claude (état `unknown`, puis `native_id` au hook suivant) ou comme Bash (`orphan_agent` ne reconnaît que `claude`), et ce que fait alors `x` (un ou deux `C-c`).
