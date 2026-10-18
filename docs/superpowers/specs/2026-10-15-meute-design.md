# Spécification de conception — `meute`, poste de pilotage de sessions Claude Code

- Date : 2026-10-15
- Statut : relue par l'auteur ; mise à jour après les spikes S1 à S5, puis migrée vers Python (spike S6)
- Langue : L'interface est en anglais ; la spécification reste en français.
- Sources : concept initial (non publié), brainstorm du 2026-10-15, mod Claude Code « session-board » v0.33.0
- Nom : `meute` (commande, paquet, chemins). Slogan envisagé : « Lead your pack of coding agents. » Licence : MIT OR Apache-2.0.

## 1. Objet

`meute` est une application Python, TUI et CLI, qui permet de piloter en parallèle plusieurs sessions Claude Code et terminaux Bash depuis un terminal, y compris en SSH, et de les relier à une gestion de tâches légère.

### 1.1 Contexte

L'auteur travaille toute la journée en SSH sur un serveur de développement, dans tmux, avec 6 à 7 sessions Claude Code en parallèle sur des projets différents. Un mod Claude Code (« session-board ») affiche aujourd'hui, dans un panneau latéral de chaque session, l'état de toutes les sessions, les quotas et les tâches. Il fonctionne, mais :

- il vit à l'intérieur de Claude Code et dépend de son système de mods ;
- il est propre à l'installation de l'auteur et n'est pas distribuable ;
- il ne gère pas les terminaux Bash ;
- il y a un panneau par session au lieu d'un poste de pilotage unique.

`meute` doit offrir la même expérience, en mieux, sous forme d'outil autonome et prêt à l'emploi.

### 1.2 Critères de réussite de la V1

1. L'auteur abandonne le mod au profit de `meute` pour son usage quotidien (7 sessions, SSH, tmux).
2. Depuis le tableau de bord, on voit en un coup d'œil quelles sessions attendent une intervention, et on y accède en une touche.
3. Fermer le TUI ou perdre la connexion SSH n'arrête aucune session.
4. Un nouvel utilisateur qui dispose de `tmux` et `claude` lance `meute` et obtient un environnement fonctionnel sans éditer de fichier.

## 2. Principes

1. **Terminal-first** : tout fonctionne en SSH, sans interface graphique.
2. **Local-first** : les données restent sur la machine, sans serveur central.
3. **Le TUI ne possède pas les sessions** : les processus vivent dans tmux.
4. **Observé plutôt que supposé** : un état n'est affiché comme certain que s'il provient d'un événement observé. L'incertitude est affichée comme telle.
5. **Jamais d'action implicite** : rien n'est relancé, fusionné, commité ou supprimé automatiquement. La fin d'une session ne modifie jamais une tâche.
6. **Mécanismes natifs d'abord** : hooks, statusline, `--resume` et permissions de Claude Code. `meute` ne contourne pas les permissions de l'agent.
7. **Ne pas toucher à l'environnement de l'utilisateur** : ni aux fichiers des dépôts, ni à `~/.claude/settings.json`, ni à son tmux personnel.
8. **Un seul cœur métier** : la CLI, le TUI et le MCP appellent les mêmes opérations.

## 3. Périmètre

### 3.1 V1

| Domaine | Contenu |
|---|---|
| Disposition | Tableau de bord fixe dans un panneau tmux, session affichée dans la zone principale (§ 5) |
| Sessions | Lancement Claude Code et Bash, avec ou sans worktree. Échange, rattachement, arrêt explicite |
| Vue Sessions | Regroupement par projet, statut, dernière activité, durée, coût, contexte %, branche et état Git, filtre « needs attention » (permission demandée, réponse attendue, `stuck?`), sessions terminées repliées |
| Quotas | Fenêtres 5 h et 7 j, reset, projection « limit around HH:MM », heures pleines/creuses |
| Vue Tâches | Saisie rapide, filtres, regroupement par urgence ou par projet, détail, notes |
| MCP | Outils de lecture et d'écriture des tâches pour Claude |
| États sauvegardés | Sauvegarder l'ensemble des sessions ouvertes, puis rouvrir un état sauvegardé |
| Reprise | Reprendre une session Claude récente (`--resume`) |
| Statusline | Statusline Claude fournie par `meute` (portage Python du script actuel) |
| Configuration | Fichier TOML commenté créé au premier lancement, commandes `meute config get/set` |

### 3.2 V1.1 — Forges

- Configuration de forges GitHub, Gitea et GitLab dans un écran du TUI.
- PR/MR et état de la CI affichés sur chaque session.
- Rappels après un merge : « back to main », « worktree to delete ».
- Transitions de tâche déclenchées par des faits observés sur la forge (§ 9.4).
- Catalogue des dépôts distants, clonage, puis lancement de session.
- Ordre d'implémentation : GitHub, puis Gitea, puis GitLab.

### 3.3 Plus tard

- Titres de session résumés par Haiku.
- Rapport de temps et de coût.
- Codex et autres agents.
- Lancement de session demandé par Claude via MCP.
- Politique de commit.
- Packaging Nix.
- Service de fond (§ 4.4).
- Tâches récurrentes.
- Création de tâche en langage naturel.

### 3.4 Hors périmètre

- Synchronisation entre machines.
- Fusion automatique.
- Émulation de terminal dans le TUI.

## 4. Architecture

### 4.1 Vue d'ensemble

```
                   ┌────────────── tmux -L meute ──────────────┐
                   │  pane principale        │ pane tableau     │
                   │  (session échangée)     │ `meute board`    │
                   └─────────────────────────┴──────────────────┘
                              ▲ swap-pane / list-windows
                              │
 claude (session gérée) ──hooks──────► meute ingest hook ──┐
        │              ──statusline──► meute ingest status ─┼──► SQLite (WAL) ◄── meute board (TUI)
        └──stdio──► meute mcp ──────────────────────────────┘          ▲
                                                                     meute <cmd> (CLI)
```

- Il n'y a **pas de service de fond en V1**. SQLite en mode WAL est le seul point de rendez-vous entre processus.
- **Claude Code appelle `meute`** (hooks, statusline, MCP stdio). `meute` n'interroge pas Claude Code.
- **tmux détient les processus.** Le TUI peut être fermé et relancé à tout moment.

### 4.2 Une commande, plusieurs sous-commandes

`meute` est le script installé par `uv tool`. Son point d'entrée, `_entry`, dispatche `ingest` avant tout import lourd (Typer, Textual, SDK MCP), pour tenir le budget du § 7.3 (spike S6, § 14).

| Commande | Rôle |
|---|---|
| `meute` | Démarre le serveur tmux dédié si besoin, puis s'y rattache (§ 5) |
| `meute board` | Le TUI du tableau de bord, lancé dans le panneau tmux |
| `meute ingest hook <event>` | Reçoit un hook Claude sur stdin et l'enregistre |
| `meute ingest statusline` | Reçoit le JSON de la statusline, l'enregistre et affiche la statusline |
| `meute mcp` | Serveur MCP stdio, lancé par Claude Code |
| `meute task …`, `meute session …`, `meute state …`, `meute config …`, `meute doctor` | CLI |

### 4.3 Paquet Python

Un seul paquet `meute`, en disposition `src/meute/`, géré par uv (Python 3.13). Chaque package ci-dessous est un sous-package.

| Package | Responsabilité | Peut importer |
|---|---|---|
| `meute.core` | Modèle métier, règles, transitions d'état, accès SQLite et migrations, analyse de la saisie rapide, lecture de la configuration, chemins XDG, modèles de vue | stdlib uniquement |
| `meute.ingest` | `ingest hook` et `ingest statusline` : le chemin chaud | `meute.core` (sous-modules nécessaires seulement), stdlib |
| `meute.tmux` | Pilotage de tmux : serveur dédié, fenêtres, panneaux, `swap-pane`, `capture-pane`, options utilisateur `@meute_*` | stdlib uniquement |
| `meute.git` | Découverte des dépôts, état Git, worktrees | stdlib uniquement |
| `meute.claude` | Adaptateur Claude : construction de la ligne de commande, fichiers `--settings` et `--mcp-config`, interprétation des hooks et de la statusline | `meute.core` |
| `meute.tui` | Écrans Textual | `meute.core`, `textual` |
| `meute.mcp` | Outils MCP | `meute.core`, `mcp` |
| `meute.forge` (V1.1) | Protocole `Forge` et adaptateurs GitHub, Gitea, GitLab | `meute.core` |
| `meute.cli` | Typer, assemblage, édition de la configuration (`tomlkit`) | tous |
| `meute._entry` | Point d'entrée : dispatche sur `sys.argv`, imports paresseux | `meute.ingest`, `meute.cli` |

Règles (vérifiées par import-linter) :

- Le code est **synchrone par défaut**. L'asynchrone n'apparaît que dans `meute.tui` et `meute.mcp`, là où Textual et le SDK MCP l'imposent.
- Toute règle métier vit dans `meute.core`. Les autres packages n'appellent que ses opérations publiques. `meute.core`, `meute.tmux` et `meute.git` sont indépendants les uns des autres ; l'assemblage se fait dans `meute.cli`.
- `meute.tui`, `meute.mcp` et `meute.claude` sont indépendants les uns des autres.
- Seul `meute.cli` importe `typer` et `tomlkit`, seul `meute.tui` importe `textual`, seul `meute.mcp` importe `mcp` (et, en V1.1, seul `meute.forge` importe son client HTTP).
- `meute/core/__init__.py` n'importe ni ne réexporte rien, et `ingest` n'importe que les sous-modules de `core` dont il a besoin : le chemin chaud ne paie que ce qu'il utilise (marge du spike S6 : environ 3 ms). Un test `importtime` échoue si `ingest` importe un module tiers.
- Bibliothèques pressenties :
  - interface : Typer (CLI), Textual (TUI) ;
  - stockage : `sqlite3` de la stdlib, migrations en fichiers SQL numérotés, sans ORM ;
  - configuration : `tomllib` en lecture, `tomlkit` pour `meute config set` ;
  - dates : `datetime` et `zoneinfo` ;
  - divers : `uuid`, chemins XDG codés à la main ;
  - MCP : SDK officiel `mcp` ;
  - forges (V1.1) : un client HTTP synchrone.

### 4.4 Pourquoi pas de service de fond

Les besoins couverts par le service du concept initial sont déjà assurés autrement :

- **persistance des processus** : tmux ;
- **collecte des événements** : hooks et statusline ;
- **état partagé** : SQLite ;
- **réconciliation** : faite à l'ouverture du TUI.

On évite ainsi un protocole de socket, la gestion des versions entre clients, une unité systemd et toute une catégorie de bugs. **Contrepartie** : quand le TUI est fermé, rien n'est interrogé, ni forges ni horloge. Les faits observés pendant cette période sont rattrapés au prochain affichage. Si ce retard devient gênant (notifications système, interrogation des forges), un service de fond pourra être ajouté au-dessus de `meute.core` sans rien réécrire.

### 4.5 Rafraîchissement du TUI

- Le TUI détecte les écritures en interrogeant `PRAGMA data_version` toutes les 500 ms. Il ne relit les données que si la base a changé.
- L'état de tmux (panneaux vivants ou morts) et la sortie de `claude agents --json` (§ 5.5) sont relus toutes les 2 s.
- L'état Git des sessions affichées est relu toutes les 10 s, et à la demande avec la touche `r`.

## 5. Disposition tmux

### 5.1 Serveur dédié

- `meute` utilise son propre serveur, `tmux -L meute`, avec un fichier de configuration généré par l'application. Le tmux personnel de l'utilisateur n'est jamais touché.
- Ce serveur contient deux sessions tmux :
  - `meute` : une fenêtre avec deux panneaux, la zone principale et le tableau de bord. Le tableau est à droite par défaut, sur 60 colonnes, réglable ;
  - `meute-bg` : une fenêtre par session gérée.
- **L'identité d'une session est portée par son panneau, pas par sa fenêtre.** `@meute_id=<uuid>` et `remain-on-exit on` sont posés comme **options de pane** (`set-option -p`). Lors d'un `swap-pane`, une option de fenêtre reste sur la fenêtre et ne suit pas le panneau. Pour la même raison, aucune option `@meute_*` n'est posée sur une fenêtre, puisqu'une option de pane hérite de celle de sa fenêtre (spike S4).
- **Afficher une session** consiste à échanger, avec `swap-pane`, le panneau de la zone principale avec celui de la session. La session précédemment affichée retourne dans la fenêtre de `meute-bg` que l'autre panneau vient de libérer.
- **Si le panneau principal disparaît**, par exemple parce que la session affichée s'est terminée sans `remain-on-exit`, le tableau de bord occupe toute la largeur. meute recrée alors un panneau d'accueil pour retrouver la disposition.
- **Raccourcis globaux**, définis sans préfixe dans la configuration générée et modifiables :
  - `M-p` : focus sur le tableau de bord ;
  - `M-o` : focus sur la zone principale ;
  - `M-n` / `M-N` : session suivante / précédente parmi celles « needs attention ».
- **La barre d'état tmux** affiche la session affichée et le nombre de sessions « needs attention ». Elle est remplacée par une ligne meute (§ 5.6).
- **Se détacher** (`q` dans le tableau de bord, `M-q` partout, `prefix d` ou fermeture du terminal, voir § 5.6) laisse tout tourner. Relancer `meute` permet de se rattacher.

### 5.2 Mode étroit

Si la largeur du client est inférieure à 120 colonnes (réglable), le tableau de bord passe en plein écran :

- `Enter` bascule le client vers la fenêtre de la session ;
- `M-p` revient au tableau de bord.

### 5.3 Lancement depuis un tmux existant

Si `meute` est lancé depuis un tmux (variable `$TMUX` définie), il se rattache au serveur `meute` en mode imbriqué, après avoir retiré `TMUX` de l'environnement, et affiche un avertissement sur les conflits de préfixe. Le spike S4 l'a validé : les raccourcis `M-*` traversent le tmux externe tant que celui-ci ne les utilise pas lui-même. C'est pourquoi ils sont configurables.

### 5.4 Réconciliation

À l'ouverture du TUI, puis à chaque relecture de tmux (`list-panes -a`), chaque session enregistrée « vivante » est comparée aux panneaux portant `@meute_id` :

- **panneau absent** : la session passe à l'état `Unreachable` ;
- **panneau mort** (`pane_dead=1`) : elle passe à l'état `Exited(code)`, avec `code = pane_dead_status` ;
- **panneau `@meute_id` inconnu de la base** : il est affiché comme « orphan », avec deux actions possibles, l'adopter ou le fermer.

Aucune relance n'est automatique.

### 5.5 Sessions Claude lancées hors de meute

- `claude agents --json` liste toutes les sessions Claude actives de la machine, y compris celles lancées en dehors de meute. Pour chacune, il donne `pid`, `cwd`, `kind` (`interactive` / `background`), `sessionId`, `name` et `status` (`busy` / `waiting` / `idle`).
- meute l'appelle à chaque relecture de tmux :
  - les sessions qu'il ne gère pas sont affichées **en lecture seule** dans une section « outside meute », avec leur statut et leur dossier ;
  - pour les sessions qu'il gère, il sert de **source d'état de secours** quand aucun hook n'a été reçu depuis longtemps.
- meute ne lance pas lui-même de sessions `claude --bg`. Avec `--bg`, `--session-id` est ignoré, un dossier non approuvé bloque le démarrage, et la session peut créer des worktrees d'elle-même (spike S1).

### 5.6 Interface transparente

Décision de l'auteur, 2026-10-18. Le but est que l'utilisateur n'ait pas à connaître tmux.

- **Souris active** :
  - un clic sur une ligne du tableau affiche la session ;
  - un clic sur un panneau lui donne le focus ;
  - la molette fait défiler ;
  - la sélection de texte se fait en maintenant `Shift`.
- **Ligne d'état meute** : la barre d'état de tmux est remplacée par une ligne meute, qui affiche la session affichée, le nombre de sessions « needs attention » et le quota 5 h.
- **Bordures** réduites à une ligne discrète.
- **Détacher sans rien arrêter** : `q` dans le tableau et `M-q` partout.
- **Messages et alertes de tmux masqués.**
- **Le préfixe tmux** reste utilisable, mais n'est plus nécessaire.

## 6. Sessions

### 6.1 Modèle

```python
class AgentKind(Enum):
    CLAUDE = "claude"
    BASH = "bash"

# Chaque variante est une dataclass gelée ; seule Exited porte une donnée.
# Les variantes sans donnée sont des dataclasses gelées vides (`case Running():` est sans ambiguïté).
@dataclass(frozen=True, slots=True, kw_only=True)
class Exited:
    code: int | None

SessionState = (
    # observés (événement reçu)
    Running | SubagentRunning | Compacting
    | PermissionRequested   # PermissionRequest : outil et argument connus
    | WaitingInput          # tour terminé (Stop) : « waiting for your reply », compté dans « needs attention »
    | Idle                  # démarrée (SessionStart), aucun prompt encore envoyé
    | Exited
    # déduits de tmux
    | Unreachable           # panneau disparu (redémarrage machine, kill)
    # supposés (affichés avec un « ? »)
    | MaybeStuck            # Running sans événement depuis > N min (défaut 10)
    | Unknown
)
```

Une session comporte les champs suivants :
- un `id` (UUID interne) et un type d'agent ;
- `native_id`, l'identifiant de session Claude ;
- un titre ;
- un projet, un dépôt et une tâche, tous facultatifs ;
- `cwd`, la branche et le worktree ;
- l'état et la dernière activité ;
- le mode de permission ;
- le dernier outil appelé, et le détail de la permission en attente ;
- la dernière réponse de Claude (`Stop.last_assistant_message`, tronquée) ;
- les dernières métriques (§ 7.2) ;
- les dates de création et de fin.

Chaque adaptateur déclare ses capacités (`resume`, `metrics`, `states_observed`). Le TUI n'affiche que les actions disponibles.

### 6.2 Lancement d'une session Claude

`meute.claude` génère deux fichiers, dans `~/.local/state/meute/sessions/<id>/` :
- `settings.json` : les hooks et la statusline, pointant vers `meute ingest …` ;
- `mcp.json` : le serveur `meute mcp`.

Il lance ensuite, en mode interactif, dans une nouvelle fenêtre de `meute-bg` :

```
MEUTE_SESSION=<id> claude --settings <settings.json> --mcp-config <mcp.json> \
    --session-id <uuid> --permission-mode <mode> -n <titre> \
    --append-system-prompt "<contexte composé, § 8>"
```

- Le spike S1 a validé toutes ces options sur Claude Code 2.1.301. `--session-id` est respecté en mode interactif, et `MEUTE_SESSION` est transmise aux hooks et à la statusline. Le hook `SessionStart` confirme l'identifiant natif.
- **Le mode de permission est toujours explicite.** meute passe toujours `--permission-mode`, avec la valeur choisie au lancement, ou celle de la configuration de meute (`claude.permission_mode`), ou `auto` par défaut, la valeur par défaut de Claude Code depuis Opus 5.5 (décision de l'auteur, 2026-10-18). Une session ne doit jamais hériter en silence du mode de l'utilisateur : le mode est toujours passé explicitement. Le spike S1 a montré qu'une session en mode `auto` peut aller jusqu'à pousser sur un remote ; `manual` reste disponible par la configuration ou `--permission-mode`. Le mode est affiché dans la liste des sessions, et les modes `auto`, `bypassPermissions` et `dontAsk` sont signalés en couleur.
- **Dossier non approuvé** : au premier lancement dans un dossier, Claude affiche sa question de confiance (réponse par défaut : « No, exit »). L'utilisateur y répond lui-même dans la zone principale, et meute ne modifie jamais `~/.claude.json`. La confiance ne s'hérite pas du dossier parent, donc chaque nouveau worktree la redemande. Le formulaire de lancement le signale.
- Il reste à vérifier pendant l'implémentation que les réglages passés par `--settings` s'ajoutent à ceux de l'utilisateur sans les écraser, notamment ses propres hooks.
- `~/.claude/settings.json` n'est jamais modifié. Les sessions lancées hors de meute sont visibles via `claude agents --json` (§ 5.5).

### 6.3 Lancement d'une session Bash

Une nouvelle fenêtre de `meute-bg` est ouverte avec `$SHELL` dans le `cwd` choisi. Aucun projet ni aucune tâche n'est requis. Les états possibles sont `Running` (panneau vivant) et `Exited(code)`. Il n'y a ni reprise ni métriques.

### 6.4 Lancement rapide

Depuis la vue Sessions :
- `n` lance, sur le projet ou dépôt sélectionné, le dernier type utilisé (Claude par défaut) dans le répertoire principal ;
- `N` ouvre le formulaire de lancement : type, dépôt, répertoire, worktree (aucun / nouveau / existant) et tâche, avec les valeurs connues préremplies.

Si une autre session vivante travaille déjà dans le même répertoire, le formulaire recommande un worktree, sans l'imposer.

### 6.5 Arrêt et reprise

- **Arrêter** (`x`, avec confirmation) envoie `C-c` deux fois pour une session Claude (une fois pour une session Bash) puis, après 5 s, tue le panneau. La session passe à l'état `Exited`.
- **Reprendre** n'est proposé que pour les sessions Claude dont le panneau a disparu ou dont le processus est terminé. Cette action ouvre un nouveau panneau avec `claude --resume <native_id>`, réutilise l'`id` interne et remplace l'état.
- La liste « recent sessions to resume » affiche les sessions Claude terminées depuis moins de 7 jours (valeur réglable).

### 6.6 États sauvegardés

- **`meute state save [nom]`**, ou l'action correspondante dans le TUI, enregistre la liste des sessions vivantes : type, `cwd`, worktree, `native_id`, titre, tâche et ordre d'affichage.
- **Rouvrir un état** relance chaque session absente : `claude --resume` pour Claude, un nouveau shell dans le même `cwd` pour Bash. Les sessions encore vivantes sont ignorées.
- Les 10 derniers états sont conservés.

## 7. Ingestion des données Claude

### 7.1 Hooks

| Hook | Effet |
|---|---|
| `SessionStart` | Enregistre `native_id`, `transcript_path`, le modèle et le titre. État `Idle` |
| `UserPromptSubmit` | `Running`, enregistre le mode de permission |
| `PreToolUse` | `Running`, enregistre le dernier outil appelé (nom et extrait de l'argument) |
| `PermissionRequest` | `PermissionRequested`, enregistre l'outil et l'argument concernés |
| `PostToolUse` | `Running` (sortie de `PermissionRequested` après approbation) |
| `PreCompact` | `Compacting` |
| `SubagentStart` / `SubagentStop` | `SubagentRunning` / retour à `Running`. **Ignorés si `agent_type` est vide** (tâches internes de Claude, comme la suggestion de prompt) |
| `Stop` | `WaitingInput`, enregistre `last_assistant_message` |
| `SessionEnd` | `Exited` |
| `Notification` | Enregistrée dans l'historique seulement. Pour les permissions, elle fait doublon avec `PermissionRequest`, qui est plus précis |

Le spike S2 a validé ces messages sur Claude Code 2.1.301. Aucune notification d'inactivité (`idle_prompt`) n'a été observée : l'état « waiting for your reply » se déduit donc de `Stop`. `SubagentStart` et `PreCompact` n'ont pas été déclenchés pendant le spike et seront vérifiés pendant l'implémentation. Les messages bruts, nettoyés des chemins personnels, servent de fichiers de test.

### 7.2 Statusline

- `meute ingest statusline` lit le JSON sur stdin et enregistre un relevé de métriques. Les champs ont été confirmés par le spike S3 :
  - `session_id`, `model.id` / `model.display_name`, `effort.level` ;
  - `context_window.used_percentage` ;
  - `cost.total_cost_usd`, `cost.total_duration_ms`, `cost.total_lines_added` / `total_lines_removed` ;
  - `worktree.{name, branch, path}` ;
  - `workspace.repo.{host, owner, name}`, conservé pour détecter la forge en V1.1 ;
  - `rate_limits.five_hour` / `seven_day` : `used_percentage` et `resets_at` (horodatage epoch en secondes).
- La statusline est appelée très souvent, y compris sans terminal attaché. Un relevé n'est donc écrit que si une valeur a changé, ou au plus une fois toutes les 30 s.
- La commande affiche ensuite la statusline : un portage Python du script actuel, avec une largeur adaptative et les mêmes segments.
- Si la configuration contient `statusline.chain = "<commande>"`, la commande indiquée reçoit le même JSON et sa sortie remplace celle de `meute`.

### 7.3 Contraintes des commandes `ingest`

Ces commandes sont appelées par Claude Code à chaque événement. Elles **ne doivent jamais gêner la session** :

- **durée** : moins de 50 ms en temps normal ;
- **écriture en base** : `busy_timeout` de 200 ms. Au-delà, l'événement est abandonné et une ligne est ajoutée dans `~/.local/state/meute/ingest.log` ;
- **erreurs** : le code de sortie est toujours 0 et aucune sortie n'est produite sur stdout, sauf pour la statusline. Une erreur ne doit jamais bloquer ni modifier le comportement de Claude ;
- **session inconnue** : si `MEUTE_SESSION` est absente ou inconnue, l'événement est ignoré.

### 7.4 Quotas et projection

- Les quotas sont propres au compte. On retient le relevé le plus récent, toutes sessions confondues.
- **Projection** : régression linéaire sur les relevés de la fenêtre 5 h des 30 dernières minutes. Si la limite de 100 % est atteinte avant le reset, on affiche « limit around HH:MM at this rate ».
- **Heures pleines** : la plage est réglable. Par défaut, du lundi au vendredi de 8 h à 14 h, heure de New York, comme dans le script actuel. Il s'agit d'une heuristique et elle est documentée comme telle.
- **Couleurs** des pourcentages (quotas et contexte) : vert en dessous de 50 %, orange de 50 à 80 %, rouge au-delà.

## 8. Contexte transmis à Claude

`--append-system-prompt` reçoit un texte composé de trois niveaux, du plus général au plus spécifique :

1. les consignes globales (configuration) ;
2. les consignes du projet ;
3. pour une session liée à une tâche : « You are working on task #N. Read it with the `task_read` tool and report your progress with `task_note_add`. »

Le texte de la tâche n'est pas injecté : Claude le lit via MCP.

**Règle de résolution des contradictions**, écrite en tête du texte composé : « The repository's `CLAUDE.md` files are authoritative on code conventions. The task is authoritative on the goal. If they contradict each other, point it out to the user instead of choosing. »

`meute` n'écrit jamais dans le dépôt.

## 9. Tâches

### 9.1 Modèle

```python
# Chaque variante est une dataclass gelée ; seule Blocked porte une donnée.
# Les variantes sans donnée sont des dataclasses gelées vides (`case Todo():` est sans ambiguïté).
@dataclass(frozen=True, slots=True, kw_only=True)
class Blocked:
    reason: str

TaskStatus = Todo | InProgress | Blocked | Review | Done

class Priority(Enum):
    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
```

Une tâche comporte les champs suivants :
- un `id` (entier, affiché `#N`) et un titre ;
- une description, une priorité et un statut ;
- une échéance, un projet et un dépôt, tous facultatifs ;
- un champ `version`, entier incrémenté à chaque écriture ;
- ses dates de création et de mise à jour.

À chaque tâche sont associées :
- des **notes** : texte, auteur et date ;
- des **événements d'historique** : champ, ancienne valeur, nouvelle valeur, auteur et session.

L'auteur vaut `user`, `claude` ou `system` et est accompagné du canal : `tui`, `cli`, `mcp` ou `forge`.

### 9.2 Concurrence

Toute écriture fournit la `version` attendue. Si elle ne correspond pas, l'opération est rejetée et l'état courant est renvoyé. Il n'y a jamais d'écrasement silencieux. Dans le TUI, un conflit affiche « modified in the meantime », puis recharge la tâche.

### 9.3 Saisie rapide

Syntaxe :

```
free title [@project] [!|!!] [>due]
```

- `!` correspond à la priorité haute et `!!` à la priorité urgente.
- `>due` accepte les formes `>tomorrow`, `>tonight`, `>mon`, `>mon-9am`, `>mon-2pm`, `>+2h`, `>+30m`, `>+3d`, `>2026-10-20` et `>2026-10-20T14:00`. Pour l'heure d'un jour nommé, une seule forme est acceptée : `9am` / `2pm` (pas de `14:00` après un nom de jour) ; `>+2h`, `>+30m` et `>+3d` sont des durées relatives (heures, minutes, jours).
- Les jetons non reconnus restent dans le titre.
- Le résultat analysé est affiché avant la validation.

### 9.4 Transitions automatiques

- **Règle** : seul un fait observé sur une ressource externe peut faire avancer une tâche, et uniquement vers l'avant.
- **Jamais de transition automatique** à la fin d'une session, ni après un crash ou une interruption.
- **V1** : aucune transition automatique. Claude peut changer le statut via MCP, ce qui est historisé.
- **V1.1** : une PR ou MR ouverte pour une session liée fait passer la tâche à `Review`. Une PR ou MR fusionnée la fait passer à `Done`. Ces transitions sont historisées avec l'auteur `system/forge`.

### 9.5 Vue Tâches

Fonctionnalités reprises du mod :
- les filtres `all · this project · floating` (une tâche volante n'a pas de projet) ;
- le regroupement par urgence (overdue, today, upcoming, no due date, done today) ou par projet ;
- les compteurs de tâches ouvertes et en retard ;
- une ligne par tâche, avec un symbole de statut (`·` `»` `✕` `◎` `✓`), `!`/`!!`, le titre, `@project`, puis l'échéance ou la raison du blocage ;
- un détail avec l'édition des champs, des reports rapides (+1 h, tonight 6 pm, tomorrow 9 am, Monday 9 am, clear), les notes, les sessions liées et l'action « launch Claude on this task ».

La suppression demande une confirmation et n'est possible que depuis le TUI ou la CLI.

## 10. Projets et dépôts

- **Dépôt** : découvert dans les racines configurées (par défaut `~/git`) par un parcours limité à une profondeur de 3. Les worktrees sont rattachés à leur dépôt principal et ne sont pas comptés en double. Le type de dépôt (fastapi, angular, node, python, rust…) est déduit par des règles simples sur les fichiers présents.
- **Projet** : un nom, une description, des consignes, et un ou plusieurs dépôts. Au premier lancement d'une session dans un dépôt sans projet, un projet du même nom est créé automatiquement et lié à ce dépôt. Plusieurs dépôts peuvent ensuite être regroupés dans un même projet.
- **Vue Sessions** :
  - les sessions sont regroupées par projet, à défaut par dépôt, à défaut sous `Other`, en attendant la création automatique des projets (plan 6) ;
  - l'en-tête de chaque projet affiche son nom, son type, son temps et son coût, et se replie en une ligne de résumé ;
  - les projets sans session vivante sont listés en bas, avec l'action « + session ».

## 11. Worktrees et Git

- **Nouveau worktree** : `git worktree add <parent-du-dépôt>/<dépôt>.worktrees/<branche> -b <branche>`. Le dépôt n'est pas modifié et aucune entrée `.gitignore` n'est ajoutée.
- **Pas de worktrees natifs de Claude** : meute n'utilise pas `claude -w`, qui crée le worktree dans `<dépôt>/.claude/worktrees/<nom>`, donc à l'intérieur du dépôt, avec un risque de pollution de `git status` si `.claude/` n'est pas ignoré (spike S5). Les worktrees créés par Claude lui-même (outil `EnterWorktree`) restent visibles grâce à `worktree.*` dans la statusline, et sont affichés comme tels.
- **Nettoyage** : uniquement par une action explicite. Il est refusé s'il reste des modifications non commitées ou des commits non poussés, sauf si l'utilisateur confirme une seconde fois en voyant la liste.
- **Informations affichées par session** : branche, `*` s'il reste des modifications non commitées, lignes ajoutées et retirées, commits à pousser ou à tirer (↑ ↓), mention « not pushed ».
- **Ce que `meute` ne fait jamais** : commit, fusion, push.

## 12. MCP

Le serveur stdio `meute mcp` propose les outils suivants :

| Outil | Effet |
|---|---|
| `task_list` | Filtres : projet, statut, échéance. Renvoie des résumés |
| `task_read` | Tâche complète, avec ses notes et sa `version` |
| `task_create` | Titre et champs facultatifs, projet déduit de la session |
| `task_update` | Champs et `expected_version` |
| `task_set_status` | Statut, raison si bloquée, et `expected_version` |
| `task_note_add` | Ajout d'une note |
| `task_link_session` | Lie la session courante à une tâche |

- Les outils de suppression et d'arrêt de session ne sont pas exposés. **La V1 n'a donc pas besoin du mécanisme de confirmations en attente** : il ne sera conçu que si un outil sensible est ajouté.
- L'identité de la session appelante provient de `MEUTE_SESSION`. Les écritures sont historisées avec `claude/mcp` et l'identifiant de session.
- Les réponses ne contiennent que les données demandées.

## 13. Configuration et données

- **Emplacements** (XDG) :
  - configuration : `~/.config/meute/config.toml` ;
  - base : `~/.local/share/meute/meute.db` ;
  - état : `~/.local/state/meute/`.
- **Premier lancement** : écriture d'une configuration par défaut, commentée et fonctionnelle. Une configuration existante n'est jamais écrasée.
- **`meute config get/set`** modifie le TOML en préservant les commentaires (`tomlkit`).
- **`meute doctor`** vérifie les versions de `tmux` (minimum 3.2, pour les options de pane) et de `claude`, l'accès à la base, l'état du serveur tmux dédié et les options de Claude utilisées.
- **`claude.permission_mode`** : le mode de permission par défaut des sessions lancées par meute (`auto` si rien n'est défini, § 6.2).
- **Migrations SQLite** : versionnées, appliquées à l'ouverture, avec une sauvegarde de la base (`meute.db.bak-<version>`) avant chaque migration.
- **Tables** : `projects`, `repos`, `project_repos`, `tasks`, `task_notes`, `task_events`, `sessions`, `session_events`, `metric_samples`, `quota_samples`, `saved_states`.
- **Purge** : les relevés de métriques de plus de 30 jours sont supprimés au démarrage du TUI.
- **V1.1** : `credentials.toml` (droits `0600`) pour les tokens des forges, ou le trousseau système s'il est disponible, ou `token_cmd`/`token_env`. Les tokens ne sont jamais stockés en base ni intégrés dans une URL de clone.

## 14. Spikes réalisés

Les spikes S1 à S5 ont été réalisés le 2026-10-15 sur Claude Code 2.1.301 et tmux 3.5a. Le détail se trouve dans `docs/superpowers/spikes/2026-10-15-spikes-s1-s5.md`. Le spike S6 (démarrage de Python) a été réalisé le 2026-10-16 ; son rapport est `docs/superpowers/spikes/2026-10-16-spike-s6-demarrage-python.md`.

| # | Question | Résultat |
|---|---|---|
| S1 | Options de `claude` | ✅ Toutes présentes. `--session-id` respecté en mode interactif, ignoré avec `--bg`. Mode de permission à passer explicitement (§ 6.2) |
| S2 | Hooks | ✅ États observables. On s'appuie sur `PermissionRequest` et `Stop`, et on ignore les `SubagentStop` internes (§ 7.1) |
| S3 | JSON de la statusline | ✅ `session_id`, quotas avec `resets_at`, `workspace.repo` (§ 7.2) |
| S4 | Disposition tmux | ✅ Échange entre sessions, imbrication et raccourcis `M-*`. Options de pane uniquement (§ 5.1) |
| S5 | Worktrees natifs | Ils existent, mais on garde la convention du § 11 |
| S6 | Démarrage de `meute ingest` en Python | ✅ Médiane ≈ 46,7 ms avec `--compile-bytecode` (bande 35–50 ms) : on continue, le test `importtime` reste un garde-fou strict (§ 4.3, § 7.3). [Rapport](../spikes/2026-10-16-spike-s6-demarrage-python.md) |

Restent à vérifier pendant l'implémentation :
- l'ajout des réglages de `--settings` à ceux de l'utilisateur ;
- le contenu effectif de `--mcp-config` et `--append-system-prompt` ;
- les hooks `SubagentStart` et `PreCompact`.

## 15. Décisions ouvertes, non bloquantes

- La couleur et le placement du tableau de bord (à droite ou à gauche).
- La forme exacte des commandes CLI et de leur sortie `--json`.

## 16. Gestion des erreurs

- **tmux absent ou trop ancien** : erreur explicite au démarrage, avec la version minimale requise et une indication d'installation.
- **`claude` absent** : les sessions Bash restent disponibles et le lancement de sessions Claude est désactivé, avec la raison.
- **Base indisponible ou verrouillée** : la vue Sessions continue à partir de tmux, sans métriques. La vue Tâches affiche « Tasks unavailable: reason ».
- **Commandes `ingest`** : voir § 7.3.
- **Code** : les erreurs sont des exceptions typées (hiérarchie `MeuteError` dans `meute.core`, avec des données attachées, par exemple `VersionConflict`), traduites en messages et en codes de sortie par la CLI. Pas d'`assert` hors des tests.

## 17. Tests

- **`meute.core`** : tests unitaires des transitions d'état, de la concurrence par version, de l'analyse de la saisie rapide (cas tirés du § 9.3, plus des propriétés hypothesis) et des migrations (base vide, puis base de la version précédente).
- **`meute.claude`** : tests à partir des messages réels enregistrés pendant les spikes S2 et S3.
- **`meute.tmux`** : tests d'intégration sur un serveur jetable `tmux -L meute-test-<uuid>`, sans jamais toucher aux serveurs réels.
- **`meute.tui`** : trois niveaux. Modèle de vue pur dans `meute.core.views`, testé en texte avec syrupy ; comportement avec `App.run_test` et `Pilot` ; rendu avec `pytest-textual-snapshot`, en largeur normale et en largeur étroite.
- **Sorties de la CLI** : instantanés syrupy, relus ligne par ligne.
- **CI et règle de projet** (CLAUDE.md) : chaque changement passe `bash scripts/verify.sh` (ruff, basedpyright, import-linter, pytest, deptry, pip-audit, licences). Détail des outils : `docs/dev/developpement-assiste-par-ia.md`.

## 18. Ordre de réalisation indicatif

Le plan d'implémentation détaillera les étapes suivantes :

1. ~~Spikes S1 à S6~~ (réalisés, § 14).
2. Paquet Python, `meute.core` (modèle, base, migrations) et CLI des tâches.
3. `meute.tmux` et disposition (§ 5), avec des sessions Bash.
4. Adaptateur Claude : lancement, ingestion et statusline.
5. TUI : vue Sessions, quotas, filtre « needs attention ».
6. TUI : vue Tâches, puis MCP.
7. Worktrees, reprise et états sauvegardés.
8. Préparation de la V1 : `doctor`, configuration par défaut, documentation.
