# Rapport de mutation — plan 2 Python (tmux, dépôts et sessions Bash)

Commande : `uv run mutmut run --max-children 4` puis `uv run mutmut results` (mutmut 3.8.0, 2547 mutants, environ 50 s). Passage complet après `rm -rf mutants`, sur le code de la branche `feat/plan-2-python` à la fin de la Task 13.

Configuration (`[tool.mutmut]` de `pyproject.toml`) : `source_paths = ["src/meute/core/", "src/meute/git/", "src/meute/tmux/parse.py", "src/meute/tmux/conf.py"]` (mutmut 3.8 accepte des fichiers). Les autres modules de `tmux/` (`client.py`, `panes.py`, `layout.py`, `names.py`, `errors.py`) lancent tmux en sous-processus ou nécessitent un serveur réel : ils ne sont pas mutés, leurs tests passent par un serveur tmux de test. La liste blanche de tests contient les fichiers ajoutés par les Tasks 1 à 8 et `tests/test_mutants_plan2.py`.

| | mutants | tués | survivants | sans test | délais | suspects |
|---|---|---|---|---|---|---|
| Premier passage | 2547 | 2382 | 165 | 0 | 0 | 0 |
| Après `tests/test_mutants_plan2.py` | 2547 | 2412 | 135 | 0 | 0 | 0 |

Sur les 135 survivants, 88 sont ceux du plan 1 (déjà justifiés dans `2026-plan-1-python.md`, y compris deux `... and False` de `row_to_task` et `task_to_json`) et 47 viennent du code du plan 2, tous justifiés ci-dessous.

## Tests ajoutés (aucun test existant modifié)

Tous dans `tests/test_mutants_plan2.py`.

| Test | Mutations tuées |
|---|---|
| `test_reconcile_goes_on_after_an_ended_session` | `continue` remplacé par `break` dans `reconcile` |
| `test_session_json_ended_at_is_null_while_live` | `ended_at` toujours formaté dans `session_to_json` |
| `test_session_keeps_project_repo_and_task_in_their_own_columns` | indices 3, 4, 5 permutés dans `_row_to_session` (les identifiants du test sont distincts) |
| `test_session_without_links_reads_none` | liens absents lus comme présents |
| `test_repos_carry_their_database_ids` | `id` perdu ou `RepoId(None)` dans `_row_to_repo` |
| `test_corrupt_text_column_says_what_was_expected` (repos et sessions) | message et exception de `_text` |
| `test_unknown_session_names_the_session_and_the_id` | entité et identifiant de `NotFound` dans `_require` et `find_session` |
| `test_worktree_pointer_file_with_invalid_utf8_is_still_read` | encodage et `errors="replace"` retirés ou faussés dans `_main_repo_of_worktree` |
| `test_fastapi_is_only_looked_for_in_the_first_megabyte` | `read(None)` dans `_mentions_fastapi` |
| `test_pane_line_errors_name_the_field_and_the_line` | messages de `_int_field` et `parse_pane_line`, noms de champs « exit status » et « width » |
| `test_tmux_escape_only_touches_backslash_quote_and_dollar` | caractères parasites ajoutés à l'ensemble échappé de `_tmux_escape` |

`test_discovery_goes_on_after_a_root_that_cannot_be_resolved` documente le comportement mais ne tue pas son mutant (voir plus bas).

## Survivants restants du plan 2, justifiés (47)

- **`case _: assert_never(x)` (16)** : `board_view` (`entry_key`, `enter_action`, `new_action`, `stop_target`) et `session_state` (`state_id`, `is_live`, `state_label`, `state_to_json`) ; le `case _` supprimé ou `assert_never(None)`. La branche est inatteignable : le `match` est exhaustif sur nos unions (garanti par pyright), elle n'existe que pour le typage.
- **Casse des mots-clés SQL, tables et colonnes (20)** : `repos.sync_repos` (4) et `list_repos` (2), `sessions.create_session` (10) et `set_session_state` (4). SQLite ignore la casse.
- **`encode("UTF-8")` / `decode("UTF-8")` (4)** : `create_session`, `_is_walkable`, `_main_repo_of_worktree`, `_mentions_fastapi` ; le nom de l'encodage ignore la casse. `decode(errors="replace")` sans nom d'encodage (1) est équivalent : UTF-8 est la valeur par défaut. `is_dir(follow_symlinks=None)` (1) est équivalent : `None` est faux comme `False`.
- **`(x is None) and False` (3)** dans `_row_to_session` (`project_id`, `repo_id`, `task_id`) : la condition devient fausse, donc `ProjectId(None)`, `RepoId(None)`, `TaskId(None)` ; `NewType` est l'identité, le résultat est le même `None`.
- **`parse_session_id` `parsed = ""` au lieu de `None` (1)** : `str("") != text.lower()` est toujours vrai, donc la même `InvalidInput` est levée.
- **`discover` `continue` remplacé par `break` sur une racine illisible (1)** : `Path.resolve()` sans mode strict ne lève presque jamais (les boucles de liens symboliques sont résolues sans erreur sous Python 3.13) ; la branche ne se déclenche que sur une erreur du système de fichiers qu'on ne peut pas provoquer de façon portable dans un test.
