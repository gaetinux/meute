# Rapport de mutation — plan 4 Python (vue Sessions)

Commande : `rm -rf mutants && uv run mutmut run --max-children 4` puis `uv run mutmut results` (mutmut 3.8.0, 5011 mutants, environ 3 min). Même configuration que le plan 3 (`[tool.mutmut]` de `pyproject.toml`) ; `tests/test_mutants_plan4.py` est ajouté à la liste blanche. Les autres fichiers en processus du plan (`test_attention.py`, `test_quota_view.py`, `test_sessions_view.py`, `test_board_sessions.py`, `test_config_show_details.py`, `test_status_line.py`…) y figuraient déjà ; les tests de `meute.cli`, du TUI et des sessions tmux ne voient pas les mutants et n'y sont pas.

| | mutants | tués | survivants | sans test |
|---|---|---|---|---|
| `main` (plan 3 mergé, copie de travail jetable) | 4291 | 4036 | 255 | 0 |
| Plan 4, premier passage | 5011 | 4709 | 301 | 1 |
| Plan 4, après `tests/test_mutants_plan4.py` | 5011 | 4733 | 278 | 0 |

Les survivants de `main` (255) sont ceux des plans 1 à 3, déjà justifiés dans les rapports précédents. En comparant les survivants par fonction, le plan 4 en ajoute 25 (tous justifiés ci-dessous) et en retire 2 (`_make_private_file`, réécrit par le correctif ci-dessous).

## Essai scripté

Faux `claude` (`tests/fake_claude/claude`), serveur tmux jetable `meute-test-trial-<horodatage>` (`-L`, dossier `TMUX_TMPDIR`, `HOME` et `XDG_*` sous `/tmp/meute-trial-10`, supprimé ensuite), `MEUTE_FAKE_CLAUDE_SCRIPT=permission` pour la première session et `done` pour la seconde (`tmux set-environment -g`, car l'environnement du serveur est hérité). Ni le serveur `meute` ni le vrai `claude` n'ont été touchés.

| Étape | Résultat |
|---|---|
| `meute layout sync` | code 0 ; session `meute` avec le tableau (rôle `board`) |
| deux sessions Claude (`perm`, `calm`) | `session list` : `perm  permission  [manual]` et `calm  waiting for your reply  [manual]` |
| `tmux show-options -gv @meute_status` | `2 need attention · 5h 27%` (`perm` en permission, `calm` attend la réponse : les deux comptent). Après l'arrêt de `calm` : `▶ perm · 1 need attention · 5h 27%` |
| `meute session next` | code 0 ; le panneau principal affiche `perm` (`%2  28c3ac62-…`) |
| `capture-pane` du tableau | `Other  2 live · 0m · $0.11` (en-tête de groupe), `!perm  permission  now  [manual]`, `!calm  waiting for your reply  now  4%  $0.11  [manual]`, et le détail (`Folder:`, `Model: claude-opus-5-5`, `Mode: manual`, `Waiting for: Bash mkdir /tmp/capture/denied`, `Last tool:`, `Cost:`, `Duration:`) |
| `down`, `x`, `y` par `send-keys` | après `x` : `Stop "calm"? y: yes · any other key: no` ; après `y`, `session list` ne montre plus `calm` en **0,42 s** ; le tableau reste vivant : `Other  1 live`, `1 ended (e to show)` |

**Premier passage : échec, bug trouvé.** Avant le correctif, après `y` le tableau affichait en permanence `Error: database disk image is malformed` et la ligne `calm` restait. La trace (journalisation temporaire, retirée) montrait `sqlite3.DatabaseError` dans `set_session_state`, appelé par `CliBoardBackend._stop` dans le fil de travail. Cause : `Database.open` appelait `_make_private_file`, qui ouvrait puis fermait un descripteur sur le fichier de la base ; or POSIX libère tous les verrous que le processus détient sur un fichier à la fermeture de n'importe lequel de ses descripteurs. Le tableau (connexion du fil principal) et le fil d'arrêt (seconde connexion, ouverte pour ne pas partager celle du premier) étaient dans le même processus, avec en plus les hooks du faux `claude` qui écrivaient : le fichier WAL se corrompait. La commande CLI `meute session stop` n'était pas touchée (un processus par connexion).

Correctif en TDD : `_make_private_file` ne fait plus que `Path.chmod(0o600)` sur un fichier existant (il le crée seulement s'il manque, quand personne ne le tient ouvert). Tests : `tests/test_db_open_beside_connection.py` (une connexion ouverte, un fil qui rouvre la base en boucle et un sous-processus qui écrit : échoue au rouge avec `database disk image is malformed` dans trois exécutions sur cinq, passe au vert à chaque fois ; le test est probabiliste et dure environ 10 s) et `test_an_existing_database_file_is_not_opened_by_descriptor` dans `tests/test_mutants_plan4.py` (déterministe : `os.open` n'est pas appelé sur un fichier existant, dont le mode est tout de même ramené à `0600`).

Second passage après correctif : toutes les lignes du tableau ci-dessus, aucune erreur dans les cinq secondes qui suivent. Nettoyage : serveur tué (`kill-server`), dossier de l'essai supprimé par son chemin exact ; `/tmp/tmux-1000` ne contient que `default`, `meute` et `revchk`, présents avant l'essai.

## Tests ajoutés (aucun test existant modifié)

Tous dans `tests/test_mutants_plan4.py`, sauf indication.

| Test | Mutations tuées |
|---|---|
| `test_unknown_current_starts_at_the_first_going_forwards`, `…_last_going_backwards` | point de départ de `next_attention` sans session courante (condition `backwards`, départ à 1) |
| `test_no_sessions_are_dated_at_the_epoch`, `test_board_sessions_keeps_the_given_clock` | défaut du `max` et champ `now` de `board_sessions` |
| `test_outside_agents_and_orphans_are_in_the_view_with_a_short_home` | `outside`, `orphans` et `home` perdus dans l'appel de `build_view` |
| `test_a_session_line_without_its_session_has_no_entry`, `test_a_repo_line_without_its_repository_has_no_entry` | branches `None` de `line_entry` |
| `test_new_action_on_a_session_keeps_its_repository` | `repo_id` perdu dans `new_action` |
| `test_stopping_text_neutralises_control_characters` | `printable(None)` dans `stopping_text` (le seul mutant sans test) |
| `test_a_drop_between_the_first_two_samples_starts_a_new_cycle`, `test_equal_samples_are_not_a_drop` | bornes de `_current_cycle` (départ de la boucle, `<`, `index - 1`) |
| `test_a_sample_exactly_thirty_minutes_old_counts`, `test_a_limit_exactly_at_the_reset_is_none` | bornes de `projected_limit` |
| `test_quota_lines_show_every_time_in_the_given_zone`, `test_peak_text_converts_the_start_to_the_given_zone` | `astimezone(None)` (fuseau du système au lieu de celui demandé), vérifiés avec Asia/Kathmandu (+05:45) |
| `test_attention_filter_skips_one_session_and_keeps_the_next`, `test_ended_sessions_do_not_hide_the_live_ones_after_them`, `test_every_ended_session_is_counted` | `continue` devenu `break` et `ended += 1` devenu `= 1` dans `_group_lines` |
| `tests/test_db_open_beside_connection.py` | voir l'essai : `_make_private_file` |

## Survivants restants du plan 4, justifiés (25)

- **`assert_never` retiré ou remplacé par `assert_never(None)` (6)** : `needs_attention` (2), `line_entry` (2), `line_key` (2). Branche inatteignable par construction : le `match` est exhaustif.
- **Casse du SQL de `quota_history` (4)** : SQLite ignore la casse des mots-clés, tables et colonnes.
- **`_crossing_seconds` (6)** : `x + mean_x` et `y + mean_y` donnent la même pente, car `sum(y - mean_y)` et `sum(x - mean_x)` valent zéro (3 mutants avec les deux `zip(strict=…)` retirés ou faussés, car les deux listes ont toujours la même longueur : 3 de plus) ; `or True` sur `isfinite` : un temps infini passe alors à `projected_limit`, qui le refuse de la même façon (comparaison avec `resets_at`, ou `OverflowError` de `timedelta`), donc le résultat public est identique.
- **`_current_cycle` `start = None` et `range(len(samples))` (2)** : `samples[None:]` rend tout comme `samples[0:]` ; partir de l'indice 0 compare `samples[0]` à `samples[-1]` et ne peut que reposer `start = 0`, que la suite d'une vraie chute écrase.
- **`age_text` `/` au lieu de `//` (3) et `duration_text` `max(ms, 1)` (1)** : `int()` tronque pareil pour une valeur positive ; sous 1000 ms, `1 // 1000` vaut 0 comme `0 // 1000`.
- **`_bottom_lines` `lines = [...]` au lieu de `+=` (1)** : la liste est vide à ce point.
- **`risky_mode_span` `line is None and mode is None or …` (1)** : une ligne absente n'a pas d'information, donc pas de mode, et `None not in RISKY_MODES` suffit déjà à rendre `None`.
- **`_bool` `rpartition` au lieu de `partition` (1)** : les clés ont un seul point (`ui.show_details`), comme pour `_int` (déjà justifié).
