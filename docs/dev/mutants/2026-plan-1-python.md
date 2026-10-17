# Rapport de mutation — plan 1 Python (socle et tâches)

Commande : `uv run mutmut run --max-children 4` puis `uv run mutmut results` (mutmut 3.8.0, 1646 mutants, environ 26 s). Un seul passage complet, après `rm -rf mutants`, sur le code après la passe de simplification (`deff904`) et les correctifs de fin de branche.

Configuration (`[tool.mutmut]` de `pyproject.toml`) :

- `source_paths = ["src/meute/core/"]` : seul le cœur est muté.
- `also_copy = ["tests/", "src/meute/"]` : les tests et le reste du paquet sont copiés dans `mutants/`.
- `pytest_add_cli_args = ["-n", "0"]` : pas de xdist (neutralise le `-n auto` d'`addopts`).
- `pytest_add_cli_args_test_selection` : liste **explicite** (une liste blanche) des tests rejoués : `test_config*`, `test_db_*`, `test_due_parse`, `test_instants`, `test_migrations`, `test_paths`, `test_quick_add`, `test_render`, `test_status`, `test_task_model`, `test_views`, `test_mutants_*`. Les tests de la CLI, de garde, d'`importtime` et d'`_entry` passent par un sous-processus qui ne voit pas les mutants : ils sont exclus. **Les plans suivants doivent ajouter à cette liste chaque nouveau fichier de test du cœur** (par exemple `tests/test_context.py` n'y figure pas volontairement : il teste `meute.cli`) ; sinon ces tests ne tuent aucun mutant et les mutants du nouveau code apparaissent « sans test ».

| | mutants | tués | survivants | sans test | délais | suspects |
|---|---|---|---|---|---|---|
| Avant (premier passage, début du plan) | 1635 | 1403 | 205 | 27 | 0 | 0 |
| Après les tests ajoutés (rapport précédent, avant `deff904`) | 1635 | 1546 | 89 | 0 | 0 | 0 |
| Code actuel, avant les deux derniers tests | 1646 | 1556 | 90 | 0 | 0 | 0 |
| Code actuel, après | 1646 | 1558 | 88 | 0 | 0 | 0 |

Les 27 « sans test » du premier passage (`project_to_json`, `note_to_json`, `utc_now`) n'étaient couverts que par les tests de la CLI en sous-processus. `mutmut` a ajouté `textual` (dépendance de `mutmut`) au verrou ; la licence est MIT.

## Tests ajoutés (aucun test existant modifié)

| Fichier | Test | Mutations tuées |
|---|---|---|
| `tests/test_mutants_db.py` | `test_migration_files_are_loaded_in_order_as_sql_text` | mutations de `_load_migrations` (le chargement n'a lieu qu'à l'import) |
| | `test_open_creates_missing_parent_folders` | `parents` supprimé, `None` ou `False` dans `Database.open` |
| | `test_connections_commit_each_statement_themselves` | `autocommit=True` retiré de `open` et de `in_memory` |
| | `test_open_hands_its_path_to_the_migration` | `migrate(conn, None)` dans `open` |
| | `test_pragma_rejects_bad_names_with_a_message` | message et exception de `Database.pragma` |
| | `test_project_description_defaults_to_empty_and_keeps_all_columns` | défaut `"XXXX"`, colonnes `description`, `instructions`, `created_at` perdues ou décalées dans `row_to_project` |
| | `test_empty_project_name_message` | message de `create_project` |
| | `test_task_created_with_a_due_stores_it` | `due_columns(None)` dans `create_task` |
| | `test_title_update_keeps_the_project_and_logs_only_the_title` | `project_id=None` dans `_fields_of` et `_apply_patch` |
| | `test_description_update_is_recorded_under_its_name` | clé `description` de `_event_values` |
| | `test_moving_to_an_unknown_project_names_it` | `project_must_exist(None)` dans `update_task` |
| | `test_corrupt_rows_say_what_was_expected` | messages de `_text` et `as_integer` |
| | `test_task_row_reads_every_column_from_its_own_position` | indices et conversion de `repo_id`, `created_at` dans `row_to_task` |
| | `test_event_row_keeps_task_id_and_instant` | `task_id` et `created_at` de `row_to_event` |
| | `test_note_row_keeps_its_own_id` | indice de `id` dans `row_to_note` |
| `tests/test_mutants_config.py` | `test_defaults_when_every_section_is_empty` | valeurs par défaut de `validate_config` |
| | `test_a_section_must_be_a_table` | message de `_section` |
| | `test_integer_bounds_are_inclusive_and_explained` | `<`/`>` et bornes de `_int`, messages, noms de clés, bornes de `validate_config` |
| | `test_explicit_values_are_read_from_their_own_key` | arguments supprimés dans `validate_config` |
| | `test_roots_permission_mode_and_timezone_messages` | messages de `_roots`, `_permission_mode`, `_timezone` |
| | `test_every_key_reads_its_default`, `test_config_get_reads_the_keys_of_the_file` | clés de `_flatten` |
| | `test_load_config_decodes_utf8` | encodage de `load_config` |
| | `test_non_string_timezone_gets_the_same_message` | `InvalidInput(None)` pour un fuseau qui n'est pas une chaîne dans `_timezone` |
| | `test_atomic_write_stages_the_temporary_file_next_to_the_target` | `dir=` retiré ou `None` dans `write_atomic` |
| | `test_failed_atomic_write_cleans_up_even_if_the_temporary_file_is_gone` | `missing_ok` de `write_atomic` |
| `tests/test_mutants_model.py` | `test_utc_now_is_aware_and_in_utc` | `datetime.now(None)` |
| | `test_naive_datetime_is_refused_with_a_message` | message de `to_db` |
| | `test_invalid_zoned_time_names_the_text` | deux messages de `parse_zoned` |
| | `test_blocked_without_reason_message`, `test_config_error_exposes_its_path_and_reason` | message de `Blocked`, attributs de `ConfigError` |
| | `test_ensure_dirs_can_run_twice` | `exist_ok` de `Paths.ensure_dirs` |
| | `test_a_one_o_clock_time_is_accepted` | `1 <= hour` de `_weekday_time` |
| | `test_due_at_is_normalised_to_utc_whatever_the_system_zone` | `astimezone(None)` et message de `DueAt` |
| | `test_due_from_json_rejects_unknown_shapes_with_a_message` | `or` pour `and`, trois messages de `due_from_json` |
| | `test_task_json_*`, `test_note_json`, `test_project_json` | clés, valeurs et `format_instant` des trois sérialiseurs |
| | `test_a_later_time_on_a_future_day_is_upcoming_not_today` | `or True` dans `_bucket_of_due` |
| | `test_days_are_read_in_the_zone_of_now_not_the_system_zone` | `astimezone(None)` dans `bucket_of`, `_bucket_of_due`, `format_due` (le fuseau du processus est fixé à Auckland) |
| | `test_a_date_due_sorts_at_the_last_second_of_the_day` | `time(23, 59)` dans `_due_instant` |
| | `test_done_status_is_built_from_its_kind` | branche `DONE` supprimée de `status_from_kind` |

La preuve « rouge » est le second passage de `mutmut` : chaque mutation ci-dessus survivait ou n'avait pas de test avant, et est tuée après (donc le test échoue sur le mutant et passe sur le code réel).

## Survivants restants, justifiés (88)

Aucun ne touche un comportement observable.

- **Casse des mots-clés SQL ou des pragmas (42)** : `select`/`SELECT`, `where`/`WHERE`, `insert into`, `returning`, `pragma foreign_keys = on`, `pragma user_version`, `rollback`, `vacuum into`, noms de tables et de colonnes en majuscules… SQLite ignore la casse des mots-clés, des noms de tables et de colonnes. Dans `db/` (`tasks`, `task_update`, `projects`, `connection`, `rows` avec `insert_event`, `migrations`, `task_notes`).
- **Branches défensives inatteignables (19)** : `rows.inserted_id` (5 : message et `RuntimeError(None)` quand `lastrowid` vaut `None`, ce qui n'arrive jamais après un `INSERT` réussi) ; `projects.create_project` (5 : message de « INSERT returned no row » quand `INSERT ... RETURNING` ne renvoie rien, impossible puisque l'insertion vient de réussir) ; `connection.pragma` (`if row else ""`, 2 : un `PRAGMA` nommé valide renvoie toujours une ligne) ; `migrations.current_version` (`if row else 0` devenu `or True` ou `1`, 2 : `PRAGMA user_version` renvoie toujours une ligne) ; `task_update.update_task` (5 : sous `BEGIN IMMEDIATE`, la version vient d'être vérifiée, donc la garde `rowcount == 0` ne se déclenche jamais ; la relecture `fetch_task(conn, task_id)` de `VersionConflict(...)` qu'elle contient n'est jamais exécutée, d'où `None`, arguments `None`, supprimés ou permutés. Le chemin `VersionConflict` réel, avec une version périmée, est testé et tué plus haut dans la fonction).
- **Équivalents par construction (13)** : `diff_tasks` `strict=None/False/absent` (3 : les deux listes ont toujours six éléments) ; `list_tasks` sans le cas `AnyProject` (1 : le `match` n'a alors aucune branche, ce qui revient à `pass`) ; `row_to_task` `(repo_id is None) and False`, `task_to_json` `(task.due is None) and False` et `_event_values` `(task.due is None) and False` (3 : avec la condition mutée, `None` passe à `RepoId(None)`, `due_to_json(None)` ou `due_text(None)` ; `NewType` est l'identité et un `match` sans cas correspondant renvoie `None`, donc le résultat est le même `None`); `due_parse._delta` `astimezone(None)` (1 : `DueAt` normalise de toute façon en UTC) ; `rpartition` pour `partition` dans `config._int` et `config_key` (2 : les clés n'ont qu'un point) ; `paths.from_env` `get(variable, None / sans défaut / "XXXX")` (3 : une valeur absente, vide ou relative donne le même chemin par défaut).
- **Dépendant de l'environnement (14)** : `encoding="UTF-8"` pour `"utf-8"` dans `load_config`, `write_atomic` et `_load_migrations` (3, le nom d'encodage ignore la casse) ; `encoding=None`/absent dans `write_atomic` et `_load_migrations`, et `ensure_ascii=None` dans `config_get` (4, équivalents sous une locale UTF-8 ; `None` est faux comme `False`) ; `delete=None`, `delete=True` ou absent dans `write_atomic` (3 : le fichier temporaire est déjà renommé quand le gestionnaire se ferme, et la suppression d'un fichier absent est ignorée) ; `_load_migrations` `key=None`, `key=lambda f: None`, sans `key`, et `resources.files(None)` (4 : une seule migration existe, donc aucun tri n'est comparé, et `files(None)` désigne le paquet appelant, le même). Les mutations de tri deviendront détectables avec la deuxième migration.

Les cinq fichiers explicitement visés par le plan (`quick_add.py`, `due_parse.py`, `views.py`, `config.py`, `db/`) n'ont aucun survivant sans justification ci-dessus. `views.is_overdue` s'écrit désormais `bucket_of(...) is Bucket.OVERDUE` : le survivant `is_open(None)` a disparu avec la simplification.
