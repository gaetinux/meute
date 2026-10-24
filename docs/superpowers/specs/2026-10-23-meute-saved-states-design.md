# meute — Conception du plan 6b : reprise et états sauvegardés

- Spécification générale : `docs/superpowers/specs/2026-10-15-meute-design.md`, § 3.1 (« États sauvegardés », « Reprise »), § 6.5 (« Reste au plan 6 » : la liste des sessions récentes) et § 6.6 (états sauvegardés), § 13 (table `saved_states`).
- Feuille de route : `docs/superpowers/plans/2026-10-15-meute-v1-roadmap.md` (plan 6b).
- Branche : `feat/plan-6b-python`, créée sur `main` à jour (166fc28, après le merge de la PR #14).

## Intention

Après une journée de travail, ou après un redémarrage de la machine, on retrouve ses sessions en une touche : `O` rouvre l'ensemble des sessions qui tournaient, Claude reprend chaque conversation là où elle était, et Bash rouvre un shell dans le même dossier. On peut aussi garder des ensembles nommés (« revue », « refonte ») et reprendre une session Claude récente depuis la CLI.

## Périmètre (décisions de l'auteur, 2026-10-23)

- **Sessions récentes** : seulement les sessions lancées par meute. `e` les montre déjà (plan 4) ; la durée devient réglable, et la CLI gagne `meute session recent` et `meute session resume`.
- **Tableau** : `S` sauvegarde un état horodaté, `O` ouvre la liste des états et en rouvre un. Le nom personnalisé passe par la CLI.
- **État automatique `last`** : tenu à jour par le tableau, jamais vide, hors des 10 états conservés.
- **Bash** : à la réouverture, une session Bash est ignorée si une session Bash vivante travaille déjà dans le même dossier.
- Hors périmètre :
  - les conversations Claude démarrées hors de meute (`~/.claude/projects/`) ;
  - un écran dédié aux sessions récentes ;
  - la reprise de l'historique ou des processus d'un shell ;
  - le choix du nom dans le tableau.

## Sessions récentes

- **Réglage** : `[ui] recent_days = 7`, un entier de 1 à 365, validé comme les autres clés (`meute config set ui.recent_days 14`). Il remplace la constante `RECENTLY_ENDED` (7 jours) de `cli/board_data.py`. `e` montre les sessions terminées depuis moins de `recent_days` jours ; le texte `+ N ended (e to show)` ne change pas.
- **`meute session recent [--json]`** : les sessions Claude de meute terminées depuis moins de `recent_days` jours, la plus récente d'abord. Une ligne par session : id court, titre, dossier (avec `~`), âge (`3h`, `2d`), puis `resumable` (le `native_id` est connu) ou `no conversation id`. `--json` donne `{"sessions": [{"id", "title", "cwd", "ended_at", "resumable"}]}`.
- **`meute session resume <id|préfixe>`** : appelle `resume_session`, comme `r` dans le tableau, avec les mêmes messages d'erreur. Elle affiche `Resumed: <id court> <titre>`.
- `r` reste la seule touche de reprise dans le tableau.

## Contenu et stockage d'un état

### Contenu

Un état est la liste des sessions vivantes au moment de la sauvegarde, dans l'ordre du tableau (`board_order`). Pour chaque session :

| Champ | Contenu |
|---|---|
| `session_id` | l'id meute, qui permet de reprendre la même ligne |
| `agent` | `claude` ou `bash` |
| `cwd` | le dossier ; le worktree d'une session est son dossier |
| `native_id` | l'id de la conversation Claude, ou `null` |
| `title` | le titre |
| `task_id`, `repo_id` | la tâche et le dépôt, ou `null` |
| `displayed` | `true` pour la session affichée dans la zone principale |

### Stockage

- La migration `005_saved_states.sql` crée la table `saved_states` : `id INTEGER PRIMARY KEY`, `name TEXT NOT NULL UNIQUE`, `created_at TEXT NOT NULL` (instant UTC, format habituel), `sessions TEXT NOT NULL` (le JSON de la liste).
- Le JSON est lu par un analyseur du cœur qui ne lève jamais : une entrée illisible (champ manquant, type faux, id invalide) est ignorée, et un document illisible donne une liste vide.

### Noms

- `meute state save [nom]` : sans nom, le nom est l'heure locale, `2026-10-24 09:12` ; si ce nom existe déjà (deux sauvegardes dans la même minute), l'état existant est remplacé.
- Sauver sous un nom qui existe remplace l'état, qui devient le plus récent.
- Un nom passe par `one_line`, est borné à 60 caractères, et ne peut être vide (`state name is empty`). `last` est réservé : `last is kept by the board`.

### Rétention

Au-delà de 10 états nommés, les plus anciens (par `created_at`) sont supprimés dans la même transaction que la sauvegarde. `last` ne compte pas dans les 10.

### L'état `last`

- Le backend du tableau compare, à chaque relecture, la liste des sessions vivantes (ids, dans l'ordre du tableau) à la dernière liste écrite. Si elle a changé **et n'est pas vide**, il réécrit `last`. Il n'écrit rien sinon.
- Ainsi, quand tout est arrêté par `x`, ou après un redémarrage de la machine (les sessions deviennent `Unreachable` au démarrage du tableau), `last` garde la dernière liste non vide.
- La dernière liste écrite est relue en base au démarrage du tableau : un tableau qui redémarre n'écrase pas `last`.

## Rouvrir un état

`meute state open <nom>`, ou `Entrée` dans la liste de `O`, traite les sessions dans l'ordre enregistré :

| Cas | Ce qui se passe |
|---|---|
| la session (même id) est vivante | ignorée : `already running` |
| Claude, ligne connue en base avec un `native_id` | `resume_session` sur cette ligne, comme `r` : même id, même tâche, même titre, même panneau mort s'il existe encore |
| Claude sans `native_id`, ou ligne supprimée de la base | ignorée : `no conversation id` |
| Bash, et une session Bash vivante travaille déjà dans ce dossier (chemins résolus) | ignorée : `already running` |
| Bash | une nouvelle session Bash dans le même dossier, avec le même titre et le même dépôt (nouvel id) |
| dossier disparu (par exemple un worktree enlevé) | ignorée : `folder not found: <chemin>` |
| le lancement échoue (`claude` absent, erreur de tmux, configuration invalide) | ignorée, avec le message de l'erreur ; les sessions suivantes continuent |

- À la fin, la session marquée `displayed` est remise dans la zone principale, si elle a été rouverte ou si elle tournait déjà.
- Compte rendu : `reopened <n> · skipped <m>`. La CLI ajoute une ligne par session ignorée, `  <titre>: <raison>`, et sort avec le code 0 (1 seulement si l'état n'existe pas : `no saved state named <nom>`).
- La réouverture n'arrête ni ne tue jamais rien.
- Une session Bash rouverte ne retrouve ni son historique ni ses processus.

## Tableau

- **`S`** (onglet Sessions) sauvegarde un état horodaté ; le pied confirme `state saved: <nom>`.
- **`O`** ouvre la liste des états, un bloc au-dessus du pied comme le formulaire `N` :
  - `last` d'abord, puis les 10 états nommés, du plus récent au plus ancien ;
  - une ligne par état : `<nom>  <n> sessions  <âge>` (`1 session` au singulier) ;
  - `↑` / `↓` choisissent, `Entrée` rouvre, `Échap` ou toute autre touche ferme ;
  - sans état, la liste montre `no saved state` ;
  - la relecture du tableau toutes les 2 s ne change pas la sélection.
- La réouverture se fait hors du fil de l'interface, par `BoardWorkers` ; le pied montre `reopening <nom>…`, puis le compte rendu. Un second `Entrée` pendant ce temps est ignoré.
- L'aide `?` gagne la ligne `S save the open sessions · O reopen a saved state`.

## CLI

- `meute state save [nom]` → `Saved: <nom> (<n> sessions)`.
- `meute state list [--json]` → une ligne par état, comme dans `O` ; `--json` donne `{"states": [{"name", "created_at", "sessions"}]}`, où `sessions` est le nombre.
- `meute state open <nom>` → le compte rendu.
- `meute state rm <nom> [--yes]` → confirmation `Remove saved state "<nom>"? [y/N]`, puis `Removed: <nom>`. `last` peut être supprimé ; le tableau le recrée à la prochaine liste non vide.
- `meute session recent [--json]` et `meute session resume <id>`, décrites plus haut.

## Architecture

| Paquet | Nouveau ou modifié |
|---|---|
| `meute.core` | `saved_state.py` (`SavedSession`, `SavedState`, JSON et analyseur, noms, `RETAINED = 10`, `LAST = "last"`, texte du compte rendu) ; `db/saved_states.py` (lecture, écriture, rétention dans une transaction) ; `db/sql/005_saved_states.sql` ; `config_validate.py` (`ui.recent_days`) ; `board_view.py` (`KEYS_HELP`, `BoardData.saved_states` pour `O`) |
| `meute.cli` | `state_commands.py` (`meute state …`) ; `state_reopen.py` (réouverture, qui réutilise `resume_session`, `launch_bash` et `show_session`) ; `last_state.py` (mise à jour de `last` par le backend) ; `session_commands.py` (`recent`, `resume`) ; `board_data.py` (`recent_days`) |
| `meute.tui` | touches `S` et `O`, panneau de la liste (`tui/saved_states_panel.py`), `BoardWorkers.reopen` |

Les contrats d'import ne changent pas.

## Erreurs

- **Base indisponible** pendant une sauvegarde : l'erreur habituelle, dans le pied ou sur la sortie d'erreur ; rien n'est écrit.
- **État inconnu** : `no saved state named <nom>` (code de sortie 1).
- **Nom invalide** : `state name is empty`, `last is kept by the board`.
- **Session ignorée à la réouverture** : sa raison, sans arrêter les autres.

## Tests

- **Migration 005** : base vide, puis base de la version précédente (avec sauvegarde `meute.db.bak-<version>`).
- **Analyseur du JSON** : propriétés `hypothesis` (ne lève jamais, aller-retour d'un état valide), instantanés `syrupy`.
- **Rétention et noms** : 11 états donnent 10, `last` est exclu, remplacement d'un nom existant, nom horodaté, nom réservé.
- **`last`** : jamais vide ; rien n'est écrit si la liste ne change pas ; un tableau qui démarre après un redémarrage (sessions `Unreachable`) ne l'écrase pas.
- **Réouverture** : chaque ligne du tableau de la section « Rouvrir un état », avec le faux `claude` sur un serveur tmux jetable, jamais les serveurs `meute` ni `default`.
- **Sessions récentes** : `recent_days`, `meute session recent` (texte et JSON, instantanés), `meute session resume`.
- **TUI** : `S` et `O` avec `Pilot`, instantanés en largeur normale et étroite.
- **Fin de plan** : `mutmut`, essai scripté, `/simplify` et `/security-review`.
- **Exception demandée** : n° 29, les tests et instantanés qui montrent l'aide `?` gagnent la ligne `S save the open sessions · O reopen a saved state`.

Pas de spike : la reprise sous meute (`claude --resume`) est validée par S10.

## Limites acceptées

- Une session Bash rouverte est un shell neuf.
- Une session Claude sans `native_id` (Claude n'a jamais envoyé `SessionStart`) ne se rouvre pas.
- `last` reflète la dernière relecture du tableau : une session lancée et arrêtée entre deux relectures n'y figure pas.

## Écarts constatés à la réalisation

Ce que le plan 6b a fait autrement que ce texte, ou précisé en le réalisant (les numéros sont ceux du registre de décisions du plan, les « décisions » celles du plan lui-même).

- **Exception n° 31 (Task 3, autorisée par l'auteur le 2026-10-24)** : la migration 005 fait passer la version du schéma de 4 à 5. Six tests de `main` fixaient la version 4 ou la liste des tables (`test_db_open.py`, `test_db_sessions.py`, `test_db_claude_sessions.py`) ; ils passent à 5 et gagnent `"saved_states"` dans la liste des tables, rien d'autre. L'exception n° 30 (clé `ui.recent_days` dans une liste de toutes les clés) n'a pas servi : aucun test ne liste toutes les clés.
- **`NotFound` et son texte (R5)** : `NotFound` gagne un argument nommé facultatif, `message`, qui remplace le texte `<entité> not found: <id>` ; l'entité, l'identifiant et le code de sortie ne changent pas. Un état inconnu donne ainsi exactement `no saved state named <nom>`. La CLI de `meute state open` et `rm` sort avec le code 1, et non le 4 des autres absences, comme le veut ce texte.
- **Sauvegarde par suppression puis insertion (R6)** : `save_state` supprime l'état du même nom puis en insère un neuf, dans la même transaction ; un état renouvelé reçoit un nouvel id. Deux sauvegardes au même instant sont ainsi rangées par ordre de sauvegarde (`created_at DESC, id DESC`), et l'état qui vient d'être sauvé n'est jamais celui que la rétention supprime, sauf si l'horloge recule (voir la feuille de route).
- **Noms tels que tapés pour `open` et `rm` (R2)** : seul `meute state save` passe le nom par `state_name` ; `open` et `rm` le prennent tel quel, si bien que `meute state rm last` fonctionne.
- **`LastState.follow`** : le backend appelle `LastState(db).follow(data)` juste après `load_board_data`. Quand `last` vient d'être écrit, `follow` relit la liste des états (`BoardData.saved_states`) : la liste de `O` montre le nouveau `last` sans attendre la relecture suivante, puisqu'une écriture de cette connexion ne change pas sa `data_version`.
- **Instantané des sessions vivantes avant la réouverture (R9)** : la réouverture relit les sessions une seule fois, avant la boucle (ids vivants, et sessions Bash vivantes par dossier résolu). Un état qui contient deux sessions Bash du même dossier revient donc entier, et une seconde réouverture ne double toujours rien. Un état écrit à la main qui contient deux fois le même id Claude rouvre le premier, puis ignore le second avec le texte de `resume_session`, `"<titre>" is still running`, au lieu de `already running`.
- **Comptes rendus du tableau par `ActionNotice(MeuteError)` (Task 7)** : `state saved: <nom>` et `reopened <n> · skipped <m>` remontent de `CliBoardBackend._perform` (et de `BoardWorkers`) par une exception `ActionNotice`, dérivée de `MeuteError`, que le tableau attrape avant `MeuteError` et montre comme une information, pas comme une erreur. Coût : un futur appelant qui n'attraperait que `MeuteError` afficherait `Error: state saved: …` (relevé dans la feuille de route).
- **Refus de `rm`** : répondre autre chose que `y` à `Remove saved state "<nom>"? [y/N]` affiche `Cancelled.` et sort avec le code 0, comme les autres confirmations de la CLI ; l'état reste.
- **La liste de `O` reste ouverte après `Entrée`** : `Entrée` lance la réouverture et laisse la liste ouverte ; le pied montre `reopening <nom>…`, puis le compte rendu. `Échap` ou toute autre touche la ferme.
- **`S` avant la première lecture** : si le tableau n'a encore rien lu, `S` fait d'abord une lecture, puis sauve les sessions qu'elle donne ; sinon il sauve celles de la dernière lecture, dans l'ordre du tableau.
- **filelock 4.2.1 (R4)** : six nouvelles failles de filelock 4.2.0 faisaient échouer `pip-audit`, donc `scripts/verify.sh` et la CI. Le verrou passe à 4.2.1 avec une exemption datée `exclude-newer-package`, sur le modèle de celle de certifi au plan 5, dans un commit `build:` séparé. Elle est à retirer au prochain rafraîchissement du verrou.
- **Limites relevées** : voir la feuille de route, « Reports issus du plan 6b ».
