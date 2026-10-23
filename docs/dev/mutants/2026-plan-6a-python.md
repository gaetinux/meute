# Rapport de mutation — plan 6a Python (état Git et worktrees)

Commande : `rm -rf mutants && uv run mutmut run --max-children 4` puis `uv run mutmut results` (mutmut 3.8.0, 9134 mutants, environ 8 min). Même configuration que les plans précédents (`[tool.mutmut]` de `pyproject.toml`, `src/meute/git/` déjà dans `source_paths`). La liste blanche gagne les tests du plan qui exercent des modules mutés en processus : `test_git_state.py`, `test_worktrees.py`, `test_card_git_line.py`, `test_launch_form_worktree.py`, `test_repo_holding.py`, `test_git_run.py`, `test_git_run_pipeline.py`, `test_git_run_traps.py`, `test_git_poller.py`, `test_worktree_launch.py`, `test_worktree_removal.py`, et le nouveau `tests/test_mutants_plan6a.py`. Ils lancent le vrai git sur des dépôts jetables ou un faux `git`, mais le code muté (`meute.core`, `meute.git`) tourne dans le processus de pytest. Les tests qui passent par tmux, la CLI ou le TUI (`test_board_backend_git.py`, `test_board_backend_worktree.py`, `test_cli_worktree.py`, `test_worktree_launch_cli.py`, `test_worktree_launch_board.py`, `test_worktree_removal_board.py`, `test_tui_*`) ne voient pas les mutants et n'y sont pas.

| | mutants | tués | survivants | sans test |
|---|---|---|---|---|
| `main` (fin du plan 5), même configuration (chiffres du rapport 5) | 8109 | 7640 | 402 | 67 |
| Plan 6a, premier passage | 9134 | 8593 | 473 | 67 |
| Plan 6a, après `tests/test_mutants_plan6a.py` | 9134 | 8633 | 434 | 67 |

Le premier passage comptait aussi un mutant en délai dépassé (`_communicate`, délai remplacé), tué depuis. Les 67 mutants « sans test » sont exactement ceux de `main` (`next_live`, `create_repo_project`, `choice_project_id`, `project_refs`, `count_overdue`, voir le rapport 5) ; aucun n'est dans du code du plan 6a.

Les 434 survivants gagnent 32 sur `main` (402). Ceux du plan 6a sont 30, justifiés plus bas ; le reste de l'écart est du bruit d'autres fonctions, que le plan ne touche pas (un survivant de plus ou de moins à chaque passage, comme aux plans précédents). Les survivants de `main` sont ceux des plans 1 à 5, justifiés dans leurs rapports ; en particulier, ceux de `open_form` (3), `choose` (1) et `form_lines` (1) sont ceux du rapport 4c, et ceux de `meute.git.discover` (5) et `meute.git.kind` (4) ceux du rapport 2.

## Tests ajoutés (aucun test existant modifié)

Tous dans `tests/test_mutants_plan6a.py` (19 tests, 22 cas). Ils tuent 39 survivants du premier passage.

| Test | Mutations tuées |
|---|---|
| `test_editing_the_branch_clears_the_error` | `_edit_text` : `error=None` retiré pour le champ `Branch` |
| `test_a_card_takes_the_git_state_of_the_worktree_claude_reported` | `board_sessions` : la statusline (`worktree.path`) oubliée pour choisir le dossier de l'état Git (2) |
| `test_blank_lines_and_unknown_headers_are_not_changes` | `parse_status_v2` : `and` devenu `or`, `#` faussé (une ligne vide ou `# stash 3` marquait le dossier modifié) |
| `test_a_malformed_ahead_behind_counts_nothing` | `_ahead_behind` : conditions `or` / `and`, valeurs de repli `(1, 0)` / `(0, 1)` (4) |
| `test_eighteen_digits_still_count` | `_count` : `<=` devenu `<` |
| `test_numstat_columns_are_split_on_the_first_two_tabs_only` | `parse_numstat` : `split(None, 2)`, `split` sans borne, `rsplit`, borne 3 (4) |
| `test_a_filter_key_without_a_name_does_not_stop_the_lookup`, `test_a_filter_value_on_several_lines_keeps_its_name` | `filter_names` : `continue` devenu `break`, `or` devenu `and`, `rpartition`, séparateur faussé (4). Une clé `filter.clean` (sans nom de pilote) arrêtait la recherche, et les pilotes suivants n'étaient plus neutralisés |
| `test_a_git_that_cannot_run_names_the_reason` | `_start` : message de l'`OSError` (`git: Permission denied`) remplacé par `None` (2) |
| `test_a_git_reaped_elsewhere_has_exited`, `test_killing_a_finished_git_returns_its_status` | `has_exited` (`ChildProcessError` → `False`), `kill_read` (`suppress(None)`) |
| `test_a_message_that_is_not_utf8_is_shown` | `_failure` : `errors="replace"` retiré ou faussé (3) |
| `test_a_silent_failure_after_the_lookup_gives_the_status` | `_run` : code de sortie remplacé par `None` dans le message |
| `test_reads_and_writes_time_out_after_the_lookup`, `test_the_lookup_of_start_read_times_out` | délai remplacé par `None` dans `_run`, `read_git`, `write_git`, `start_read` (4). Les tests existants ne faisaient dépasser le délai qu'à la recherche des pilotes |
| `test_every_worktree_command_has_a_timeout` | délai remplacé par `None` dans les sept commandes de `meute.git.worktree` (7) ; les constantes de délai sont abaissées à 0,3 s par `monkeypatch` |
| `test_check_branch_refuses_an_invalid_name` | `check_branch` : l'appel à `check-ref-format` retiré |
| `test_a_detached_head_excludes_no_branch_even_one_named_none` | `worktree_only_commits` : `--exclude=None` passé pour un HEAD détaché |
| `test_git_reads_nothing_from_our_stdin` | ne tue pas `stdin=subprocess.DEVNULL` retiré (voir plus bas) : mutmut lance pytest avec `/dev/null` en entrée, le mutant y est équivalent ; le test le garde hors de mutmut |

## Survivants restants du plan 6a, justifiés (30)

- **`assert_never` remplacé ou branche `case _` retirée (7)** : `_worktree_lines` (2), `cycle_worktree` (2), `target_folder` (2), et la branche `case _:` de `_worktree_lines`. Branches inatteignables par construction : le `match` est exhaustif et pyright le vérifie.
- **Branche morte de `target_folder` (4)** : `expanded(form.folder, home)` sous `if form.repo is None` avec le choix `new` (dossier ou `home` remplacés par `None`, ou retirés). `chosen_worktree` renvoie `none` sans dépôt, la branche ne s'exécute jamais (relevé à la revue du Task 8). Elle protège l'indexation `form.repos[form.repo]` pour pyright.
- **`home` inutile (1)** : `_worktree_lines` appelle `target_folder(form, None)` au lieu de `home` dans le cas `new`, où `home` ne sert que dans la branche morte ci-dessus.
- **Valeurs initiales écrasées (4)** : `open_form` construit le formulaire avec `worktrees=()`, `worktree=NoWorktree()` et `branch_typed=False`, puis le passe à `with_worktrees`, qui remplace les deux premiers ; `None` et `False` sont tous deux faux pour `branch_typed`, qui n'est lu que comme booléen. `_choose_repo` passe `None` au lieu de `()` à `with_worktrees` quand aucun dépôt n'est choisi : sans dépôt, ni le champ `Worktree` ni `cycle_worktree` ne lisent la liste, et le choix suivant d'un dépôt la remplace.
- **Binaire de `numstat` (2)** : `_numstat_count` avec `word == "-"` neutralisé ou faussé. `_count("-")` renvoie `None`, la ligne est alors sautée au lieu de compter 0 : même total. Git écrit toujours `-` dans les deux colonnes d'un binaire.
- **Repli `HEAD` de `git_text` (2)** : `branch` et `detached` tous deux à `None` ne sortent jamais de `parse_status_v2`, qui met l'un ou l'autre. Le texte `HEAD` n'est qu'un repli pour un `GitState` construit à la main.
- **`branch_from_title` (1)** : le premier `strip(_EDGES)` devenu `strip(None)` ; la ligne suivante refait `strip(_EDGES)`, et `_UNSAFE` a déjà remplacé tous les blancs.
- **Encodage (6)** : `decode("UTF-8")` ou `decode(errors="replace")` sans nom dans `_failure`, `_run` et `lookup_filters`. Le nom d'encodage ignore la casse, et UTF-8 est la valeur par défaut.
- **`stdin` (2)** : `stdin=subprocess.DEVNULL` retiré ou `None` dans `_start`. Équivalent sous mutmut, qui donne déjà `/dev/null` à pytest ; `test_git_reads_nothing_from_our_stdin` le vérifie lancé depuis un terminal ou un tube.
- **`has_exited` (1)** : le premier `return True` (déjà récolté par `Popen`) devenu `False` ; `os.waitid` lève alors `ChildProcessError`, qui renvoie aussi `True`.
- **`filter_names` (1)** : `names[name] = ""` au lieu de `None` ; le dictionnaire ne sert que d'ensemble ordonné.

## Essai scripté

Faux `claude` (`tests/fake_claude/claude`, script `paste`, en tête du `PATH` ; jamais le vrai), serveur tmux jetable `-L meute-trial-p6a-67f82a02` (`TMUX_TMPDIR` dans un dossier court `/tmp/claude-1000/t6a.XXXX`, le dossier de travail dépassant la limite des chemins de sockets Unix), `HOME`, `XDG_*` (config, data, state, cache), `SHELL=/bin/sh`, `GIT_CONFIG_NOSYSTEM=1` et l'identité Git épinglés dans un dossier d'essai pour **toutes** les commandes, serveur tmux compris. Un dépôt `git init` neuf `~/git/fresh` (un commit), puis un dépôt nu local comme amont. Le tableau tourne dans son panneau (`meute layout sync`), sans client attaché : touches par `tmux send-keys`, écran lu par `capture-pane`. Ni le serveur `meute` ni `default` n'ont été touchés, même en lecture ; le serveur jetable est tué (`kill-server`, vérifié : « no server running ») et les dossiers d'essai supprimés par leur chemin exact.

| Cas | Action | Résultat |
|---|---|---|
| Ligne Git, dépôt neuf | `c` sur `fresh` | `└ main (not pushed)` |
| Ligne Git qui suit une modification | trois lignes ajoutées à `README.md` | `└ main* +3 −0 (not pushed)` 4 s plus tard (un tour de 10 s au plus) |
| Amont et avance | `push -u` vers le dépôt nu, un commit, une modification | `└ main* +1 −0 ↑1` |
| HEAD détaché | `git checkout --detach` | `└ (detached 2cd962f)* +1 −0` |
| `N` sur un dossier occupé | `N` sur la session vivante de `fresh` | `Worktree ◂ new ▸`, `Branch` vide, `Claude will ask whether to trust the new folder`, `⚠ another live session works in this folder: a new worktree is recommen…` (coupé à 72 colonnes, R10) |
| `Branch` prérempli | `Tab` jusqu'à `Title`, « Fix login bug » | `Branch fix-login-bug`, `→ ~/git/fresh.worktrees/fix-login-bug` |
| Lancement dans un nouveau worktree | `Entrée` | session `Fix login bug` dans `~/git/fresh.worktrees/fix-login-bug`, rangée sous `fresh` ; `git worktree list` montre le worktree, branche `fix-login-bug` créée ; sa carte : `└ fix-login-bug (not pushed)` |
| `W` sur une session vivante | `W` | `stop the session first` |
| `W`, une autre session vit dans le worktree | `W` sur la session terminée | `a live session works in this worktree` |
| `W` sur le dossier principal | `W` sur la session terminée de `fresh` | `not a linked worktree: ~/git/fresh` |
| `W` propre | `W`, `n`, puis `W`, `y` | `remove worktree ~/git/fresh.worktrees/fix-login-bug? (branch fix-login-bug is kept) y/n` ; `n` ne change rien ; `y` : `worktree removed: ~/git/fresh.worktrees/fix-login-bug`, la branche reste, la carte perd sa ligne Git |
| `W` puis `r` sur un worktree enlevé | `W`, `r` | `folder not found: ~/git/fresh.worktrees/fix-login-bug` ; `r` : `Error: folder not found: <chemin absolu>` |
| `meute session new --worktree` | `--cwd ~/git/fresh --worktree feat/listed` ; la même deuxième fois ; `--cwd ~` | `Launched: … (~/git/fresh.worktrees/feat/listed)` ; `meute: folder already exists: ~/git/fresh.worktrees/feat/listed` (code 1) ; `meute: not in a git repository: ~` (code 1) |
| `W` avec une liste | 12 commits, une modification, un fichier non suivi dans `feat/listed`, session arrêtée ; `W`, `y`, `n` | `~/git/fresh.worktrees/feat/listed has uncommitted changes or unpushed commits: y shows them, n cancels` ; `y` : ` M README.md`, `?? untracked.txt`, 10 lignes `git log --oneline`, `… and 2 more`, `remove anyway? y/n` ; `n` : le worktree reste |
| `meute worktree list` | sans argument, `--json`, puis avec un chemin de worktree | `~/git/fresh.worktrees/dirty  dirty`, `~/git/fresh.worktrees/feat/listed  feat/listed *`, `~/git/fresh.worktrees/locked  locked  locked` ; JSON avec `repo`, `path`, `branch`, `dirty`, `locked`, `missing` ; un chemin de worktree liste les worktrees de son dépôt principal |
| Worktree verrouillé absent | dossier `locked` déplacé | `~/git/fresh.worktrees/locked  locked  locked  missing`, code 0 |
| `meute worktree remove`, refus | dossier principal, verrouillé, modifié sans `--force`, absent, session vivante | `not a linked worktree: ~/git/fresh`, `the worktree is locked`, la liste puis `… has uncommitted changes or unpushed commits`, `folder not found: ~/git/nowhere`, `a live session works in this worktree` ; code 1 à chaque fois |
| `meute worktree remove`, enlèvement | propre : `n`, puis `--yes` ; modifié `--force` : `n`, puis `y` | `remove worktree …? (branch dirty is kept) y/n Cancelled.` ; `worktree removed: …` ; la liste puis `remove anyway? y/n` ; `worktree removed: ~/git/fresh.worktrees/feat/listed` ; toutes les branches restent |
| Configuration piégée | `core.fsmonitor`, pilote de diff et pilote de filtre `clean` qui créent un témoin, `.gitattributes` `* diff=trap filter=trap` | ni `fsmonitor` ni le pilote de diff n'ont tourné ; **le `clean` du filtre a tourné une fois**, puis plus du tout pendant trois tours avec fichiers modifiés (voir plus bas) |

Constat de l'essai, à trancher par le contrôleur : le pilote de filtre a été ajouté à `.git/config` pendant un tour. Dans `GitPoller`, la recherche des pilotes et `git status` sont deux étapes séparées par une relecture (R7, 2 s au plus) : la recherche n'a rien trouvé, puis `status` a tourné avec le filtre, sans le neutraliser. Les six essais suivants, faits exprès (filtre ajouté et retiré à divers moments), n'ont rien déclenché, mais la fenêtre est réelle. Il faut pouvoir écrire dans `.git/config`, ce que Claude peut faire. La limite est consignée dans la feuille de route (« Reports issus du plan 6a »).

Autres remarques, sans correctif : le message de `r` sur un dossier disparu donne le chemin absolu (hérité du plan 4c), là où `W` l'abrège en `~` ; `+3 −0` montre les deux nombres dès que l'un est non nul, comme le veut la conception.

## À essayer à la main (vrai terminal, vrai Claude)

À copier dans la PR. Dans un vrai terminal, avec le vrai `claude`, sur un dépôt sans importance qui a un amont :

1. **Ligne Git** : `c` sur le dépôt ; demander à Claude de modifier un fichier : la carte passe à `└ main* +N −M` en 10 s au plus ; un commit fait par Claude la fait passer à `↑1` ; `git push` à la main la ramène à `└ main`.
2. **Recommandation** : une session vivante sur le dépôt, puis `N` : le formulaire s'ouvre sur `Worktree ◂ new ▸` avec la recommandation ; `←` revient à `none` et le message reste ; en largeur étroite (moins de 74 colonnes), le message est coupé (R10) : dire s'il faut le replier.
3. **Lancement dans un nouveau worktree** : titre, `Entrée` : Claude demande s'il faut faire confiance au nouveau dossier (`Claude will ask whether to trust the new folder`) ; la session est rangée sous le dépôt, et sa carte montre la nouvelle branche `(not pushed)`.
4. **Worktree existant** : `N`, `→` jusqu'à un worktree existant (`<branche>  <chemin>`) : `Folder` prend son chemin, en lecture seule, et la session s'y lance.
5. **Hooks Git** : un hook `post-checkout` du dépôt tourne bien à la création du worktree (`N` avec `new`, ou `meute session new --worktree`).
6. **Worktree créé par Claude** : demander à Claude d'entrer dans un worktree (`EnterWorktree`) : la carte montre l'état Git de ce worktree, suivi de son nom.
7. **`W`** : arrêter la session du worktree (`x`), `e`, `W` : confirmation simple sur un worktree propre ; avec des modifications ou des commits non poussés, les deux confirmations et la liste ; vérifier que la branche reste (`git branch`) et que `r` sur la session répond `folder not found`.
8. **Pas de texte pendant l'enlèvement** : sur un gros worktree, `W` puis `y` : le pied ne dit rien pendant `git worktree remove` (jusqu'à 30 s) ; dire si un texte « removing… » manque.
9. **CLI** : `meute worktree list`, `meute worktree list --json`, `meute worktree remove <chemin>` sans puis avec `--force`.
10. **Aide** : `?` liste `W remove the worktree of an ended session`.
