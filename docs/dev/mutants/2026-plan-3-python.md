# Rapport de mutation — plan 3 Python (adaptateur Claude)

Commande : `uv run mutmut run --max-children 4` puis `uv run mutmut results` (mutmut 3.8.0, 4184 mutants, environ 2 min). Passage complet après `rm -rf mutants`, sur le code de la branche `feat/plan-3-python` à la Task 12.

Configuration (`[tool.mutmut]` de `pyproject.toml`) : `source_paths` couvre `src/meute/core/`, `src/meute/git/`, `src/meute/tmux/parse.py`, `src/meute/tmux/conf.py` et, nouveau, `src/meute/claude/`. `meute.ingest` et `meute.cli` ne sont pas mutés : leurs tests passent par un sous-processus ou un serveur tmux et ne voient pas les mutants. La liste blanche de tests reçoit les fichiers en processus ajoutés par les Tasks 1 à 11 ; la Task 12 y ajoute `tests/test_agents_poller.py`, `tests/test_refresh_stuck.py`, `tests/test_board_purge.py` (oubliés jusque-là) et `tests/test_mutants_plan3.py`.

| | mutants | tués | survivants | sans test | délais | suspects |
|---|---|---|---|---|---|---|
| Premier passage | 4184 | 3871 | 312 | 0 | 1 | 0 |
| Après `tests/test_mutants_plan3.py` | 4184 | 3961 | 223 | 0 | 0 | 0 |

Pour séparer l'hérité du nouveau, mutmut a aussi été lancé sur `main` (copie de travail jetable) : 137 survivants (le rapport du plan 2 en annonçait 135). Les diffs de mutation ont été comparés un à un : sur les 223 survivants restants, 136 sont ceux des plans 1 et 2, déjà justifiés dans `2026-plan-1-python.md` et `2026-plan-2-python.md` (dont 8 sur des lignes seulement déplacées ou retouchées par le plan 3 : `set_session_state` devenu `write_state`, `migrate` devenu `_migrate_locked`, l'`INSERT` de `create_session` qui gagne `permission_mode`) ; 87 viennent du code du plan 3, tous justifiés ci-dessous. Le 137e survivant hérité, `current_version` `else 1`, a été tué une fois au second passage alors que la branche est inatteignable : sans doute un échec ponctuel d'un test lent pendant ce mutant, à surveiller.

Le délai du premier passage était `run_agents` `wait(timeout=None)` (un `sleep 30` attendu sans fin) : le mutant est tué, par délai puis par `test_agents_default_timeout_is_two_seconds`.

## Essai réel avec Claude Code (Task 12, étape 1)

Vrai `claude` 2.1.302 (Opus 5.5), serveur tmux jetable `meute-test-trial-<uuid>`, base, configuration et état sous le scratchpad (`XDG_*`), dans ce dépôt (déjà approuvé dans Claude), mode de permission par défaut `manual`. Aucune permission demandée ni accordée.

| Étape | Résultat |
|---|---|
| `meute layout sync` | code 0 ; sessions `meute` (deux panneaux) et `meute-bg` |
| `meute session new --title trial` | `Launched: 010d0803 trial (~/git/poc-app-rust)` ; panneau `meute-bg:claude`, `claude` à l'écran |
| `session list` après démarrage | `unknown?` puis `idle` (hook `SessionStart`) ; `[manual]` affiché ; la session de l'auteur apparaît en `outside: busy` (via `claude agents --json`) |
| `Reply with the single word pong.` par `send-keys` | Claude répond `pong` ; `session list` affiche `waiting for your reply` en 3 s ; `last_message = pong` |
| `metric_samples` | 2 lignes ; la dernière : `Opus 5.5`, effort `medium`, contexte 4 %, 0,16 $, dépôt `github.com/gaetinux/meute` ; `quota_samples` : 1 ligne (5 h à 95 %, 7 j à 51 %) |
| `session_events` | `SessionStart` (`startup`), `UserPromptSubmit`, `Stop`, puis `SessionEnd` (`other`) après l'arrêt |
| Statusline dans le panneau (`capture-pane -p`) | `➜ gaetinux poc-app-rust │ Opus 5.5 │ █████ 5h 95% │ ✦ OFF-PEAK (weekend) │ …`, produite par `…/.venv/bin/python -m meute ingest statusline` (commande du `--settings`) |
| `meute session stop 010d0803 --yes` | `Stopped: 010d0803 trial`, état `exited`, `ended_at` renseigné, panneau fermé |
| Nettoyage | serveur tué (`kill-server`), son fichier de socket retiré par son chemin exact ; `/tmp/tmux-1000` ne contient que `default` ; aucun processus `tmux -L meute-test` ; `~/.claude/settings.json` inchangé (`md5sum -c` OK) ; `git status` propre ; pas de `ingest.log` (aucun échec d'ingestion) |

## Tests ajoutés (aucun test existant modifié)

Tous dans `tests/test_mutants_plan3.py`.

| Test | Mutations tuées |
|---|---|
| `test_path_key_wins_over_an_earlier_string` | clé de chemin de `tool_excerpt` perdue (`None`, `get(None)`, `get("")`) |
| `test_tool_without_name_or_input_is_empty` | nom d'outil absent remplacé par un texte dans `_tool` |
| `test_session_start_history_is_the_source` | clé `source` et valeur par défaut de l'historique de `_start` |
| `test_stop_keeps_newlines_and_has_no_history` | `keep_newlines` faussé ou retiré, historique non vide dans `_stop` |
| `test_prompt_has_no_history`, `test_prompt_permission_mode_is_written` | historique de `_prompt` ; colonne `permission_mode` faussée dans `apply_hook` |
| `test_metrics_round_trip_every_column` | colonnes `lines_*` et `worktree_*` perdues ou permutées dans `latest_metrics` |
| `test_corrupt_metric_number_says_what_was_expected` | condition, message et exception de `_as_real` |
| `test_session_events_default_to_the_latest_fifty` | limite par défaut de `session_events` |
| `test_unknown_claude_session_names_the_session` | entité et identifiant du `NotFound` de `get_claude_details` |
| `test_open_existing_missing_file_names_the_path`, `test_open_existing_uses_the_clock_and_autocommits` | `FileNotFoundError(None)`, `clock=None`, `autocommit` retiré dans `open_existing` |
| `test_stuck_after_minutes_can_be_read`, `test_chain_that_is_not_a_string_is_refused` | clé de `_flatten` ; message de `_chain` |
| `test_tz_with_a_leading_colon_is_the_zone`, `test_localtime_file_is_read_when_tz_is_unset` | `removesuffix` et préfixe faussé ; mode d'ouverture de `/etc/localtime` |
| `test_basename_keeps_trailing_capital_x`, `test_empty_cwd_has_an_empty_basename` | jeu de caractères de `rstrip` et cas du dossier vide dans `_basename` |
| `test_lines_of_one_are_shown_and_zero_is_not`, `test_lines_summing_to_zero_are_hidden` | bornes de `_lines` |
| `test_friday_morning_is_before_the_peak`, `test_friday_at_the_end_hour_is_the_weekend` | bornes du vendredi dans `_peak` |
| `test_peak_start_is_a_whole_hour_in_a_half_hour_zone`, `test_peak_start_of_twenty_four_is_midnight` | `minute=0` retiré, `% 25` dans `_peak` |
| `test_agents_runs_detached_with_its_arguments` | arguments `agents --json`, `stderr` et `start_new_session` de `start_agents` |
| `test_agents_output_is_decoded_leniently_and_capped` | `errors="replace"` faussé ou retiré, `read(None)` dans `finish_agents` |
| `test_agents_default_timeout_is_two_seconds` | délai par défaut et `wait(timeout=None)` de `run_agents` |
| `test_kill_agents_reaps_the_process` | `wait()` retiré dans `kill_agents` |
| `test_settings_file_is_indented_json` | `indent` faussé ou retiré dans `write_settings` |

## Survivants restants du plan 3, justifiés (87)

- **Fabriques évaluées à l'import (21)** : `hooks._noted` (15) et `hooks._simple` (6). Elles ne sont appelées qu'en construisant `_HANDLERS` au chargement du module, avant que mutmut n'active un mutant ; le comportement est couvert par les tests de `SessionEnd`, `Notification`, `PostToolUse` et `PreCompact`.
- **Casse des mots-clés SQL, tables et colonnes (40)** : `apply_hook` (14), `get_claude_details` (4), `session_events` (6), `purge_samples` (4), `record_metrics` (4), `record_quota` (2), `latest_metrics` (2), `_require_current_schema` et `open_existing` (`PRAGMA`, 4). SQLite ignore la casse.
- **Branches défensives inatteignables (3)** : `apply_hook` `if row or True` (`get_session` a déjà levé `NotFound` si la ligne manque) ; `_require_current_schema` `if row or True` et `else 1` (`PRAGMA user_version` renvoie toujours une ligne).
- **`uri=True` retiré ou faussé dans `open_existing` (3)** : le SQLite livré avec ce Python est compilé avec `SQLITE_USE_URI=1` et interprète les noms `file:` même sans le drapeau (vérifié : `?mode=rw` ouvre la bonne base) ; le drapeau reste pour les SQLite compilés autrement.
- **`stdin=subprocess.DEVNULL` retiré ou `None` dans `start_agents` (2)** : les processus de mutmut ont déjà `/dev/null` pour entrée standard, que le fils hérite ; le test vérifie quand même `/dev/null`, qui tuerait ces mutants hors de mutmut.
- **`decode()` sans nom d'encodage ou `"UTF-8"` (2)** dans `finish_agents` : UTF-8 est la valeur par défaut, et le nom ignore la casse.
- **`mkdir` sans `mode` ou en `0o701` (2)** dans `write_settings` : le `chmod(0o700)` qui suit fixe le mode, et `mode` ne s'applique qu'au dernier dossier.
- **`TZ` absent lu comme `"XXXX"` (1)** dans `local_zone` : la zone inconnue est ignorée comme la chaîne vide, et `/etc/localtime` est lu dans les deux cas.
- **`tool_excerpt` `get(tool_name, None)`, sans défaut ou `"XXXX"` (3)** : diffèrent seulement si `tool_input` a une clé vide `""`, ce que Claude n'envoie pas.
- **`_lines` `added or 1` et `removed or 1` (2)** : quand la valeur concernée est nulle ou absente, aucun segment n'en sort, et la somme décide comme avant pour l'autre valeur.
- **`_peak` `minute` conservée, `minute=1`, `second=1` (3)** : seule l'heure locale est lue ; une minute ou une seconde de plus ne la change pour aucun décalage horaire actuel (heures pleines, :30 ou :45). Le cas de la minute non remise à zéro est tué (`Asia/Kolkata`) ; celui des secondes ne l'est pas, car les décalages ne comptent pas de secondes.
- **`render_statusline` `seven = None` et `< width` (2)** : `_join` et `_fit` ignorent les segments vides comme `None` ; une ligne de largeur exactement `width` est reconstruite à l'identique par `_fit`.
- **`statusline_width` `"XXXX"` par défaut et `columns = 1` sur erreur (2)** : `int("XXXX")` lève la même `ValueError` que `int("")`, et 1 comme 0 n'est pas au-dessus de 80.
- **`_epoch` `<= _MAX_EPOCH` (1)** : à exactement `_MAX_EPOCH`, `datetime.fromtimestamp` lève (année 10000), exception rattrapée qui donne le même `None`.
