# Rapport de mutation — plan 6b Python (reprise et états sauvegardés)

Commande : `rm -rf mutants && uv run mutmut run --max-children 4` puis `uv run mutmut results` (mutmut 3.8.0, 9447 mutants, environ 9 min). Même configuration que les plans précédents (`[tool.mutmut]` de `pyproject.toml`) : `src/meute/core/` est déjà dans `source_paths`, donc `saved_state.py`, `state_capture.py` et `db/saved_states.py` sont mutés sans changement. La liste blanche gagne les tests du plan qui exercent le cœur en processus : `test_saved_state.py`, `test_db_saved_states.py`, `test_state_capture.py`, `test_recent_days.py` (configuration et `board_data` sur une base en mémoire), et le nouveau `tests/test_mutants_plan6b.py`. Les tests qui passent par tmux, la CLI ou le TUI (`test_last_state.py` et `test_board_backend_states.py`, qui reprennent les fixtures tmux de `test_board_backend.py`, `test_state_reopen.py`, `test_cli_state.py`, `test_cli_session_recent.py`, `test_tui_saved_states.py`) ne voient pas les mutants et n'y sont pas ; `meute.cli` et `meute.tui` ne sont d'ailleurs pas mutés.

| | mutants | tués | survivants | sans test |
|---|---|---|---|---|
| Fin du plan 6a (chiffres du rapport 6a) | 9134 | 8633 | 434 | 67 |
| Plan 6b, premier passage | 9447 | 8924 | 454 | 69 |
| Plan 6b, après `tests/test_mutants_plan6b.py` | 9447 | 8930 | 450 | 67 |

Le plan ajoute 313 mutants. Au premier passage, 23 survivants et 2 mutants « sans test » étaient dans son code ; les 2 « sans test » (`saved_text`, `reopening_text`, appelés seulement par la CLI et le TUI) sont désormais tués, et les 67 restants sont exactement ceux de `main` (voir le rapport 5). Les autres survivants (431 aux deux passages, contre 434 au rapport 6a) sont ceux des plans 1 à 6a, justifiés dans leurs rapports ; l'écart est du bruit de fonctions que le plan ne touche pas (un survivant de plus ou de moins à chaque passage, comme aux plans précédents). Les ajouts du plan aux modules existants (`board_session_order`, `UiConfig.recent_days` et sa validation, `NotFound(message=…)`, `SaveState`, `ReopenState`, `KEYS_HELP`) ne laissent aucun survivant.

## Tests ajoutés (aucun test existant modifié)

Tous dans `tests/test_mutants_plan6b.py` (6 tests). Ils tuent 7 mutants du premier passage, plus un mutant tué par hasard au premier passage et resté vivant au deuxième.

| Test | Mutations tuées |
|---|---|
| `test_saved_and_reopening_texts_name_the_state`, `test_saved_and_reopening_texts_neutralise_control_characters` | `saved_text`, `reopening_text` : le nom remplacé par `None` (2, « sans test » : seuls la CLI et le TUI les appelaient) |
| `test_getting_an_unknown_state_names_its_entity_and_ident`, `test_deleting_an_unknown_state_names_its_entity_and_ident` | `_not_found` : l'entité (`None`, `XXsaved stateXX`, `SAVED STATE`) ou l'identifiant (`None`) du `NotFound` faussés (4) ; le texte, remplacé par `message`, ne les montrait pas |
| `test_the_largest_database_id_is_read`, `test_ids_of_one_are_read` | `_db_id` : `<=` devenu `<` sur la borne `2**63 - 1`. Les propriétés `hypothesis` de `test_saved_state.py` ne l'atteignent que par hasard (tué au premier passage, vivant au deuxième) ; les deux bornes sont désormais fixées |

## Survivants restants du plan 6b, justifiés (19)

- **Casse du SQL (12)** : `save_state` (10) et `delete_state` (2), requêtes passées en minuscules ou en majuscules (`delete from saved_states`, `SAVED_STATES`, `NAME`, `CREATED_AT`…). SQLite ne distingue pas la casse des mots-clés ni des identifiants ; mutants équivalents, comme aux plans précédents.
- **Ligne inatteignable de `save_state` (5)** : le message (`None`, `XX…XX`, minuscules, majuscules) ou l'argument de `RuntimeError("INSERT returned no row")`. `INSERT … RETURNING` rend toujours une ligne ; la branche ne sert qu'à pyright, `fetch_one` renvoyant un `tuple | None`.
- **`NewType` des ids (2)** : dans `_session`, `None if task_id is None else TaskId(task_id)` devenu `TaskId(task_id)` toujours (de même pour `RepoId`). `TaskId` et `RepoId` sont des `NewType` : `TaskId(None)` vaut `None` à l'exécution. Mutants équivalents.

## Essai scripté

Faux `claude` (`tests/fake_claude/claude`, script `done`, en tête du `PATH`, devant `.venv/bin` ; jamais le vrai), serveur tmux jetable `-L meute-trial-p6b-422402f8` (`TMUX_TMPDIR` dans un dossier court `/tmp/claude-1000/t6b.uNbW`, le dossier de travail dépassant la limite des chemins de sockets Unix), `HOME`, `XDG_*` (config, data, state, cache), `SHELL=/bin/sh`, `GIT_CONFIG_NOSYSTEM=1` et l'identité Git épinglés dans un dossier d'essai pour **toutes** les commandes, serveur tmux compris. Un dépôt `git init` neuf `~/git/fresh` (un commit) et un dossier `~/notes`. Le tableau tourne dans son panneau (`meute layout sync`), sans client attaché : touches par `tmux send-keys`, écran lu par `capture-pane`, états lus par `meute state list` et dans la base. Ni le serveur `meute` ni `default` n'ont été touchés, même en lecture ; le serveur jetable est tué (`kill-server`, vérifié : « no server running ») et les dossiers d'essai supprimés par leur chemin exact.

| Cas | Action | Résultat |
|---|---|---|
| Trois sessions | `meute session new` : `Claude one` (`~/git/fresh`), `Claude two` (`~/notes`), `--kind bash` `Shell fresh` (`~/git/fresh`) ; `meute session show` sur `Claude two` | trois cartes ; `last  3 sessions  now` écrit par le tableau dès sa relecture, sans `S` |
| `S` | `S` dans le tableau | pied `state saved: 2026-10-24 10:30` ; `meute state list` : `last  3 sessions  now`, puis `2026-10-24 10:30  3 sessions  now` ; `--json` : `{"states":[{"name":"last","created_at":"…Z","sessions":3},{"name":"2026-10-24 10:30",…,"sessions":3}]}` |
| `S` juste après `show` | `S` 1 s après `meute session show` | l'état est écrit avec `displayed` faux partout (voir plus bas) ; un second `S` 2 s plus tard, dans la même minute, remplace l'état, cette fois avec `Claude two` affichée |
| `x` sur tout | `x`, `y` trois fois (`Stop "Claude one"? y: yes · any other key: no`, …) | les trois sessions s'arrêtent ; `last` est gardé (jamais vide), mais il ne contient plus que `Shell fresh` (`last  1 session`), la dernière liste non vide vue par le tableau (voir plus bas) ; l'état nommé garde ses 3 sessions |
| Redémarrage | `kill-server` du serveur jetable, puis `meute layout sync` | nouveau tableau, aucune session vivante ; `last` n'est pas écrasé (`last  1 session`) |
| `O` | `O` | la liste au-dessus du pied : `last  1 session  now`, `2026-10-24 10:30  3 sessions  1m` ; le pied montre encore `↑↓ select · Enter show · c/n new · x stop · ? keys` |
| `O`, `last`, `Entrée` | `Entrée` sur `last` | `reopened 1 · skipped 0` ; `Shell fresh` revient (nouvel id, même dossier) et est affichée dans la zone principale ; la liste reste ouverte |
| `O`, état nommé, `Entrée` | `↓`, `Entrée` | `reopened 2 · skipped 1` : `Claude one` et `Claude two` reprises avec leurs ids (`claude --resume`), `Shell fresh` ignorée (Bash vivante dans le même dossier) ; `Claude two` revient dans la zone principale (`▶`) ; `Échap` ferme la liste |
| Seconde réouverture | `meute state open "2026-10-24 10:30"`, puis `meute state open last` | `reopened 0 · skipped 3`, puis `  Claude one: already running`, `  Claude two: already running`, `  Shell fresh: already running`, code 0, les deux fois ; aucune session doublée (`meute session list` : 3 lignes) |
| État inconnu | `meute state open nope` | `meute: no saved state named nope`, code 1 |
| `meute session recent` | `meute session stop eb0237fa --yes`, puis `recent` et `recent --json` | `eb0237fa  Claude one  ~/git/fresh  now  resumable` ; `{"sessions":[{"id":"eb0237fa-…","title":"Claude one","cwd":"…/home/git/fresh","ended_at":"…Z","resumable":true}]}` |
| `meute session resume` | `resume eb02` (préfixe), puis `recent` ; `resume` d'une session vivante ; `resume` d'une Bash | `Resumed: eb0237fa Claude one`, la session revit, `recent` ne montre plus rien (code 0) ; `meute: "Claude one" is still running` (code 1) ; `meute: only Claude sessions resume` (code 1) |
| `meute state save` et `rm` | `save review`, `save last`, `save "  "` ; `rm review` avec `n`, puis `y`, puis encore | `Saved: review (3 sessions)` ; `meute: last is kept by the board` (1) ; `meute: state name is empty` (1) ; `Remove saved state "review"? [y/N]Cancelled.` (0) ; `Removed: review` (0) ; `meute: no saved state named review` (1) |

Constats de l'essai, à trancher par le contrôleur :

1. **`last` après des `x` successifs** : le tableau réécrit `last` à chaque changement de la liste des sessions vivantes. Arrêter les sessions une à une donne les listes 3, 2, 1, puis 0 (non écrite) : `last` garde la liste à **une** session, pas celle de la journée. Après un redémarrage de la machine (toutes les sessions deviennent `Unreachable` d'un coup), `last` garde bien toute la liste. Le comportement est celui de la conception (« `last` garde la dernière liste non vide »), mais pas son intention (« `O` rouvre l'ensemble des sessions qui tournaient ») quand on arrête tout par `x`. Piste : n'écrire `last` que quand la liste grandit ou change de membres sans rétrécir, ou garder la plus grande liste depuis la dernière ouverture ; à décider avec l'auteur.
2. **`displayed` de `last` figé** : `last` n'est réécrit que si les **ids** changent ; changer la session affichée ne le réécrit pas. Ici, la première écriture de `last` (3 sessions) avait `displayed` faux partout, bien que `Claude two` ait été affichée ensuite ; seule la liste à une session, écrite après les `x`, marquait `Shell fresh` affichée. Rouvrir `last` remet alors en avant la session affichée au dernier changement de la liste, ou aucune.
3. **`S` sur une lecture de 2 s au plus** : `S` sauve la dernière lecture du tableau ; une session amenée par `meute session show` moins de 2 s avant n'y est pas encore marquée affichée. Limite du même ordre que celle de `last` dans la conception.
4. **Invite de `rm` sans espace** : `[y/N]` est suivi directement de la réponse (`[y/N]Cancelled.` quand l'entrée est un tube) ; texte de la conception gardé (mineur déjà relevé au Task 6).

## À essayer à la main (vrai terminal, vrai Claude)

À copier dans la PR. Dans un vrai terminal, avec le vrai `claude` :

1. **`S` et `O`** : deux sessions Claude qui ont déjà échangé un message, une session Bash ; `S` : le pied dit `state saved: <heure>` ; `O` : la liste montre `last` puis l'état, `↑` `↓` choisissent, `Échap` ferme.
2. **Reprise après un redémarrage** : quitter meute (`M-q`), redémarrer la machine (ou `tmux -L meute kill-server`), relancer `meute`, puis `O`, `last`, `Entrée` : chaque conversation Claude reprend où elle était (`claude --resume`, même tâche, même titre), le shell se rouvre dans son dossier, et la session affichée revient dans la zone principale.
3. **Deux fois** : `Entrée` de nouveau, ou `meute state open last` : `reopened 0 · skipped N`, rien n'est doublé.
4. **`last` et `x`** : arrêter toutes les sessions une à une par `x`, puis `O` : dire si `last` (qui ne garde que la dernière session arrêtée, constat 1) convient.
5. **Session sans conversation** : une session Claude arrêtée avant que Claude n'ait envoyé `SessionStart` : `O` la saute avec `no conversation id`.
6. **Worktree enlevé** : un état qui contient une session d'un worktree enlevé depuis par `W` : la réouverture la saute avec `folder not found: <chemin>`.
7. **CLI** : `meute state save revue`, `meute state list`, `meute state list --json`, `meute state open revue`, `meute state rm revue` (puis `n`, puis `y`) ; `meute state rm last`, puis vérifier que le tableau le recrée.
8. **Sessions récentes** : `meute config set ui.recent_days 1`, `e` dans le tableau, `meute session recent`, puis `meute session resume <préfixe>` : la conversation reprend.
9. **Largeur étroite** : `O` sous 60 colonnes : les lignes de la liste sont coupées proprement.
10. **Aide** : `?` liste `S save the open sessions · O reopen a saved state`.
