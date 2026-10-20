# Rapport de mutation — plan 4b Python (passe visuelle, onglet Tâches, `M-t`)

Commande : `rm -rf mutants && uv run mutmut run --max-children 4` puis `uv run mutmut results` (mutmut 3.8.0, 6889 mutants, environ 4 min). Même configuration que les plans précédents (`[tool.mutmut]` de `pyproject.toml`). La liste blanche gagne `tests/test_mutants_plan4b.py` (depuis scindé en `test_mutants_plan4b_tasks.py` et `test_mutants_plan4b_sessions.py`) et trois fichiers du plan qui exercent des modules mutés en processus : `test_sessions_cards.py`, `test_card_marks.py` et `test_tmux_conf_quick.py` (la ligne `M-t` de `conf.py`). Les tests du TUI, de `meute.cli` et des sessions tmux ne voient pas les mutants et n'y sont pas.

| | mutants | tués | survivants | sans test |
|---|---|---|---|---|
| Plan 4 (rapport précédent) | 5011 | 4733 | 278 | 0 |
| Plan 4b, premier passage | 6889 | 6239 | 503 | 147 |
| Plan 4b, avec les trois fichiers ajoutés à la liste blanche | 6889 | 6363 | 410 | 116 |
| Plan 4b, après `tests/test_mutants_plan4b.py` | 6889 | 6572 | 317 | 0 |

Les 147 mutants « sans test » du premier passage venaient de fonctions que seuls les tests du TUI appelaient (`details_card`, `board_totals`, `tab_at`, les textes du pied du tableau…) : ils n'avaient donc aucune couverture visible de mutmut. Les tests de `test_mutants_plan4b_*.py` les appellent directement.

Les 255 survivants de `main` au plan 3 sont ceux des plans 1 à 3, déjà justifiés. En comparant les survivants par fonction, le plan 4b (et le plan 4 avant lui) en ajoute 69 et en retire 7 (`_make_private_file` réécrit au plan 4, `entry_key` et `_peak` remplacés) : 317 au total. Les 69 sont justifiés ci-dessous ; 9 d'entre eux (`_crossing_seconds`, `_current_cycle`, `_bool`) et 10 autres (`needs_attention`, `line_entry`, `line_info`, SQL de `quota_history`) sont déjà justifiés dans le rapport du plan 4 et sont repris ici parce que la comparaison se fait avec `main` au plan 3.

## Essai scripté

Faux `claude` (`tests/fake_claude/claude`, `tests/fake_claude` en tête du `PATH` ; jamais le vrai), serveur tmux jetable `meute-test-t14-<horodatage>` (`-L`, `TMUX_TMPDIR=/tmp/m14`, `HOME` et `XDG_*` sous le dossier de travail de la session, `SHELL=/bin/sh`), 61 dépôts `git init` sous `~/git` (dont `w`, rattaché à un projet `w` par `project_repos` car la CLI n'a pas de commande pour ce lien). Un client de 140×40 est attaché par `script -qfc 'stty cols 140 rows 40; exec tmux … attach' /dev/null`, dont l'entrée standard est un tube nommé : les touches globales (`M-t`) et la molette y sont envoyées comme un terminal le ferait (`\et`, `\e[<65;100;10M`), les autres touches par `send-keys` dans le panneau du tableau. Ni le serveur `meute` ni `default` n'ont été touchés ; le serveur est tué et son dossier supprimé par son chemin exact à la fin.

| Étape | Résultat |
|---|---|
| `meute layout sync`, client attaché | code 0 ; tableau dans le panneau de droite, onglet Sessions : `0 live`, `⚡ PEAK (~6h left)`, `▶ Without session (61)` (replié, car plus de 5 dépôts) |
| molette sur la liste Sessions, groupe replié | rien ne bouge (une seule ligne sélectionnable, rien à faire défiler) |
| `Space` (déplier), puis 6 crans de molette vers le bas | la liste défile : l'écran passe de `repo01…` à `repo10…` ; la barre de défilement bouge ; 6 crans vers le haut ramènent le haut de la liste. Le contrôle reporté de la Task 10 (`#sessions` n'est plus focalisable) est donc bon : la molette défile sans focus |
| `Tab` | onglet Tâches : `1 open`, filtres `all · this project (none) · floating`, `▶ No due date (1)`, pied `a add · s status · d postpone · o note · L Claude · ? keys` |
| `a`, `Trial by a !! >tomorrow` | aperçu sous la liste : `Title Trial by a`, `Project floating (no displayed session)`, `Priority urgent`, `Due tomorrow`, `Enter create · Esc cancel` ; pied `Enter confirm · Esc cancel` |
| `Enter` | tâche #2 créée : `▼ Upcoming (1)` `· !! Trial by a (floating) tomorrow`, titre de l'onglet `2 open` |
| `M-t` (par l'entrée du client), `Trial by M-t @none`, `Enter` | la tâche #3 `Trial by M-t` existe (`meute task list`), le tableau passe à `3 open` sans que l'utilisateur ait quitté l'onglet. Le contenu de la fenêtre flottante n'est pas lisible par `capture-pane` (elle est dessinée par le client) ; la création prouve qu'elle s'est ouverte, a reçu la saisie et s'est fermée |
| `s` | liste `todo · in progress · blocked · review · done` et `Enter confirm · Esc cancel` ; `Down`, `Enter` : `» !! Trial by a` et `Status in_progress` |
| `d` | liste `+1h · tonight 6pm · tomorrow 9am · Monday 9am · clear` ; `Enter` sur `+1h` : la tâche passe dans `▼ Today (1)` avec l'heure locale (`3:48pm` pour 14:48 + 1 h CEST), identique à `meute task list` après le correctif ci-dessous |
| `Del` | `Delete #2 "Trial by a"? y: yes · any other key: no` ; `y` : la tâche disparaît, `2 open`, `meute task list` ne montre plus que #1 et #3 |
| `Space` sur `No due date`, `Up` jusqu'à #1, `MEUTE_FAKE_CLAUDE_SCRIPT=paste`, `L` | pied `Launching Claude on #1…` puis, au bout de moins de 8 s : `Sessions ○ #1 Launch me; ok; idle` dans le détail ; le filtre passe à `this project (w)` (la session affichée est celle du projet `w`) ; le faux `claude` a reçu `ESC[200~#1 Launch me; ok;ESC[201~`, sans retour chariot : le texte, qui se termine par `;`, est collé tel quel et non envoyé |
| nettoyage | `kill-server` ; `/tmp/m14` supprimé ; les sockets `meute` et `default` n'ont pas bougé |

**Un bogue trouvé, corrigé en TDD (commit `fix(board): show task times in the local zone`).** Au premier passage, une échéance `+1h` à 15:46 s'affichait `1:46pm` dans le tableau et `3:46pm` dans `meute task list` : l'horloge du tableau venait de `db.now()`, qui est en UTC, et `bucket_of`, `format_due` et `format_clock` suivent le fuseau de `now`. Les heures du tableau et la frontière Aujourd'hui / À venir suivaient donc UTC. `load_board_data` renvoie maintenant `clock.astimezone(local_zone(environ))` ; le test `test_the_board_clock_is_in_the_local_zone` (fuseau `Asia/Kathmandu`) échouait au rouge avec un décalage de 0 au lieu de 5 h 45.

**Écarts relevés, sans correctif (à trancher par l'auteur)** :
- le détail d'une tâche écrit `Status in_progress` (identifiant interne) là où la liste de choix écrit `in progress` ;
- pendant la saisie de `a`, le pied du tableau et la dernière ligne de l'aperçu disent presque la même chose (`Enter create · Esc cancel` puis `Enter confirm · Esc cancel`) ;
- la CLI n'a pas de commande pour rattacher un dépôt à un projet : « launch Claude on this task » n'est donc utilisable, pour l'instant, que pour une tâche qui a un `repo_id` ou un projet lié à un dépôt par la base.

## Tests ajoutés (aucun test existant modifié)

Tous dans `tests/test_mutants_plan4b_tasks.py` et `tests/test_mutants_plan4b_sessions.py`.

| Test | Mutations tuées |
|---|---|
| `test_fit_*` | rôle de l'ellipse, largeur 0, `room == 1`, remplissage seulement quand il y a un écart (`styled.fit`, `_pad`, `_cut`) |
| `test_a_due_today_shows_its_clock_in_the_zone_of_now`, `test_a_note_written_today_in_the_zone_of_now_shows_its_clock`, `test_next_monday_is_computed_in_the_zone_of_now` | `astimezone(None)` (fuseau du système au lieu de celui de `now`) dans `_today_text`, `_note_when`, `_monday`, vérifiés avec Asia/Kathmandu (+05:45) et Pacific/Kiritimati (+14) |
| `test_task_detail_roles`, `test_a_floating_task_says_so_in_dim` | tous les rôles de l'état, du projet, des notes et des sessions du détail d'une tâche |
| `test_a_done_task_with_a_due_has_no_short_due_in_its_detail` | `and` devenu `or` dans `_status` |
| `test_the_information_lines_of_the_tasks_tab_are_dim`, `test_project_groups_keep_going_after_a_task_that_is_not_listed` | rôle des lignes d'information, `continue` devenu `break` dans `_project_groups` |
| `test_an_empty_entry_still_shows_the_default_project`, `test_a_title_less_entry_keeps_the_default_project_and_the_error`, `test_preview_roles` | projet par défaut perdu dans `quick_preview`, rôles de chaque ligne de l'aperçu de `M-t` |
| `test_the_tab_under_a_column`, `test_the_overdue_count_appears_from_one`, `test_board_totals_sum_what_the_sessions_reported` | bornes de `tab_at`, seuil `overdue > 0`, totaux du tableau (durées et coûts partiels) |
| `test_card_first_line_roles`, `test_needs_you_and_reference_lines`, `test_the_title_keeps_one_column_when_only_one_is_left`, `test_clip_keeps_a_single_column`, `test_card_more_lines_roles`, `test_sections_and_information_lines_are_dim` | rôles des cartes, marque `▶`, bornes de `_with_title` et de `clip`, rôle du titre coupé avec sa ligne |
| `test_details_card_roles`, `test_a_session_card_is_a_one_line_title` | règle et lignes de la fiche (`_rule`, `_row`, `details_card`) |
| `test_every_state_has_an_attention_reason` | états sans raison particulière dans `attention_reason` |
| `test_task_texts_of_the_footer_name_the_task_and_neutralise_the_title`, `test_prompt_not_pasted_keeps_its_task_and_message`, `test_ended_notice_only_for_an_ended_session_without_a_pane` | textes du pied (`confirm_delete_text`, `conflict_text`, `launching_text`, `ended_text`), `PromptNotPasted`, conditions de `ended_notice` |
| `test_session_project_is_the_own_project_else_the_repository_name` | projet propre, puis nom du dépôt, insensible à la casse |
| `test_folding_a_group_forgets_that_it_was_expanded`, `test_the_status_line_says_overdue_from_one`, `test_sections_are_keyed_by_their_title`, `test_the_hint_without_sessions_*`, `test_board_sessions_default_width_is_the_board_width` | `with_fold`, seuil de `status_text`, clé des sections, indice « No sessions » suivi du reste, largeur par défaut du tableau |
| `test_quota_bars_show_every_time_in_the_given_zone`, `test_a_window_that_resets_exactly_now_is_over` | fuseau des heures des barres de quota et rôle de `resets`, borne `<=` de `current_quota` |

## Survivants restants du plan 4b, justifiés (69)

- **`assert_never` retiré ou remplacé par `assert_never(None)` (30)** : `needs_attention`, `line_entry`, `line_info`, `ended_notice`, `fold_key`, `line_key`, `attention_reason`, `state_role`, `_late_text`, `_today_text`, `_keep`, `build_tasks_view`, `tasks_line_key`, `postpone`, `_project_line` (2 chacun). Branche inatteignable par construction : le `match` est exhaustif et pyright le vérifie.
- **Casse du SQL (8)** : `latest_metrics_by_session` (2), `quota_history` (4) et `project_repo_ids` (2). SQLite ignore la casse des mots-clés, tables et colonnes.
- **`_late_text`, `case None` (3)** : la branche `None` (retirée ou renvoyant `XXlateXX` / `LATE`) est inatteignable, car une tâche n'est en retard (`Bucket.OVERDUE`) que si elle a une échéance.
- **Mutants équivalents (19)** :
  - `age_text` `/` au lieu de `//` (3) et `duration_text` `max(ms, 1)` (1) : `int()` tronque pareil pour une valeur positive ; sous 1000 ms, `1 // 1000` vaut 0 comme `0 // 1000`.
  - `fit` `width < 0` au lieu de `<= 0` (1) : à 0, `room < 1` mène à `_pad(_cut(left, 0), 0)`, qui est aussi vide.
  - `tab_at` `next(names, )` au lieu de `next(names, None)` (1) : il n'y a jamais plus de segments d'onglet que d'onglets.
  - `postpone` `+1h` avec `astimezone(None)` au lieu de `astimezone(UTC)` (1) : même instant, et `DueAt` compare des instants.
  - `_peak_parts` sans `second=0`, `minute=1` ou `second=1` (3) : seule l'heure du résultat est lue (`.hour`), et aucun fuseau n'a un décalage qui fasse changer d'heure pour une minute ou une seconde.
  - `keep_tasks_selection` `(old_group is None) and False` (1), `session_project` `(repo_id is None) and False` (1), `_group_lines` `(repo_id is not None) or True` (1) : `repos.get(None)` vaut `None`, comme la branche remplacée, et `"group:None"` ne désigne aucun groupe.
  - `due_short` `bucket is UPCOMING or task.due is not None` (1) : les autres seaux sont traités avant, et `NO_DUE` n'a pas d'échéance.
  - `resolve_quick_project` sans `n=1`, sans `cutoff` ou avec `n=2` (3) : `close[0]` est le meilleur candidat dans les trois cas ; `quick_preview` `projects=None` pour un texte vide (2) : sans `@`, la liste des projets n'est pas lue.
- **Repris du plan 4 (9)** : `_crossing_seconds` (6), `_current_cycle` (2) et `_bool` `rpartition` (1), justifiés dans `2026-plan-4-python.md`.

## À essayer à la main (vrai terminal, vrai Claude)

La liste est dans le rapport de la tâche et dans la description de la PR.
