# meute — Conception du plan 6a : état Git et worktrees

- Spécification générale : `docs/superpowers/specs/2026-10-15-meute-design.md`, § 3.1 (« branche et état Git »), § 6.4 (formulaire `N`, « Reste au plan 6 »), § 10 (dépôts et worktrees) et § 11 (worktrees et Git).
- Feuille de route : `docs/superpowers/plans/2026-10-15-meute-v1-roadmap.md`. Le plan 6 est découpé en trois plans (décision de l'auteur, 2026-10-23) :
  - **6a, Git et worktrees**, l'objet de ce document ;
  - **6b, reprise et états sauvegardés** : « recent sessions to resume » et `meute state` ;
  - **6c, préparation de la V1** : projets créés automatiquement, `meute doctor`, purge de `session_events` et README.
- Branche : `feat/plan-6a-python`, créée sur `main` à jour (f4d5a2a, après le merge de la PR #13).

## Intention

On voit d'un coup d'œil où en est chaque session côté Git : sa branche, ce qui n'est pas commité, ce qui n'est pas poussé. Deux sessions ne se marchent plus sur les pieds dans le même dossier, parce que le formulaire `N` crée ou choisit un worktree, et le recommande quand le dossier est déjà occupé. Un worktree devenu inutile se nettoie depuis le tableau, sans jamais perdre de travail en silence.

meute ne fait toujours ni commit, ni fusion, ni push, ni `fetch` (§ 11).

## Périmètre (décisions de l'auteur, 2026-10-23)

- **État Git** relevé en fond, au plus toutes les 10 s, sans jamais bloquer l'interface.
- **Nouveau worktree** créé depuis le HEAD du dépôt principal (`git worktree add <chemin> -b <branche>`), sans accès réseau.
- **Recommandation** : quand le dossier du dépôt est déjà occupé par une session vivante, le formulaire s'ouvre avec `Worktree` sur `new`.
- **Nettoyage** : `git worktree remove` seulement ; la branche est toujours gardée. Touche `W` sur une session terminée, et `meute worktree list` / `meute worktree remove` en CLI. Tous les worktrees liés sont concernés (ceux de meute, ceux de Claude, ceux faits à la main), jamais le dossier principal du dépôt.
- Hors périmètre :
  - l'état Git en base ;
  - une mention « worktree » sur les cartes ;
  - la suppression de branches ;
  - les rappels « worktree to delete » après un merge (V1.1, forges) ;
  - la vérification de la version de git au démarrage (`meute doctor`, plan 6c).

## Lancer git sans risque

meute lance git dans des dépôts que Claude peut modifier. Un `.git/config` piégé peut faire exécuter une commande par un simple `git status` (`core.fsmonitor`) ou par `git diff` (pilote de diff externe, `textconv`). Toutes les commandes de **lecture** passent donc par une seule fonction de `meute.git`, qui ajoute toujours :

- `-c core.fsmonitor=false` et `--no-optional-locks` (ne jamais prendre le verrou de l'index que l'utilisateur ou Claude pourrait vouloir) ;
- `--no-ext-diff` et `--no-textconv` pour `diff` ;
- l'environnement `GIT_TERMINAL_PROMPT=0` et `GIT_OPTIONAL_LOCKS=0` ;
- un délai maximal (5 s pour le relevé de fond, 2 s pour la liste des worktrees du formulaire) ;
- `-C <dossier>` avec un chemin absolu, jamais un argument tiré d'une sortie de git sans validation.

Les commandes d'**écriture** (`worktree add`, `worktree remove`) gardent les hooks Git de l'utilisateur (`post-checkout`, par exemple) : c'est son dépôt, et il les attend. Elles prennent aussi `-c core.fsmonitor=false`.

`--no-optional-locks` demande git 2.15 ou plus. Sur une version plus ancienne, la commande échoue et le message de git est repris tel quel.

## L'état Git des sessions

### Relevé

- `GitPoller`, dans `meute.cli`, suit le modèle de `AgentsPoller` : pas de thread, des processus lancés sans attendre et récoltés aux relectures suivantes.
  - À chaque relecture du tableau (2 s), il récolte les commandes terminées.
  - Au plus toutes les 10 s, et seulement si le tour précédent est fini, il lance un nouveau tour.
  - Une commande qui dure plus de 5 s est tuée ; ce dossier n'a pas d'état jusqu'au tour suivant.
- Les dossiers relevés sont ceux des sessions affichées : les vivantes, et les terminées quand `e` les montre. Chaque dossier n'est relevé qu'une fois par tour, même si plusieurs sessions le partagent.
- Le dossier d'une session est `worktree.path` de sa dernière statusline quand Claude l'indique (un worktree créé par Claude lui-même), sinon son `cwd`.
- Deux commandes par dossier, lancées en parallèle :
  - `git status --porcelain=v2 --branch` : la branche (ou HEAD détaché et son commit), l'amont, ↑ et ↓, et s'il reste des modifications, fichiers non suivis compris ;
  - `git diff --numstat HEAD` : les lignes ajoutées et retirées, indexées ou non. Un fichier binaire (`-`) ne compte pas.
- Le résultat reste en mémoire dans le backend du tableau. Rien n'est écrit en base.

### Modèle

`meute.core.git_state` (stdlib seulement) :

- une dataclass gelée `GitState` : `branch: str | None`, `detached: str | None` (commit court), `upstream: bool`, `ahead: int`, `behind: int`, `dirty: bool`, `added: int`, `removed: int` ;
- des analyseurs purs, `parse_status_v2(text) -> GitState | None` et `parse_numstat(text) -> tuple[int, int]`, qui ne lèvent jamais sur une entrée inattendue (testés avec `hypothesis`) ;
- `git_text(state) -> str`, le texte affiché.

`meute.git.status` lance les commandes et renvoie le texte brut. Le contrat d'import interdit à `meute.git` d'importer `meute.core` : l'analyse se fait donc dans le cœur, et c'est `meute.cli` qui assemble.

### Affichage

La ligne 3 de la carte d'une session (`└ …`) montre l'état Git à la place de la branche de la statusline. Les sessions Bash y ont donc droit aussi :

| Cas | Ligne 3 |
|---|---|
| modifiée, avec un amont | `└ main* +12 −3 ↑2 ↓1 · Edit` |
| propre, à jour | `└ main · Edit` |
| branche sans amont | `└ feat/x (not pushed)` |
| HEAD détaché | `└ (detached a1b2c3d)` |
| pas encore relevée, ou hors Git | la branche de la statusline, comme aujourd'hui, ou rien |

- `*` : modifications non commitées, fichiers non suivis compris. `+N −M` n'apparaît que si l'un des deux est non nul ; `↑N` et `↓N` seulement s'ils sont non nuls.
- Le nom du worktree créé par Claude (statusline) reste affiché comme aujourd'hui, à côté.
- La ligne est tronquée à la largeur, comme le reste de la carte (mode étroit compris).
- `meute session show` amène le panneau de la session et n'affiche rien : l'état Git reste propre au tableau.

## Le worktree dans le formulaire `N`

### Champ `Worktree`

Le formulaire gagne un champ `Worktree`, juste après `Repo`, présent seulement quand un dépôt est choisi. `←` / `→` en changent la valeur :

| Choix | Effet |
|---|---|
| `none` | `Folder` reste éditable, comme aujourd'hui. |
| `new` | `Folder` devient `Branch`, un champ texte, et le chemin calculé s'affiche dessous : `→ ~/git/meute.worktrees/<branche>`. |
| un worktree existant | affiché `<branche>  <chemin>` ; `Folder` prend son chemin, en lecture seule. |

- Le chemin d'un nouveau worktree est `<parent du dépôt>/<nom du dépôt>.worktrees/<branche>` (§ 11). Une branche `feat/x` donne le sous-dossier `feat/x`.
- `Branch` est prérempli à partir du titre (minuscules, tout ce qui n'est ni lettre, ni chiffre, ni `-`, `_`, `.`, `/` devient `-`, tirets répétés réduits, bornes retirées) tant que l'utilisateur ne l'a pas tapé lui-même. Il doit être rempli : `branch is empty`.
- La liste des worktrees existants vient de `git worktree list --porcelain` du dépôt, lue à l'ouverture du formulaire et à chaque changement de dépôt (délai maximal 2 s). Le dossier principal du dépôt n'y figure pas, ni un worktree dont le dossier a disparu (`prunable`). Si la commande échoue, seuls `none` et `new` sont proposés, et la raison s'affiche sous le champ (`git not found`, par exemple).
- Avec `new` et le type Claude, le formulaire prévient : `Claude will ask whether to trust the new folder` (§ 6.2).

### Recommandation

Elle remplace l'avertissement `⚠ another live session works in this folder`.

- Quand le dossier du dépôt est déjà celui d'une session vivante (chemins résolus, la session sélectionnée compte), le formulaire s'ouvre avec `Worktree` sur `new` et `Branch` prérempli, et affiche `⚠ another live session works in this folder: a new worktree is recommended`.
- `←` revient à `none` ; le message reste tant que le dossier choisi est occupé.
- Pour un dossier tapé à la main (`none`) ou un worktree existant occupé, le même message s'affiche, sans rien changer.

### Lancement avec `new`

1. Le chemin calculé ne doit pas exister (`folder already exists: …`), et la branche doit passer `git check-ref-format --branch` (le message de git est repris sinon).
2. meute lance `git -C <dépôt> worktree add <chemin> -b <branche>` (depuis HEAD du dépôt principal), puis la session dans ce dossier, rattachée au dépôt.
3. Si `worktree add` échoue, rien n'est lancé et le formulaire reste ouvert avec l'erreur : `git: <première ligne du message>`, bornée à 200 caractères.
4. Si la session échoue après la création du worktree, le worktree reste et l'erreur le dit : `worktree created at <chemin> but the launch failed: …`.

Le lancement se fait sur le fil de l'interface, comme aujourd'hui pour `N` (limite connue du plan 4c).

### Dépôt d'un dossier

Une session dont le dossier est dans un worktree lié d'un dépôt connu est rattachée à ce dépôt principal. Aujourd'hui, elle n'aurait aucun dépôt, puisque le worktree est hors du dossier du dépôt.

- `meute.git` expose la règle déjà utilisée par la découverte : `main_repo_of(folder)` remonte jusqu'au dossier qui contient `.git`, et quand c'est un fichier qui pointe vers `<principal>/.git/worktrees/<nom>`, renvoie `<principal>`.
- Le cœur garde sa règle (le dépôt connu de plus long chemin qui contient le dossier) et l'applique au dossier, puis, à défaut, au dépôt principal renvoyé.
- La règle sert au formulaire (`none` avec un dossier tapé, worktree existant), à `meute session new` et à l'adoption d'un orphelin.

### CLI

- `meute session new --worktree <branche>` crée le worktree depuis le dépôt de `--cwd` (ou du dossier courant), avec les mêmes contrôles, puis lance la session dedans. Le dossier doit appartenir à un dépôt Git : `not in a git repository: …`.
- `meute session new --cwd <worktree existant>` est rattachée au bon dépôt.

## Nettoyer un worktree

### Touche `W`

`W` agit sur la session terminée sélectionnée. Son dossier doit être un worktree lié de son dépôt, selon `git worktree list --porcelain` : un worktree de meute, de Claude ou fait à la main, jamais le dossier principal. Sinon, le pied du tableau dit pourquoi :

- `not a linked worktree: <chemin>` ;
- `a live session works in this worktree` (n'importe quelle session vivante dont le dossier est dans ce worktree) ;
- `the worktree is locked` ;
- `folder not found: <chemin>` ;
- `W` sur une session vivante : `stop the session first`.

### Vérification

meute relève, avec les protections de lecture :

- les fichiers modifiés ou non suivis (`git status --porcelain`) ;
- les commits que seul ce worktree possède, ni sur un remote, ni sur une autre branche locale : `git rev-list HEAD --not --remotes --exclude=refs/heads/<sa branche> --branches` (sans `--exclude` pour un HEAD détaché). Comme la branche est gardée, ils ne sont pas perdus, mais la spécification demande de les signaler (§ 11).

### Confirmations

- **Rien à signaler** : une confirmation simple, `remove worktree <chemin>? (branch <b> is kept) y/n`.
- **Sinon** : une première confirmation, `<chemin> has uncommitted changes or unpushed commits: y shows them, n cancels`, puis une seconde qui montre la liste (10 fichiers et 10 commits au plus, puis `… and N more`) et demande `remove anyway? y/n`.

### Exécution

- Elle passe par `BoardWorkers`, hors du fil de l'interface, comme l'arrêt et la reprise.
- La commande est `git -C <dépôt principal> worktree remove <chemin>`, avec `--force` seulement après la seconde confirmation. Un worktree verrouillé est toujours refusé (pas de `--force --force`).
- La branche reste. Les sessions terminées de ce dossier restent en base.
- Le pied confirme `worktree removed: <chemin>` ou montre l'erreur de git.

### CLI

- `meute worktree list [<dépôt>]` : les worktrees liés des dépôts connus (ou d'un seul), avec le chemin, la branche, `*` s'il reste des modifications et `locked`. `--json` donne la même chose en JSON.
- `meute worktree remove <chemin> [--yes] [--force]` :
  - sans `--force`, refuse s'il reste des modifications ou des commits propres au worktree, et affiche la même liste ;
  - `--force` enlève quand même, après une confirmation qui montre la liste ;
  - `--yes` saute la confirmation.

### Reprise après nettoyage

`r` sur une session dont le dossier n'existe plus répond déjà `folder not found: <chemin>` (`resolve_folder`, plan 4c) ; rien à ajouter, un test le fixe pour un worktree enlevé.

## Architecture

| Paquet | Nouveau ou modifié |
|---|---|
| `meute.git` | `run.py` (lancement des commandes de lecture et d'écriture, `GitError`) ; `status.py` (textes bruts du relevé) ; `worktree.py` (`list_worktrees_text`, `add_worktree`, `remove_worktree`, `worktree_only_commits`) ; `main_repo_of` sorti de `discover.py` |
| `meute.core` | `git_state.py` (`GitState`, analyseurs, `git_text`) ; `worktrees.py` (`Worktree`, analyse de `worktree list --porcelain`, chemin et branche d'un nouveau worktree) ; `launch_form.py` (champ `Worktree`, `Branch`, recommandation) ; `board_actions.py` (`LaunchClaude` / `LaunchBash` gagnent `new_branch: str | None` ; `RemoveWorktree`) ; `sessions_view_text.py` (ligne 3) ; `orphans.py` (dépôt principal) |
| `meute.cli` | `git_poller.py` ; `worktree_commands.py` (`meute worktree`) ; lancement avec `new_branch` ; `session new --worktree` ; `GitError` traduite en `MeuteError` |
| `meute.tui` | touche `W` et ses deux confirmations, `BoardWorkers.remove_worktree` ; rendu du champ `Worktree` |

Les contrats d'import ne changent pas : `meute.core` ne connaît ni `meute.git` ni les sous-processus.

## Erreurs

- **git absent** : les cartes n'ont pas d'état Git ; `Worktree` ne propose que `none` et affiche `git not found` ; `W` et `meute worktree` répondent `git not found`.
- **Commande qui échoue** : le message de git, première ligne, bornée à 200 caractères, préfixée de `git: `.
- **Délai dépassé** : `git timed out after <n> s`.
- **Code** : `GitError` (dans `meute.git`) est traduite par `meute.cli` en `MeuteError`, comme `TmuxError`.

## Tests

- **Analyseurs** (`parse_status_v2`, `parse_numstat`, `worktree list --porcelain`, nom de branche tiré du titre, `git_text`) : cas tirés de sorties réelles capturées avec git 2.47, propriétés `hypothesis` (jamais d'exception, texte toujours sur une ligne), instantanés `syrupy`.
- **Commandes** : de vrais dépôts jetables (`git init` dans `tmp_path`), avec `HOME`, `GIT_CONFIG_GLOBAL`, `GIT_CONFIG_NOSYSTEM` et `XDG_CONFIG_HOME` épinglés. Jamais les dépôts de l'auteur.
- **Sécurité** : un dépôt de test plante un `core.fsmonitor` et un pilote de diff qui écrivent un fichier témoin ; le relevé et la vérification du nettoyage ne le créent pas.
- **`GitPoller`** : horloge injectée, commandes lentes tuées après 5 s, un seul tour à la fois, un dossier partagé relevé une fois.
- **Formulaire et `W`** : modèle pur testé en texte ; `Pilot` pour les touches et les deux confirmations ; instantanés en largeur normale et étroite ; faux `claude` sur un serveur tmux jetable, jamais les serveurs `meute` ni `default`.
- **Fin de plan** : `mutmut`, essai scripté, `/simplify` et `/security-review` sur toute la branche.

## Points d'attention pour la relecture

- Toute commande git de lecture passe par la fonction protégée ; aucune ne prend un chemin tiré d'une sortie sans le vérifier (absolu, sous le dépôt ou son dossier `.worktrees`, ou dans la liste de `git worktree list`).
- `W` ne peut jamais viser le dossier principal d'un dépôt, ni un worktree où vit une session.
- `--force` n'est passé qu'après la seconde confirmation (TUI) ou avec `--force` explicite (CLI).
- Le tableau ne bloque jamais sur le relevé Git.

## Limites acceptées

- L'état Git peut avoir 10 s de retard.
- La liste des worktrees du formulaire est lue sur le fil de l'interface (2 s au plus).
- ↑ et ↓ dépendent du dernier `fetch` de l'utilisateur.
- Un worktree supprimé à la main reste le dossier de ses sessions terminées ; `r` le signale.
