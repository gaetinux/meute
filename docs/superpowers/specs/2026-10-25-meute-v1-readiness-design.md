# meute — Conception du plan 6c : préparation de la V1

- Spécification générale : `docs/superpowers/specs/2026-10-15-meute-design.md`, § 9.5 (« Projet d'une session », « Projet créé depuis un dépôt »), § 10 (projets et dépôts), § 13 (`meute doctor`, purge).
- Feuille de route : `docs/superpowers/plans/2026-10-15-meute-v1-roadmap.md` (plan 6c, et les limites connues des plans 3 et 6a).
- Branche : `feat/plan-6c-python`, créée sur `main` à jour (f6f32e4, après le merge de la PR #15).

## Intention

Dernier plan avant la V1. Un nouvel utilisateur installe meute, lance `meute doctor`, voit ce qui manque et quoi faire, puis lance `meute` : ses sessions se rangent sous des projets créés pour lui, la base ne grossit plus sans limite, et le README suffit pour s'en servir sans aide.

## Périmètre (décisions de l'auteur, 2026-10-25)

- **Projets créés automatiquement** : au lancement d'une nouvelle session par meute seulement ; aucune migration de rattrapage pour les sessions et dépôts déjà en base.
- **`meute doctor`** : constate seulement (jamais de réparation), code de sortie 1 s'il y a un `fail` ; pas de `--json`.
- **Purge de `session_events`** : 30 jours, au démarrage du tableau, avec la purge des relevés.
- **README final**, documents mis à jour, et version du paquet `1.0.0`. Le tag et la release restent à l'auteur.
- Hors périmètre : la création d'un projet à l'adoption d'un orphelin ou pour une session extérieure ; un `--fix` ; une rétention réglable ; un plafond d'événements par session ; `VACUUM`.

## Projets créés automatiquement

### Règle

Au lancement d'une **nouvelle** session par meute (`launch_bash`, `launch_claude`, donc `c`, `n`, `N`, `L`, `meute session new` et la réouverture d'une session Bash d'un état), quand le dossier appartient à un dépôt connu (worktrees liés compris, rattachés à leur dépôt principal comme au plan 6a), le projet de la session est, dans cet ordre :

1. le `project_id` demandé (celui de la tâche, pour `L` ou une tâche choisie dans `N`) ;
2. le projet lié au dépôt par `project_repos` (le plus petit identifiant, comme `repo_project_links`) ;
3. le projet qui porte le nom du dépôt, casse et espaces ignorés ;
4. sinon, un projet créé par `create_repo_project(db, <nom du dépôt>)`, qui existe déjà (§ 9.5) : il crée le projet et lui rattache tous les dépôts de ce nom, et reprend un projet du même nom créé entre-temps par une autre fenêtre.

La session est enregistrée avec ce `project_id`. Une session sans dépôt connu (dossier hors des racines, hors de tout dépôt) garde `project_id` vide et reste sous `Other`, ou sous son projet demandé s'il y en a un.

### Ce qui ne crée rien

- `r` (et la réouverture d'une session Claude d'un état, qui passe par la reprise) : la session existe déjà, sa ligne n'est pas réécrite ; elle retrouve le projet par le nom de son dépôt dès qu'il existe (règle de `project_of`).
- L'adoption d'un panneau orphelin et les sessions extérieures.
- Les sessions et dépôts déjà en base : le projet d'un dépôt naît au prochain lancement dedans. D'ici là, le regroupement par dépôt montre déjà le même nom.

### Ordre et erreurs

- Le projet est résolu, et créé au besoin, **avant** le démarrage de tmux, pour que le contexte composé du § 8 lise le bon projet (consignes de projet).
- Si tmux ou l'enregistrement de la session échoue ensuite, le projet reste : c'est celui que le lancement suivant créerait de toute façon.
- Une `MeuteError` ou une `sqlite3.Error` pendant la résolution fait échouer le lancement comme toute erreur de base : rien n'est démarré.
- Aucun message dans le pied du tableau : le groupe garde le même nom ; le projet apparaît dans `meute project list`, le filtre « this project » et le `@` des tâches.

### Architecture

- `cli/launch_project.py` : `launch_project(ctx: CliContext, repo_id: RepoId | None, project_id: ProjectId | None) -> ProjectId | None`, appelée par `launch_bash` et `launch_claude` (le seul chemin des nouvelles sessions). La règle de choix (étapes 1 à 3) est une fonction pure de `meute.core.session_project`, à côté de `project_of` et `repo_projects`, qu'elle réutilise.
- Pas de migration ; pas de changement de `create_session`.

## `meute doctor`

### Principe

`meute doctor` ne modifie rien : il n'écrit pas la configuration par défaut, ne migre pas la base, ne démarre pas tmux. Il affiche une ligne par vérification et sort avec 1 s'il y a au moins un `fail`, 0 sinon. Chaque commande extérieure a un délai de 5 s ; un délai dépassé est un `fail` (`<outil> did not answer within 5 s`).

### Vérifications, dans cet ordre

| Vérification | `ok` | `warn` | `fail` |
|---|---|---|---|
| tmux | 3.3 ou plus | 3.2 : `M-t needs tmux 3.3 or later` | absent ; moins de 3.2 ; version illisible |
| git | 2.36 ou plus | — | absent, ou moins de 2.36 : `worktrees and the Git line need git 2.36 or later` |
| claude | trouvé dans le `PATH` (règle de `find_claude`), `claude --version` 2.1.301 ou plus | plus ancien que 2.1.301 (version des spikes), ou version illisible | absent |
| options de claude | `claude --help` cite `--settings`, `--mcp-config`, `--session-id`, `--resume`, `--permission-mode`, `--append-system-prompt` | — | une option manque : elle est nommée |
| configuration | le fichier se lit, ou il est absent (valeurs par défaut, écrites au premier lancement) | — | `ConfigError`, avec son message |
| base | ouverte en lecture seule, schéma à jour | schéma plus ancien : `migrated at the next start` ; base absente : `created at the first start` | impossible à ouvrir ; schéma plus récent que meute |
| dossier d'état | existe et accepte l'écriture (`os.access`), ou absent avec un parent où l'écrire | — | impossible d'y écrire |
| serveur tmux `meute` | en marche : `running, <n> sessions` ; arrêté : `not running (meute starts it)` | — | — |

Une ligne `note` termine la liste : `--append-system-prompt-file (used above 8000 bytes of context) is not in claude --help and cannot be checked`.

Les vérifications suivent leur ordre même après un `fail` : le diagnostic est complet en une fois. Les options de claude ne sont pas vérifiées si claude est absent.

### Sortie

```
ok    tmux      3.5a
ok    git       2.47.3
ok    claude    2.1.302
ok    options   claude --help lists every option meute uses
ok    config    ~/.config/meute/config.toml
ok    database  ~/.local/share/meute/meute.db (schema 5)
ok    state     ~/.local/state/meute
ok    server    tmux server meute: running, 4 sessions
note  --append-system-prompt-file (used above 8000 bytes of context) is not in claude --help and cannot be checked
```

Les niveaux sur 6 colonnes, les noms sur 10. Les chemins passent par `shown_path`, toute sortie d'un outil extérieur par `printable`, coupée à la première ligne. La dernière ligne, après un `fail` ou un `warn`, dit `<n> problem(s) found` ; sinon rien de plus.

### Architecture

- `core/doctor.py` (stdlib seule) : `CheckLevel` (`OK`, `WARN`, `FAIL`, `NOTE`), `Check` (dataclass gelée : niveau, nom, texte), le classement des versions (`tmux`, `git`, `claude` : analyse des sorties de `-V`, `--version`), le rendu des lignes et le code de sortie. Analyseurs testés par `hypothesis` (jamais d'exception sur une sortie quelconque).
- `cli/doctor.py` : les relevés. Ils réutilisent `shutil.which`, `find_claude`, `load_config`, les chemins XDG de `CliContext`, et un `TmuxClient` sur le socket `meute` (lecture seule : `list-sessions`) dont le socket est un paramètre, pour les tests. Les commandes passent par `subprocess.run` avec `timeout=5`, sans shell, `stdin` fermé.
- **Base en lecture seule** : une ouverture nouvelle, `sqlite3.connect("file:<chemin>?mode=ro", uri=True)`, qui lit `PRAGMA user_version` sans migrer ni sauvegarder (le chemin est échappé pour l'URI).
- `meute doctor` n'ouvre pas `open_context` (qui crée la configuration et migre la base).

## Purge de `session_events`

- La purge de démarrage du tableau (`purge_samples`, renommée `purge_old_rows`) supprime aussi les lignes de `session_events` dont `created_at` a plus de 30 jours, dans la même transaction et avec la même date limite (`SAMPLE_RETENTION`, renommée `RETENTION`). Elle renvoie le total des trois tables. Les sessions elles-mêmes restent.
- **Limite connue du plan 3 corrigée** : une `sqlite3.Error` ou une `MeuteError` pendant la purge (base verrouillée) n'empêche plus le tableau de démarrer ; la purge est sautée sans message et retentée au démarrage suivant.
- Pas de `VACUUM`.

## README et documents

- **README** (anglais) :
  - statut : `**Status:** V1.` ;
  - **Requirements** : Python 3.13 et uv, tmux 3.2 (3.3 pour `M-t`), git 2.36, Claude Code ;
  - **Getting started** : `uv tool install`, `meute doctor`, `meute` ; configuration par défaut au premier lancement ; racines de dépôts (`~/git` par défaut) ;
  - **Projects** : le projet créé au premier lancement dans un dépôt, le regroupement de plusieurs dépôts, les consignes de projet ;
  - **Data** : emplacements XDG, purge à 30 jours, rien ne quitte la machine ;
  - **Troubleshooting** : `meute doctor` et chaque `fail` ;
  - les sections existantes (touches, worktrees, états, MCP) restent, relues pour la cohérence.
- **Spécification générale** : § 9.5 (la mention « en avance sur le plan 6 »), § 10 (« en attendant la création automatique des projets (plan 6) »), § 13 (`doctor` tel que réalisé, git 2.36, purge de `session_events`).
- **Feuille de route** : 6c fait ; une section « Après la V1 » reprend ce qui reste ouvert (V1.1 : forges ; limites connues encore ouvertes).
- **Version** : `pyproject.toml` passe à `1.0.0` (`meute --version`).

## Tests

- **Projets** : un lancement Bash puis Claude dans un dépôt sans projet crée le projet, le lie au dépôt et remplit `project_id` ; un second lancement réutilise le projet ; une tâche d'un autre projet garde le sien ; un dépôt lié à un projet d'un autre nom garde ce projet ; un dépôt dont le nom est celui d'un projet existant le rejoint ; un worktree lié rejoint le projet de son dépôt principal ; un dossier hors dépôt ne crée rien ; l'adoption et `r` ne créent rien ; un échec de tmux laisse le projet et aucune session ; le contexte composé lit les consignes du projet trouvé.
- **`doctor`** : faux `tmux`, `git` et `claude` dans un `PATH` de test, un par cas du tableau (absent, trop vieux, illisible, muet au-delà du délai, option manquante) ; base temporaire à jour, ancienne, plus récente, illisible, absente ; configuration invalide ; dossier d'état sans droit d'écriture ; serveur tmux jetable en marche et arrêté ; code de sortie ; instantané `syrupy` de la sortie complète ; `doctor` ne crée ni configuration ni base ni dossier (vérifié après coup). Jamais les sockets `meute` ou `default`, jamais le vrai `claude`.
- **Purge** : un événement de 31 jours part, un de 29 jours reste, le total compte les trois tables ; une base verrouillée laisse le tableau démarrer.
- Mutation en fin de plan (`docs/dev/mutants/2026-plan-6c-python.md`) et essai scripté sur un serveur tmux jetable.

## Limites acceptées

- Un projet créé pour un lancement qui échoue ensuite reste en base (vide de sessions).
- Deux dépôts du même nom dans deux racines partagent un projet (règle existante de `create_repo_project`).
- `doctor` ne vérifie pas `--append-system-prompt-file` (absent de `claude --help`), ni que les hooks de Claude se déclenchent vraiment.
- La version minimale de claude (2.1.301) est celle des spikes, pas une limite connue de Claude Code : plus ancien n'est qu'un `warn`.
