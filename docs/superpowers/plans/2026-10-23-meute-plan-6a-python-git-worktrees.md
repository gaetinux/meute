# meute — Plan 6a Python : état Git et worktrees — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Objectif :** chaque carte du tableau montre l'état Git de sa session. Le formulaire `N` crée ou choisit un worktree, et le recommande quand le dossier est déjà occupé. `W` et `meute worktree remove` nettoient un worktree sans jamais perdre de travail en silence.

**Architecture :** comme aux plans précédents, ce qui se décide se calcule dans `meute.core`, de façon pure et avec la stdlib seule :
- l'analyse des sorties de git ;
- les textes affichés ;
- l'état du formulaire.

Le reste se répartit ainsi :
- `meute.git` lance git, toujours par une seule fonction protégée, et renvoie du texte brut ;
- `meute.cli` assemble : `GitPoller`, le backend du tableau, les commandes `meute worktree` et `session new --worktree` ;
- `meute.tui` ajoute le champ `Worktree` et la touche `W`.

**Stack technique :** l'existant (Python 3.13, uv, Typer, Textual 8.2, `syrupy`, `hypothesis`, `mutmut`) et git 2.47 sur la machine. Aucune nouvelle dépendance.

**Spécification :**
- conception de ce plan : `docs/superpowers/specs/2026-10-23-meute-git-worktrees-design.md` ;
- spécification générale : `docs/superpowers/specs/2026-10-15-meute-design.md`, § 6.4, § 10 et § 11 ;
- guide : `docs/dev/developpement-assiste-par-ia.md`.

**Prérequis :** le plan 5 est mergé (PR #13). La branche `feat/plan-6a-python` existe ; elle a été créée sur `main` à jour (f4d5a2a) et porte la conception (85724f3).

## Décisions de conception (à relire)

1. **Les capacités Git du TUI passent par un paramètre facultatif.** `BoardApp` gagne `git: BoardGit | None = None`, un protocole à deux méthodes : `worktrees(repo: Path) -> tuple[Worktree, ...] | str` et `inspect(folder: Path) -> WorktreeCheck | str`. `BoardBackend` ne change pas. Les faux backends des tests existants restent donc valides. Sans `git`, le formulaire ne propose que `none` et `new`, et `W` répond `git not available`.
2. **L'état Git arrive par `BoardData.git: Mapping[Path, GitState]`**, avec un dictionnaire vide par défaut. `SessionInfo` gagne `git: GitState | None = None`. Sans état, la carte garde exactement sa ligne d'aujourd'hui : aucun instantané existant ne bouge.
3. **Le backend ne connaît pas `e`.** `GitPoller` relève les dossiers de `data.sessions`, puis ceux de `data.ended` (7 jours), sans doublon, et **40 dossiers au plus par tour**, les vivants d'abord. C'est un écart à la conception (« les terminées quand `e` les montre ») : les sessions terminées sont peu nombreuses, et le tour a lieu toutes les 10 s.
4. **Pas de git dans un environnement nu.** Comme pour `claude`, git n'est cherché que si `PATH` figure dans l'environnement du backend. Les tests du tableau qui passent un environnement nu ne lancent donc jamais git.
5. **`meute session show` n'affiche rien** : il amène le panneau. La conception a été corrigée dans ce sens, et l'état Git reste propre au tableau.
6. **`r` sur un dossier disparu est déjà refusé** par `resolve_folder` (`folder not found: …`, `tests/test_session_resume.py:217`). Le Task 10 ajoute seulement un test avec un worktree enlevé.
7. **`launch_form.py` (267 lignes) et `sessions_tab.py` (275 lignes) sont découpés** pour rester sous 300 lignes :
   - la logique du worktree va dans `core/launch_form_worktree.py` ;
   - les confirmations de `W` vont dans `tui/worktree_removal.py`.

## Contraintes globales

**Hérité des plans 1 à 5 (inchangé)**
- **Frontières d'imports** (import-linter) : `meute.core`, `meute.tmux` et `meute.git` n'utilisent que la stdlib et ne s'importent pas entre eux. `meute.tui` n'importe ni `meute.tmux` ni `meute.git`. Seul `meute.cli` assemble.
- **Code :**
  - dataclasses gelées, `match` exhaustif terminé par `assert_never` ;
  - pas d'`Any`, de `cast` ni d'`assert` hors des tests ;
  - docstrings sur tout le public de `meute.core` ;
  - fichiers de moins de 300 lignes ;
  - exceptions de lint précises, suivies de ` — raison`.
- **Textes :**
  - interface en anglais, textes de la conception copiés mot pour mot ;
  - toute donnée affichée passe par `printable` ;
  - tout argument passé à tmux passe par `Tmux.run`.
- **Tests :**
  - tmux uniquement sur des serveurs jetables (`tmux_server`, `sandbox`) ;
  - aucun test n'appelle le vrai `claude` ;
  - ni le serveur `meute`, ni le serveur tmux `default`, **même en lecture seule** ;
  - jamais de modification de `~/.claude/settings.json` ni de `~/.claude.json`.

**Propre au plan 6a**
- **Git en lecture :** toujours par `meute.git.run.read_git`, qui ajoute :
  - `-c core.fsmonitor=false` et `--no-optional-locks` avant la sous-commande ;
  - `--no-ext-diff` et `--no-textconv` pour `diff` ;
  - `GIT_TERMINAL_PROMPT=0` et `GIT_OPTIONAL_LOCKS=0` dans l'environnement ;
  - `-C <dossier absolu>` ;
  - un délai maximal.
- **Git en écriture :** `worktree add` et `worktree remove` passent par `write_git`, qui garde les hooks de l'utilisateur mais ajoute `-c core.fsmonitor=false`. **Jamais** de `commit`, `merge`, `push`, `fetch` ni `branch -d`/`-D`.
- **Délais maximaux :** 5 s pour le relevé de fond et la vérification de `W`, 2 s pour la liste des worktrees du formulaire, 30 s pour `worktree add` et `remove`.
- **Dépôts de test :** de vrais dépôts jetables dans `tmp_path`. L'environnement de git est épinglé : `HOME`, `XDG_CONFIG_HOME`, `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_NOSYSTEM=1`, et `GIT_AUTHOR_*` / `GIT_COMMITTER_*` fixés. Jamais les dépôts de l'auteur.
- **Textes exacts** (conception) :
  - `(not pushed)`, `(detached <commit>)`, `→ <chemin>` ;
  - `branch is empty`, `folder already exists: <chemin>`, `git: <message>`, `git not found`, `git timed out after <n> s` ;
  - `worktree created at <chemin> but the launch failed: <erreur>` ;
  - `Claude will ask whether to trust the new folder` ;
  - `⚠ another live session works in this folder: a new worktree is recommended` ;
  - `not a linked worktree: <chemin>`, `a live session works in this worktree`, `the worktree is locked`, `folder not found: <chemin>`, `stop the session first`, `not in a git repository: <chemin>` ;
  - `remove worktree <chemin>? (branch <b> is kept) y/n` ;
  - `<chemin> has uncommitted changes or unpushed commits: y shows them, n cancels` ;
  - `remove anyway? y/n`, `… and N more`, `worktree removed: <chemin>`.

**Qualité et workflow**
- **TDD strict.** Ne jamais modifier, supprimer ni désactiver un test existant. Les seules exceptions demandées par ce plan prolongent la numérotation du plan 5. **Elles sont à autoriser par l'auteur à la relecture du plan.** Chacune est signalée dans le commit et dans la PR :
  - **n° 27** (Task 8 et Task 9) : les tests du formulaire `N`, c'est-à-dire `tests/test_launch_form.py`, `tests/test_launch_form_busy.py`, `tests/test_launch_form_view.py`, `tests/test_tui_launch_form.py`, `tests/test_tui_launch_form_task.py`, `tests/test_mutants_plan4c.py` et leurs instantanés (`test_launch_form_view.ambr`, `__snapshots__/test_tui_launch_form/`). On n'y change que les attentes que le champ `Worktree`, le champ `Branch` ou la recommandation déplacent :
    - l'ordre de `Tab` ;
    - les lignes affichées ;
    - le texte de l'avertissement ;
    - le choix `new` à l'ouverture sur un dossier occupé.

    Chaque test touché est listé dans le commit, avec l'intention gardée.
  - **n° 28** (Task 11) : les tests et instantanés qui montrent l'aide `?` des sessions (`KEYS_HELP`, par exemple `tests/test_tui_keys_help.py`). L'aide gagne la ligne `W remove the worktree of an ended session`, et rien d'autre ne change.
- **Instantanés :** relus ligne par ligne, jamais de `--snapshot-update` à l'aveugle.
- **Fin de tâche :** chaque tâche se termine par `bash scripts/verify.sh` et un commit. Les tâches marquées **[sécurité]** sont relues avec ce regard en plus.
- **Commits :** en anglais, terminés par `Co-Authored-By: Claude …`, sans ligne `Claude-Session`.
- **PR :** une seule, à la fin, **titre et corps en anglais**, assignée à `gaetinux`.

## Hors périmètre

- **Plan 6b :** « recent sessions to resume » et `meute state`.
- **Plan 6c :** projets créés automatiquement, `meute doctor` (dont la version minimale de git), purge de `session_events`, README final.
- **Non prévu :** l'état Git en base, la suppression de branches, les rappels après un merge (V1.1).

## Points de vigilance (Review Focus)

1. **Un dépôt piégé.** Un `core.fsmonitor`, un pilote de diff ou un `textconv` plantés dans `.git/config` ne doivent jamais s'exécuter pendant le relevé ou la vérification de `W`. Test au Task 1, sur un fichier témoin.
2. **Un nom de branche hostile.** `-x`, `--force`, `a..b`, `feat/`, des espaces, un saut de ligne, ou un nom qui remonte (`../../etc`) : la branche est refusée avant `worktree add`, et aucun dossier n'est créé hors de `<dépôt>.worktrees/`. Test au Task 7.
3. **`W` sur le dossier principal**, ou sur un worktree dont un sous-dossier est le `cwd` d'une session vivante : refus, sans aucun appel à `worktree remove`. Test au Task 10.
4. **Une sortie de git inattendue** : un chemin avec des espaces ou des caractères non UTF-8, un dépôt sans commit (HEAD non né), un sous-module, un rebase en cours. Aucune exception dans le tableau : au pire, pas d'état. Tests `hypothesis` au Task 2 et cas réels au Task 5.
5. **git lent ou bloqué** (verrou NFS, hook qui attend) : le tableau continue de se redessiner, la commande est tuée au bout de 5 s, et le tour suivant repart. Test au Task 5, avec un faux `git` qui dort.

---

### Task 1 : lancer git sans risque (`meute.git.run`) **[sécurité]**

**Fichiers :**
- Créer : `src/meute/git/run.py`, `tests/git_support.py` (fixture `git_repo` et environnement épinglé), `tests/test_git_run.py`
- Modifier : `src/meute/git/discover.py`, qui exporte `main_repo_of`

**Interfaces :**
- `class GitError(Exception)` : son message est déjà le texte à afficher (`git: …`, `git not found`, `git timed out after <n> s`).
- `find_git(environ: Mapping[str, str]) -> Path | None`, avec `shutil.which("git", path=environ.get("PATH"))`, et `None` sans `PATH`.
- `read_args(folder: Path, args: Sequence[str]) -> tuple[str, ...]` : l'argv protégé, sans le chemin de git. Il ajoute `--no-ext-diff --no-textconv` juste après `diff`.
- `read_git(git: Path, folder: Path, args: Sequence[str], *, timeout: float, environ: Mapping[str, str]) -> str` : la sortie standard, décodée en UTF-8 avec `errors="replace"`. Il lève `GitError` sur un code non nul (première ligne de la sortie d'erreur, bornée à 200 caractères) ou un délai dépassé.
- `start_read(git: Path, folder: Path, args: Sequence[str], *, environ: Mapping[str, str]) -> subprocess.Popen[bytes]` : la même commande, sans attendre, pour `GitPoller`.
- `write_git(git: Path, repo: Path, args: Sequence[str], *, timeout: float, environ: Mapping[str, str]) -> str` : `-c core.fsmonitor=false -C <repo>`, hooks gardés.
- `main_repo_of(folder: Path) -> Path | None` : remonte jusqu'au premier dossier qui contient `.git`. Si c'est un dossier, renvoie ce dossier ; si c'est un fichier, applique la règle actuelle de `_main_repo_of_worktree`. `discover` l'utilise sans changer de comportement.
- Le dossier passé à `-C` doit être absolu : `ValueError` sinon (erreur de programmation).

- [ ] **Étape 1 : écrire les tests, qui doivent échouer.**
  - L'argv exact de `read_args` pour `status` et pour `diff`.
  - **Point de vigilance 1 :** sur un `git_repo` dont `.git/config` porte `core.fsmonitor = <script qui touche un témoin>` et un `diff.x.command` / `textconv` liés par `.gitattributes`, `read_git(status…)` et `read_git(diff --numstat HEAD)` ne créent pas le témoin.
  - L'environnement passé : `GIT_TERMINAL_PROMPT=0` et `GIT_OPTIONAL_LOCKS=0`, tout en gardant `PATH` et `HOME`.
  - Un code non nul donne `git: fatal: …` ; un faux `git` qui dort donne `git timed out after 1 s`, et le processus est tué ; un git introuvable donne `git not found`.
  - `main_repo_of` : un dépôt, un sous-dossier, un worktree lié (créé par `git worktree add`), un dossier hors Git, un `.git` fichier qui pointe ailleurs.
  - Les tests de `discover` existants passent sans changement.
- [ ] **Étape 2 : vérifier l'échec.**
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète, puis commit** `git commit -m "feat(git): guarded git runner and main_repo_of"`

---

### Task 2 : état Git (cœur)

**Fichiers :**
- Créer : `src/meute/core/git_state.py`, `tests/test_git_state.py`

**Interfaces :**
- `@dataclass(frozen=True, slots=True, kw_only=True) class GitState` : `branch: str | None`, `detached: str | None`, `upstream: bool`, `ahead: int`, `behind: int`, `dirty: bool`, `added: int = 0`, `removed: int = 0`.
- `parse_status_v2(text: str) -> GitState | None` : lit `# branch.oid`, `# branch.head`, `# branch.upstream`, `# branch.ab +A -B`, puis toute autre ligne non vide (entrées `1`, `2`, `u`, `?`), qui veut dire `dirty`.
  - `branch.head (detached)` donne `detached` = les 7 premiers caractères de l'oid.
  - `(initial)` donne `detached=None` et `branch` lue dans `branch.head`.
  - Il renvoie `None` sans ligne `# branch.head`, et ne lève jamais.
- `parse_numstat(text: str) -> tuple[int, int]` : somme des colonnes 1 et 2, avec `-` (binaire) à 0. Une ligne mal formée est ignorée.
- `git_text(state: GitState) -> str`, selon le tableau de la conception :
  - `main* +12 −3 ↑2 ↓1` ;
  - `feat/x (not pushed)` : branche sans amont, avec `*` et `+N −M` si besoin ;
  - `(detached a1b2c3d)`.
  
  Le signe moins est `−` (U+2212). Le texte passe par `printable`.

- [ ] **Étape 1 : écrire les tests, qui doivent échouer.**
  - Des sorties réelles capturées sur des `git_repo` (propre, modifié, non suivi, en avance et en retard sur un amont local, sans amont, détaché, sans commit, en conflit), figées dans le test comme texte.
  - Chaque `git_text`, avec un instantané `syrupy`.
  - **Point de vigilance 4 :** des propriétés `hypothesis`. `parse_status_v2` et `parse_numstat` ne lèvent jamais, quel que soit le texte, et `git_text` reste sur une seule ligne, sans caractère de contrôle.
- [ ] **Étape 2 : vérifier l'échec.**
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète, puis commit** `git commit -m "feat(core): Git state of a folder"`

---

### Task 3 : worktrees (cœur)

**Fichiers :**
- Créer : `src/meute/core/worktrees.py`, `tests/test_worktrees.py`

**Interfaces :**
- `@dataclass(frozen=True, slots=True, kw_only=True) class Worktree` : `path: Path`, `branch: str | None` (sans `refs/heads/`), `head: str`, `locked: bool`, `prunable: bool`.
- `parse_worktree_list(text: str, main: Path) -> tuple[Worktree, ...]` : les blocs de `git worktree list --porcelain`, séparés par une ligne vide. Il écarte le premier bloc (le dossier principal), tout bloc dont le chemin est `main`, les blocs `prunable` et `bare`, et tout chemin non absolu. Il ne lève jamais.
- `branch_from_title(title: str) -> str` : minuscules ; tout caractère qui n'est ni lettre ASCII, ni chiffre, ni `-`, `_`, `.`, `/` devient `-` ; les tirets répétés sont réduits ; `-`, `.` et `/` sont retirés aux bords ; le résultat est borné à 60 caractères.
- `worktree_path(repo: Path, branch: str) -> Path` : `repo.parent / f"{repo.name}.worktrees" / branch`.
- `branch_error(branch: str) -> str | None` : le contrôle local, fait avant `git check-ref-format`. Il renvoie `branch is empty`, ou `invalid branch name: <b>` si la branche commence par `-`, contient un espace, un caractère de contrôle, `..`, `//`, `\`, `~^:?*[` ou `@{`, finit par `/`, `.` ou `.lock`, ou contient un composant `.` ou `..`. Sinon `None`.
- `@dataclass(frozen=True, slots=True, kw_only=True) class WorktreeCheck` : `path: Path`, `repo: Path`, `branch: str | None`, `locked: bool`, `changes: tuple[str, ...]` (les lignes de `git status --porcelain`), `commits: tuple[str, ...]` (les lignes `git log --oneline`). Propriété `clean -> bool`.
- `listed_text(lines: Sequence[str], limit: int = 10) -> list[str]` : les `limit` premières lignes, passées par `printable`, puis `… and N more`.

- [ ] **Étape 1 : écrire les tests, qui doivent échouer.**
  - `parse_worktree_list` sur des sorties réelles : un worktree verrouillé, un `prunable`, un HEAD détaché, un chemin avec des espaces.
  - `branch_from_title` : `Fix login!` donne `fix-login`, `  ` donne ``, `Été 2026` donne `t-2026`, `feat/X Y` donne `feat/x-y`.
  - **Point de vigilance 2 :** `branch_error` refuse `-x`, `--force`, `a..b`, `feat/`, `a b`, `a\nb`, `../../etc` et `x.lock`. Propriété `hypothesis` : pour toute branche acceptée, `worktree_path(repo, b)` reste sous `repo.parent / "<nom>.worktrees"` (vérifié avec `os.path.normpath`).
  - `listed_text` avec 0, 10 et 11 lignes.
- [ ] **Étape 2 : vérifier l'échec.**
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète, puis commit** `git commit -m "feat(core): worktree list, names and checks"`

---

### Task 4 : ligne Git des cartes (cœur)

**Fichiers :**
- Modifier : `src/meute/core/board_view.py` (`BoardData.git: Mapping[Path, GitState]`, dictionnaire vide par défaut), `src/meute/core/sessions_view_text.py` (`SessionInfo.git: GitState | None = None` ; `card_more_lines`), `src/meute/core/board_sessions.py` (remplit `git`)
- Créer : `src/meute/core/git_folder.py`, `tests/test_card_git_line.py`

**Interfaces :**
- `git_folder(session: Session, metrics: StatuslineData | None) -> Path` : `Path(metrics.worktree_path)` s'il est absolu, sinon `session.cwd`.
- `board_sessions` : `git=data.git.get(git_folder(row.session, data.metrics.get(id)))`.
- `card_more_lines` : avec `info.git`, la ligne 3 vaut `git_text(info.git)`, suivi du nom du worktree de Claude (`metrics.worktree_name`) s'il existe, puis du dernier outil, tous séparés par ` · `. Sans `info.git`, rien ne change.

- [ ] **Étape 1 : écrire les tests, qui doivent échouer.**
  - Chaque cas du tableau de la conception, en largeur normale et en largeur étroite (troncature).
  - Une session Bash avec un état Git a sa ligne 3.
  - Sans état Git, les lignes sont identiques à celles d'aujourd'hui, comparées à `card_more_lines` sans `git`.
  - `git_folder` avec un `worktree_path` absolu, relatif, ou absent.
  - **Les instantanés existants (`test_sessions_view.ambr`, `test_tui_board*`) passent sans changement.**
- [ ] **Étape 2 : vérifier l'échec.**
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète, puis commit** `git commit -m "feat(core): Git state on the session cards"`

---

### Task 5 : `GitPoller` et le backend du tableau **[sécurité]**

**Fichiers :**
- Créer : `src/meute/cli/git_poller.py`, `tests/test_git_poller.py`
- Modifier : `src/meute/cli/board_backend.py`

**Interfaces :**
- `GitPoller(git: Path | None, environ: Mapping[str, str], *, every: float = 10.0, kill_after: float = 5.0, monotonic: Callable[[], float] = time.monotonic, limit: int = 40)`.
  - `poll(folders: Sequence[Path]) -> Mapping[Path, GitState] | None` : il récolte le tour en cours et renvoie le nouveau dictionnaire quand le tour est fini, sinon `None`. Il ne bloque jamais.
  - Il lance un nouveau tour si aucun n'est en cours et si `every` secondes sont passées. Le tour porte sur deux commandes par dossier (`start_read` de `status --porcelain=v2 --branch` et de `diff --numstat HEAD`), sur les `limit` premiers dossiers distincts, et seulement sur les dossiers absolus qui existent.
  - Une commande encore en cours après `kill_after` est tuée, et son dossier est absent du résultat.
  - Un `status` qui échoue (dossier hors Git) laisse le dossier absent. Un `diff` qui échoue (HEAD non né) donne `added = removed = 0`.
- `close() -> None` : tue les commandes en cours.
- `CliBoardBackend.__init__` gagne `git: GitPoller | None = None`. Par défaut, il construit `GitPoller(find_git(environ) if "PATH" in environ else None, environ)`.
  - `_load` passe au poller les dossiers (`git_folder`) des sessions de `data.sessions`, puis de `data.ended`.
  - Un résultat neuf, différent du précédent, force une relecture, comme `claude agents`.
  - La donnée renvoyée est `replace(data, git=<dernier résultat>)`.
  - `close()` ferme aussi le poller.

- [ ] **Étape 1 : écrire les tests, qui doivent échouer.**
  - Sur de vrais `git_repo` : un tour complet donne le bon `GitState`, avec `added` et `removed`.
  - Un dossier partagé par deux sessions n'est relevé qu'une fois.
  - Au plus 40 dossiers, et un seul tour à la fois.
  - Les cas réels du point de vigilance 4 : sous-module, rebase en cours, dépôt sans commit, chemin avec des espaces.
  - **Point de vigilance 5 :** un faux `git` qui dort (script en tête du `PATH` de l'environnement passé). `poll` revient sans attendre, la commande est tuée après `kill_after` (horloge injectée), et le tour suivant repart.
  - Le backend : sans `PATH`, aucun git n'est lancé (faux `git` témoin) ; avec un poller injecté, `load()` porte `git`, et un résultat neuf force la relecture.
  - **Les tests existants de `CliBoardBackend` passent sans changement.**
- [ ] **Étape 2 : vérifier l'échec.**
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète, puis commit** `git commit -m "feat: the board polls the Git state of its sessions"`

---

### Task 6 : dépôt d'un dossier (worktrees liés)

**Fichiers :**
- Modifier :
  - `src/meute/core/repo.py` : `repo_holding` ;
  - `src/meute/core/orphans.py` : `adoption` gagne `main_repo: Path | None = None` ;
  - `src/meute/cli/orphan_actions.py` ;
  - `src/meute/cli/session_commands.py` (`new`) ;
  - `src/meute/cli/board_backend.py` : lancements sans `repo_id` depuis le formulaire avec `none`.
- Créer : `tests/test_repo_holding.py`

**Interfaces :**
- `repo_holding(folder: Path, repos: Sequence[Repo], main_repo: Path | None) -> Repo | None` : le dépôt connu de plus long chemin qui contient `folder`, sinon, à défaut, celui qui contient `main_repo`. C'est la règle actuelle de `adoption`, déplacée.
- `adoption(orphan, repos, main_repo=None)` : sans `main_repo`, le résultat est identique à aujourd'hui.
- `meute session new` : `repo_id = repo_holding(folder résolu, list_repos(db), main_repo_of(folder))`, passé à `ClaudeLaunch` / `BashLaunch`.
- Depuis le tableau, `LaunchBash` / `LaunchClaude` avec `repo_id=None` reçoivent ce même `repo_id`, calculé dans `CliBoardBackend._perform`.

- [ ] **Étape 1 : écrire les tests, qui doivent échouer.**
  - `repo_holding` : dépôts imbriqués, worktree lié hors du dépôt, dossier inconnu.
  - L'adoption d'un orphelin dont le dossier est un worktree lié d'un dépôt connu.
  - `meute session new --cwd <worktree>` (bac à sable, faux `claude`) enregistre le `repo_id` du dépôt principal.
  - **Les tests existants d'adoption et de `session new` passent sans changement.**
- [ ] **Étape 2 : vérifier l'échec.**
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète, puis commit** `git commit -m "feat: sessions in a linked worktree belong to its main repository"`

---

### Task 7 : créer un worktree au lancement **[sécurité]**

**Fichiers :**
- Créer : `src/meute/git/worktree.py`, `src/meute/cli/worktree_launch.py`, `tests/test_worktree_launch.py`
- Modifier :
  - `src/meute/core/board_actions.py` : `LaunchBash` et `LaunchClaude` gagnent `new_branch: str | None = None` ;
  - `src/meute/cli/board_backend.py` ;
  - `src/meute/cli/session_commands.py` : `--worktree` ;
  - `src/meute/cli/context.py` : `GitError` est ajoutée à `ENVIRONMENT_ERRORS`.

**Interfaces :**
- Dans `meute.git.worktree` :
  - `check_branch(git: Path, repo: Path, branch: str, *, environ) -> None` : `git check-ref-format --branch <b>` (lecture protégée), qui lève `GitError` ;
  - `add_worktree(git: Path, repo: Path, path: Path, branch: str, *, environ) -> None` : `write_git(…, ["worktree", "add", str(path), "-b", branch])`, délai de 30 s ;
  - `list_worktrees_text(git, repo, *, timeout, environ) -> str` : lecture protégée de `worktree list --porcelain`.
- Dans `meute.cli.worktree_launch` :
  - `create_worktree(ctx: CliContext, environ: Mapping[str, str], repo: Path, branch: str) -> Path`. Il applique, dans l'ordre :
    1. `branch_error` ;
    2. le chemin `worktree_path`, qui ne doit pas exister (`folder already exists: <chemin>`, affiché avec `~`) ;
    3. `check_branch` ;
    4. `add_worktree`.

    Il renvoie le chemin, et lève `InvalidInput` (contrôles) ou `MeuteError(str(GitError))`.
  - `launch_in_new_worktree(…)` : il lance la session dans le chemin. Si le lancement échoue, il lève `MeuteError("worktree created at <chemin> but the launch failed: <erreur>")`.
- `CliBoardBackend._perform` : avec `new_branch`, le dépôt est celui de `repo_id`, qui est obligatoire (`InvalidInput("a new worktree needs a repository")`). Le worktree est créé, puis la session y est lancée avec `cwd` = le chemin.
- `meute session new --worktree <b>` : le dépôt est `main_repo_of(--cwd ou dossier courant)` (`not in a git repository: <chemin>` sinon). La session est rattachée au dépôt (Task 6) et lancée dans le worktree.

- [ ] **Étape 1 : écrire les tests, qui doivent échouer.**
  - Sur un `git_repo` : le worktree est créé sous `<dépôt>.worktrees/<b>` depuis HEAD, la branche existe, et le dépôt principal ne change pas (`git status` vide, aucun `.gitignore`).
  - Une branche qui existe déjà donne `git: fatal: a branch named 'x' already exists`, et rien n'est lancé.
  - Un chemin existant donne `folder already exists: …`, sans appel à git.
  - **Point de vigilance 2 :** chaque nom refusé au Task 3, passé au backend et à la CLI, ne crée aucun dossier et ne lance jamais `worktree add` (faux `git` témoin).
  - Un lancement qui échoue après la création (faux `claude` absent) donne le message `worktree created at … but the launch failed: …`, et le worktree reste.
  - La CLI `--worktree` dans un dossier hors Git donne `not in a git repository: …`.
- [ ] **Étape 2 : vérifier l'échec.**
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète, puis commit** `git commit -m "feat: launch a session in a new worktree"`

---

### Task 8 : champ `Worktree` du formulaire (cœur)

**Fichiers :**
- Créer : `src/meute/core/launch_form_worktree.py`, `tests/test_launch_form_worktree.py`
- Modifier :
  - `src/meute/core/launch_form.py` : `FormField.WORKTREE` après `REPO`, et `FormField.BRANCH`, visité à la place de `FOLDER` quand `new` est choisi ;
  - `src/meute/core/launch_form_view.py`.

**Interfaces :**
- `LaunchForm` gagne :
  - `worktrees: tuple[Worktree, ...]` et `worktrees_error: str | None` ;
  - `worktree: WorktreeChoice`, une union de dataclasses gelées `NoWorktree() | NewWorktree() | ExistingWorktree(index: int)` ;
  - `branch: str` et `branch_typed: bool`.
- `open_form(…, worktrees: tuple[Worktree, ...] | str = ())` : une chaîne est l'erreur de la liste.
  - Quand le dossier du dépôt choisi est occupé (`_busy`), le formulaire s'ouvre avec `NewWorktree()` et `branch = branch_from_title(title)`.
- Dans `launch_form_worktree.py` :
  - `with_worktrees(form, worktrees: tuple[Worktree, ...] | str) -> LaunchForm` : pour un changement de dépôt. Le choix revient à `NoWorktree()`, puis à `NewWorktree()` si le nouveau dossier est occupé.
  - `cycle_worktree(form, step) -> LaunchForm` : l'ordre est `none`, `new`, puis les existants.
- `type_text` dans `TITLE` met `branch` à jour tant que `branch_typed` est faux. Taper dans `BRANCH` met `branch_typed` à vrai.
- `form_action` :
  - avec `NewWorktree`, il donne `cwd = worktree_path(repo.path, branch.strip())` et `new_branch = branch.strip()`, ou `branch_error` s'il y en a une ;
  - avec `ExistingWorktree`, `cwd = worktree.path`.
- `form_lines` :
  - la ligne `Worktree ◂ none|new|<branche>  <chemin> ▸`, présente seulement avec un dépôt ;
  - avec `new`, `Branch <texte>`, puis `→ <chemin avec ~>`, et pour Claude `Claude will ask whether to trust the new folder` (dim) ;
  - `worktrees_error`, en dim, sous le champ ;
  - la recommandation `⚠ another live session works in this folder: a new worktree is recommended` (`Role.WARN`), qui remplace l'ancien texte dès que le dossier visé est occupé.
- `shares_folder` tient compte du worktree choisi.

- [ ] **Étape 1 : écrire les tests, qui doivent échouer.** Ils couvrent l'ouverture sur un dossier occupé ou libre, le cycle des choix, le préremplissage de `Branch` puis sa saisie, `form_action` pour chaque choix (y compris une branche refusée), `form_lines` avec un instantané `syrupy` (normal, étroit, Bash, Claude, erreur de liste), et un dépôt `none`, qui cache le champ.
- [ ] **Étape 2 : vérifier l'échec, puis lancer toute la suite** et noter les tests existants qui échouent. Seuls ceux de l'exception n° 27 sont admis : tout autre échec est un défaut du code.
- [ ] **Étape 3 : implémenter, puis adapter les tests de l'exception n° 27**, en ne changeant que les attentes déplacées. Les instantanés sont relus ligne par ligne.
- [ ] **Étape 4 : vérification complète, puis commit** `git commit -m "feat(core): Worktree field and recommendation in the launch form"`. Le message liste chaque test adapté (exception n° 27).

---

### Task 9 : formulaire `N` dans le TUI, avec la liste des worktrees

**Fichiers :**
- Créer : `src/meute/cli/board_git.py` (`CliBoardGit`), `tests/test_tui_launch_form_worktree.py`
- Modifier :
  - `src/meute/tui/board_types.py` : protocole `BoardGit` ;
  - `src/meute/tui/board.py` et `src/meute/tui/sessions_tab.py` : `git: BoardGit | None = None` jusqu'à `FormSession` ;
  - `src/meute/tui/launch_form.py` ;
  - `src/meute/cli/__init__.py` : `BoardApp(backend, options, git=CliBoardGit(…))`.

**Interfaces :**
- `BoardGit` (Protocol) : `worktrees(repo: Path) -> tuple[Worktree, ...] | str` et `inspect(folder: Path) -> WorktreeCheck | str`. `inspect` est écrit au Task 10 ; jusque-là, `CliBoardGit.inspect` lève `NotImplementedError`.
- `CliBoardGit(environ)` :
  - `worktrees` lit `list_worktrees_text` (délai de 2 s) et `parse_worktree_list`, puis renvoie `git not found`, ou le texte de `GitError`.
- `FormSession` :
  - à `open` et à chaque changement de dépôt (`←` / `→` sur `REPO`), il demande `git.worktrees(repo.path)`. Sans `git`, il passe `()` ;
  - `Entrée` envoie `LaunchBash` / `LaunchClaude` avec `new_branch` ;
  - les erreurs s'affichent comme aujourd'hui.

- [ ] **Étape 1 : écrire les tests, qui doivent échouer.** Avec `Pilot` et un faux `BoardGit` :
  - l'ouverture sur un dossier occupé montre `new` et la recommandation ;
  - `←` revient à `none` ;
  - le choix d'un worktree existant ;
  - la saisie de `Branch` ;
  - `Entrée` envoie l'action attendue, avec `new_branch` ;
  - l'erreur de liste est affichée ;
  - un instantané SVG en largeur normale et en largeur étroite ;
  - `CliBoardGit.worktrees` sur un vrai `git_repo`.
- [ ] **Étape 2 : vérifier l'échec**, puis adapter les tests existants de l'exception n° 27 qui restent (TUI).
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète, puis commit** `git commit -m "feat(tui): worktrees in the launch form"`

---

### Task 10 : vérifier et enlever un worktree (CLI) **[sécurité]**

**Fichiers :**
- Créer : `src/meute/cli/worktree_commands.py`, `src/meute/cli/worktree_removal.py`, `tests/test_worktree_removal.py`, `tests/test_cli_worktree.py`
- Modifier :
  - `src/meute/git/worktree.py` : `remove_worktree` ;
  - `src/meute/core/board_actions.py` : `RemoveWorktree(repo: Path, path: Path, force: bool)` ;
  - `src/meute/cli/board_backend.py` ;
  - `src/meute/cli/board_git.py` : `inspect` ;
  - `src/meute/cli/__init__.py` : `worktree` sous-application.

**Interfaces :**
- `remove_worktree(git, repo, path, *, force: bool, environ) -> None` : `worktree remove [--force] <path>`. Jamais deux `--force`.
- `inspect_worktree(environ: Mapping[str, str], folder: Path, live_folders: Collection[Path]) -> WorktreeCheck`. Il lève `InvalidInput` avec le texte de la conception, dans cet ordre :
  1. `folder not found` ;
  2. `not a linked worktree` : `main_repo_of` vaut `None`, le dossier est le dépôt principal, ou il est absent de `parse_worktree_list` ;
  3. `the worktree is locked` ;
  4. `a live session works in this worktree` : un dossier de `live_folders`, résolu, est dans le worktree.

  Il lit ensuite, en lecture protégée (5 s) :
  - `status --porcelain` ;
  - `rev-list HEAD --not --remotes --exclude=refs/heads/<b> --branches`, sans `--exclude` pour un HEAD détaché ;
  - puis `log --oneline --no-walk <ces commits>`, au plus 11.
- `CliBoardGit.inspect(folder)` : les dossiers vivants viennent de la dernière donnée du tableau, transmise par `CliBoardGit.live = …` à chaque `load`.
- `RemoveWorktree` est exécutée par `CliBoardBackend._perform`, qui appelle `remove_worktree`.
- `meute worktree list [<dépôt>] [--json]` : les worktrees liés des dépôts connus, avec le chemin (`~`), la branche, `*` et `locked`. `--json` donne `{"worktrees": [{"repo", "path", "branch", "dirty", "locked"}]}`.
- `meute worktree remove <chemin> [--yes] [--force]` : comme la conception. Les sessions vivantes viennent de `list_sessions` après `refresh`.

- [ ] **Étape 1 : écrire les tests, qui doivent échouer.**
  - **Point de vigilance 3 :** le dossier principal, un sous-dossier d'un worktree où vit une session, et un worktree verrouillé sont refusés sans appel à `worktree remove` (faux `git` témoin pour le dernier appel).
  - Un worktree propre, un modifié, un avec un commit propre, un dont le commit est aussi sur une autre branche (non signalé), un en HEAD détaché.
  - La CLI : `list` (texte et JSON, en instantanés), `remove` propre avec `--yes`, `remove` modifié sans `--force` (refus et liste), puis avec `--force --yes`.
  - La branche existe encore après `remove`.
  - `meute session resume` sur une session dont le worktree a été enlevé donne `folder not found: …`.
- [ ] **Étape 2 : vérifier l'échec.**
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète, puis commit** `git commit -m "feat: check and remove a worktree (meute worktree)"`

---

### Task 11 : touche `W` dans le tableau

**Fichiers :**
- Créer : `src/meute/tui/worktree_removal.py`, `tests/test_tui_worktree_removal.py`
- Modifier :
  - `src/meute/tui/sessions_tab.py` ;
  - `src/meute/tui/board_workers.py` : `remove_worktree(action: RemoveWorktree, path_text: str)`, `is_removing(path)` ;
  - `src/meute/core/board_view.py` : `KEYS_HELP`, ligne `W remove the worktree of an ended session`, après la ligne de `r`.

**Interfaces :**
- `WorktreeRemoval` (état de la confirmation) : `Idle | Asking(check) | Listing(check)`. Ses méthodes :
  - `start(check) -> str` : le texte du pied ;
  - `key(character) -> RemoveWorktree | None` ;
  - `footer() -> str | None`.
- `W` sur une session :
  - vivante : `stop the session first` ;
  - terminée : `git.inspect(git_folder(session, metrics))`. Une chaîne va au pied ; un `WorktreeCheck` démarre la confirmation.
  - Sans `git` : `git not available`.
- Une vérification propre demande `y` une fois, puis `RemoveWorktree(force=False)`.
- Une vérification qui ne l'est pas suit `y`, la liste (les fichiers, puis les commits, par `listed_text`), `remove anyway? y/n`, puis `y` et `RemoveWorktree(force=True)`.
- Toute autre touche annule. L'exécution passe par `BoardWorkers`. Le pied affiche `worktree removed: <chemin>` ou l'erreur.

- [ ] **Étape 1 : écrire les tests, qui doivent échouer.** Avec `Pilot` et un faux `BoardGit` :
  - chaque refus ;
  - le chemin propre ;
  - le chemin avec liste, avec 12 fichiers, ce qui affiche `… and 2 more` ;
  - l'annulation à chaque étape ;
  - `--force` seulement après la seconde confirmation ;
  - un instantané SVG de la liste en largeur étroite.
- [ ] **Étape 2 : vérifier l'échec**, puis adapter les tests de l'exception n° 28 (aide `?`).
- [ ] **Étape 3 : implémenter.**
- [ ] **Étape 4 : vérification complète, puis commit** `git commit -m "feat(tui): W removes the worktree of an ended session"`

---

### Task 12 : documentation, mutation, essai, relectures et PR

**Fichiers :**
- Modifier :
  - `README.md` : `W`, le champ `Worktree` de `N`, la ligne Git des cartes, `meute worktree`, `session new --worktree` ;
  - `docs/superpowers/specs/2026-10-15-meute-design.md` : § 6.4, retirer « Reste au plan 6 » pour le worktree ; § 11, renvoyer à la conception ;
  - la feuille de route : 6a fait, 6b et 6c, « Reports issus du plan 6a » ;
  - la conception : section « Écarts constatés à la réalisation » ;
  - `pyproject.toml` : la liste blanche de mutmut gagne les tests du cœur de ce plan.
- Créer : `docs/dev/mutants/2026-plan-6a-python.md`

- [ ] **Étape 1 : la documentation.**
- [ ] **Étape 2 : la mutation.** `rm -rf mutants && uv run mutmut run --max-children 4`, puis `uv run mutmut results`. Les survivants utiles sont tués dans `tests/test_mutants_plan6a.py`, et les autres sont justifiés dans le rapport.
- [ ] **Étape 3 : l'essai scripté**, sur un serveur tmux jetable, avec le faux `claude`, `HOME` et `XDG_*` épinglés, et un dépôt jeté. Il couvre :
  - la ligne Git qui suit une modification ;
  - `N` sur un dossier occupé, qui crée un worktree ;
  - `W`, propre puis avec une liste ;
  - `meute worktree list` et `remove`.

  Le rapport va dans le rapport de mutation, avec la liste des essais manuels pour l'auteur.
- [ ] **Étape 4 : `/simplify`, puis `/security-review`** sur toute la branche. Appliquer les constats, puis faire une vérification complète.
- [ ] **Étape 5 : le commit, puis la PR.** La PR est en anglais, assignée à `gaetinux`. Elle liste les exceptions n° 27 et n° 28, les écarts, les limites et les essais manuels.
