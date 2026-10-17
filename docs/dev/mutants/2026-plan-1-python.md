# Rapport de mutation — plan 1 Python (socle et tâches)

Commande : `uv run mutmut run --max-children 4` puis `uv run mutmut results` (mutmut 3.8.0, 1635 mutants, environ 25 s). Un seul passage complet, sans réduction de périmètre.

Configuration (`[tool.mutmut]` de `pyproject.toml`) :

- `source_paths = ["src/meute/core/"]` : seul le cœur est muté.
- `also_copy = ["tests/", "src/meute/"]` : les tests et le reste du paquet sont copiés dans `mutants/`.
- `pytest_add_cli_args = ["-n", "0"]` : pas de xdist (neutralise le `-n auto` d'`addopts`).
- `pytest_add_cli_args_test_selection` : uniquement les tests en processus du cœur (`test_config*`, `test_db_*`, `test_due_parse`, `test_instants`, `test_migrations`, `test_paths`, `test_quick_add`, `test_render`, `test_status`, `test_task_model`, `test_views`, `test_mutants_*`). Les tests de la CLI, de garde, d'`importtime` et d'`_entry` passent par un sous-processus qui ne voit pas les mutants : ils sont exclus.

| | tués | survivants | sans test | délais | suspects |
|---|---|---|---|---|---|
| Avant | 1403 | 205 | 27 | 0 | 0 |
| Après | 1546 | 89 | 0 | 0 | 0 |

Les 27 « sans test » (`project_to_json`, `note_to_json`, `utc_now`) n'étaient couverts que par les tests de la CLI en sous-processus. `mutmut` a ajouté `textual` (dépendance de `mutmut`) au verrou ; la licence est MIT.

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
| | `test_title_update_keeps_the_project_and_logs_only_the_title` | `project_id=None` dans `_fields_of` et `apply_patch` |
| | `test_description_update_is_recorded_under_its_name` | clé `description` de `_event_values` |
| | `test_moving_to_an_unknown_project_names_it` | `project_must_exist(None)` dans `update_task` |
| | `test_corrupt_rows_say_what_was_expected` | messages de `_text` et `_integer` |
| | `test_task_row_reads_every_column_from_its_own_position` | indices et conversion de `repo_id`, `created_at` dans `row_to_task` |
| | `test_event_row_keeps_task_id_and_instant` | `task_id` et `created_at` de `row_to_event` |
| | `test_note_row_keeps_its_own_id` | indice de `id` dans `row_to_note` |
| `tests/test_mutants_config.py` | `test_defaults_when_every_section_is_empty` | valeurs par défaut de `validate_config` |
| | `test_a_section_must_be_a_table` | message de `_section` |
| | `test_integer_bounds_are_inclusive_and_explained` | `<`/`>` et bornes de `_int`, messages, noms de clés, bornes de `validate_config` |
| | `test_explicit_values_are_read_from_their_own_key` | arguments supprimés dans `validate_config` |
| | `test_roots_permission_mode_and_timezone_messages` | messages de `_roots`, `_permission_mode`, `_timezone` |
| | `test_every_key_reads_its_default`, `test_config_get_reads_the_keys_of_the_file` | clés de `_flatten` |
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

La preuve « rouge » est le second passage de `mutmut` : chaque mutation ci-dessus survivait ou n'avait pas de test avant, et est tuée après (donc le test échoue sur le mutant et passe sur le code réel).

## Survivants restants, justifiés (89)

Aucun ne touche un comportement observable.

- **Casse des mots-clés SQL ou des pragmas (49)** : `select`/`SELECT`, `where`/`WHERE`, `pragma foreign_keys = on`, `rollback`, `vacuum into`… SQLite ignore la casse des mots-clés, des noms de tables et de colonnes. Dans `db/` (projets, tâches, notes, mise à jour, historique, migrations, connexion, `insert_event`).
- **Branches défensives inatteignables (12)** : `projects.create_project` (« inserted project not found », 4 mutants : l'insertion qui vient de réussir se relit toujours) ; `connection.pragma` (`if row else ""`, 2 : un `PRAGMA` nommé valide renvoie toujours une ligne) ; `migrations.current_version` (`if row else 0`, `isinstance(version, int)`, 4 : `PRAGMA user_version` renvoie toujours un entier) ; `lastrowid or 0` dans `create_task` et `add_note` (2 : `lastrowid` n'est jamais 0 après un `INSERT`) ; `VersionConflict(None)` après `rowcount == 0` dans `update_task` (1 : sous `BEGIN IMMEDIATE`, la version vient d'être vérifiée, donc la mise à jour touche toujours une ligne).
- **Équivalents par construction (14)** : `apply_patch` `or True` (le titre passé est déjà `title or current.title`) ; `diff_tasks` `strict=None/False/absent` (3 : les deux listes ont toujours six éléments) ; `list_tasks` sans le cas `AnyProject` (le `match` n'a alors aucune branche, ce qui revient à `pass`) ; `row_to_task` `(repo_id is None) and False` et `task_to_json` `(task.due is None) and False` (`RepoId(None)` renvoie `None` et `due_to_json(None)` renvoie `None` : `NewType` est l'identité et le `match` n'a pas de cas) ; `views.is_overdue` `is_open(None)` (`bucket_of` ne renvoie `OVERDUE` que pour une tâche non terminée, donc `is_open` est déjà vrai) ; `due_parse._delta` `astimezone(None)` (`DueAt` normalise de toute façon en UTC) ; `rpartition` pour `partition` dans `config._int` et `config_key` (les clés n'ont qu'un point) ; `paths.from_env` `get(variable, None / sans défaut / "XXXX")` (3 : une valeur absente, vide ou relative donne le même chemin par défaut) .
- **Dépendant de l'environnement (14)** : `encoding="UTF-8"` pour `"utf-8"` (3, le nom d'encodage ignore la casse) ; `encoding=None`/absent dans `write_atomic`, `load_config`, `_load_migrations`, et `ensure_ascii=None` dans `config_get` (équivalents sous une locale UTF-8 ; `None` est faux comme `False`) ; `delete=None`, `delete=True` ou absent dans `write_atomic` (le fichier temporaire est déjà renommé quand le gestionnaire se ferme, et la suppression d'un fichier absent est ignorée) ; `_load_migrations` `key=None`, `key=lambda f: None`, sans `key`, et `resources.files(None)` (une seule migration existe, donc aucun tri n'est comparé, et `files(None)` désigne le paquet appelant, le même). Les mutations de tri deviendront détectables avec la deuxième migration.

Les cinq fichiers explicitement visés par le plan (`quick_add.py`, `due_parse.py`, `views.py`, `config.py`, `db/`) n'ont aucun survivant sans justification ci-dessus.
