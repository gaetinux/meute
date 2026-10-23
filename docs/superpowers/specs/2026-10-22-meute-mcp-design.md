# meute — Conception du plan 5 : MCP et contexte composé

- Spécification générale : `docs/superpowers/specs/2026-10-15-meute-design.md`, § 8 (contexte transmis à Claude), § 9.6 (« Launch Claude on this task ») et § 12 (MCP).
- Conception de la migration : `docs/superpowers/specs/2026-10-16-migration-python-design.md` (paquet `meute.mcp`, SDK officiel, asynchrone limité à ce paquet).
- Branche : `feat/plan-5-python`, créée sur `main` à jour (aec39fb, après le merge de la PR #12).

## Intention

Une session Claude lancée par meute lit elle-même sa tâche et rend compte de son avancement (`task_read`, `task_note_add`, `task_set_status`), sans copier-coller. Elle reçoit aussi les consignes globales et celles de son projet. Le texte complet de la tâche n'est plus collé dans Claude : le contexte composé du § 8 le remplace, comme le prévoyait le § 9.6.

## Périmètre (décisions de l'auteur, 2026-10-22)

- **§ 8 et § 12 complets** :
  - les 7 outils MCP ;
  - `--mcp-config` sur chaque session Claude ;
  - le contexte composé dans `--append-system-prompt` ;
  - un moyen d'écrire les consignes globales et celles des projets.
- **SDK officiel `mcp`**, sous sa forme `FastMCP`, plutôt qu'un JSON-RPC écrit à la main.
- **`L`, et `N` avec une tâche**, collent « Work on task #N. » sans l'envoyer, au lieu du texte complet de la tâche.
- Hors périmètre :
  - les outils de suppression, d'arrêt de session ou de projets ;
  - les confirmations en attente (§ 12) ;
  - le serveur MCP pour des sessions Claude lancées hors de meute (`meute mcp` peut s'y ajouter à la main, sans garantie).

## Le serveur `meute mcp`

### Découpage

- `meute mcp` lance un serveur stdio, construit avec `FastMCP` du SDK : chaque outil est une fonction typée, et le SDK en déduit le schéma.
- `meute.mcp` n'importe que `meute.core` et `mcp`, selon les contrats d'imports existants.
  - Il définit `McpBackend`, un protocole synchrone avec une méthode par outil.
  - C'est `meute.cli` qui l'implémente (`CliMcpBackend`), comme pour `BoardBackend` du TUI : il ouvre la base et la configuration, puis appelle le cœur.
- Chaque appel d'outil ouvre sa propre connexion SQLite. Aucun état n'est gardé entre deux appels.
- Seuls `meute/mcp/backend.py` et `meute/mcp/server.py` sont asynchrones, parce que le SDK l'impose. Le backend reste synchrone.

### Identité de l'appelant

- Les écritures sont faites par `Actor(author=CLAUDE, channel=MCP, session_id=…)`.
- La session vient de `MEUTE_SESSION`, retenue seulement si `parse_session_id` l'accepte sous sa forme exacte (même règle que l'adoption d'un orphelin).
- Sans `MEUTE_SESSION`, ou si elle est invalide, les lectures et les écritures marchent. L'historique ne porte alors aucune session, et `task_link_session` répond une erreur.

### Outils

Les réponses sont en JSON et ne contiennent que ce qui est demandé.

| Outil | Entrée | Réponse |
|---|---|---|
| `task_list` | `project?` (nom), `status?`, `due?` (`overdue`, `today`, `week`), `include_done=false` | `[{id, title, status, priority, due, project}]` |
| `task_read` | `id` | la tâche complète : titre, description, statut, `blocked_reason`, priorité, échéance, projet, `version`, dates, et ses notes (texte, auteur, canal, date) |
| `task_create` | `title`, `description?`, `priority?`, `due?` (date ISO ou instant ISO avec fuseau), `project?` | `{id, version}`. Sans `project`, c'est celui de la session appelante (`session_project`), à défaut aucun |
| `task_update` | `id`, `expected_version`, et facultativement `title`, `description`, `priority`, `due` (`null` efface), `project` (`null` efface) ; pas le statut | `{version}` |
| `task_set_status` | `id`, `status` (`todo`, `in_progress`, `blocked`, `review`, `done`), `reason` (obligatoire pour `blocked`, interdit sinon), `expected_version` | `{version}` |
| `task_note_add` | `id`, `body` (non vide) | `{note_id}` |
| `task_link_session` | `id` | `{session_id, task_id}` : lie la session appelante à la tâche (`sessions.task_id`) |

Les noms de statut et de priorité sont ceux de la CLI (`meute task list --status`). Le filtre d'échéance est nouveau :
- `overdue` : échéance passée ;
- `today` : échéance d'aujourd'hui, en heure locale ;
- `week` : échéance dans les 7 jours à venir, sans compter les tâches en retard.

Leur lecture et leurs messages d'erreur vivent dans le cœur, et la CLI réutilise la lecture du statut et de la priorité.

### Erreurs

- **`MeuteError` :** elle devient une erreur d'outil (`isError`) qui porte son message.
- **Conflit de version (`VersionConflict`) :** le message donne la version actuelle, pour que Claude relise la tâche et réessaie.
- **Base indisponible :** l'erreur est `meute database unavailable: <raison>`. Le serveur ne s'arrête pas.
- **Toute autre exception :** elle est écrite dans `~/.local/state/meute/mcp.log` (même rotation que `ingest.log`) et renvoyée comme `internal error`, sans trace.
- **La sortie standard est réservée au protocole :** aucun `print`, et aucun avertissement de Python ou d'une bibliothèque ne doit y arriver. Un test de bout en bout le vérifie.

## Brancher les sessions Claude

### `--mcp-config`

- Chaque session Claude lancée par meute reçoit `--mcp-config <dossier de la session>/mcp.json` : c'est le cas pour `c`, `n`, `N`, `L` et la reprise par `r`.
- Le fichier (0600, dans le dossier 0700 qui contient `settings.json`) déclare un serveur `meute`, de type stdio. Sa commande est celle de meute (la même que celle des hooks), suivie de `mcp`, avec `MEUTE_SESSION=<id>` dans son environnement.
- Pas de `--strict-mcp-config` : les serveurs MCP de l'utilisateur restent chargés.

### Outils autorisés d'office

Le `settings.json` de la session gagne `permissions.allow` avec les 7 outils `mcp__meute__task_*`. Sans cela, en mode `manual`, chaque lecture de tâche demanderait une autorisation. Ces outils n'écrivent que dans la base de meute, et aucun ne supprime. Le spike S11 vérifie que la règle s'ajoute aux réglages de l'utilisateur au lieu de les remplacer.

### Contexte composé

`compose_context(global_instructions, project, task_id) -> str | None` est une fonction pure du cœur.

- Si les trois niveaux sont vides (pas de consignes globales, pas de consignes du projet, pas de tâche liée), elle renvoie `None`, et l'option n'est pas passée.
- Sinon le texte contient, dans cet ordre et séparé par des lignes vides :
  1. la règle de résolution du § 8, mot pour mot : « The repository's `CLAUDE.md` files are authoritative on code conventions. The task is authoritative on the goal. If they contradict each other, point it out to the user instead of choosing. » ;
  2. `Global instructions:` puis les consignes de la configuration, si elles existent ;
  3. `Project instructions (<nom du projet>):` puis les consignes du projet de la session, si elles existent ;
  4. pour une session liée à une tâche, mot pour mot : « You are working on task #N. Read it with the `task_read` tool and report your progress with `task_note_add`. »
- Le projet de la session est celui de `session_project` : son `project_id`, à défaut le projet qui porte le nom de son dépôt.
- Le texte part par `--append-system-prompt`. Si Claude Code accepte une variante qui lit un fichier, le texte va dans un fichier 0600 du dossier de la session, ce qui évite un argument long et visible dans `ps`. Le spike S11 tranche.
- À la reprise (`r`), le contexte est recalculé avec les consignes et le lien du moment. `task_link_session`, appelé pendant une session, ne change pas son contexte : seulement celui de sa prochaine reprise.

### Écrire les consignes

- **Consignes globales :** une nouvelle clé `[claude] instructions`, une chaîne TOML (multiligne permise), vide par défaut. Elle est ajoutée à la configuration commentée (`DEFAULT_CONFIG`) et validée par `config_validate`. `meute config set claude.instructions "…"` fonctionne.
- **Consignes d'un projet :** `meute project edit <nom> --instructions "…"` ou `--instructions-file <fichier>` (texte UTF-8). Une chaîne vide les efface. `meute project show <nom>` les affiche, en passant par `printable`.

### `L`, et `N` avec une tâche

- Le lancement attend toujours le `SessionStart` (10 s au plus) et colle toujours par un fichier privé et un tampon tmux, sans envoyer.
- Ce qui est collé devient « Work on task #N. ».
- Si Claude n'est pas prêt à temps, le tableau affiche toujours « prompt not pasted ».

## Spike S11, au début du plan

Le spike lance le vrai `claude`, avec l'accord explicite de l'auteur. Il tourne sur un serveur tmux jetable, avec un dossier jetable et le vrai `HOME` pour l'authentification, et ne modifie jamais `~/.claude/settings.json` ni `~/.claude.json`. Il doit établir :

1. que `--mcp-config` avec le serveur `meute` fonctionne : les outils sont listés et appelés, et `MEUTE_SESSION` arrive dans l'environnement du serveur ;
2. si `permissions.allow` dans `--settings` supprime la demande d'autorisation en mode `manual`, sans retirer les réglages de l'utilisateur ;
3. si `--append-system-prompt` est bien pris en compte (on demande à Claude ses consignes), s'il existe une variante fichier, et quelle taille l'argument supporte ;
4. combien de temps prend le démarrage à froid de `meute mcp` (SDK compris), et si Claude l'attend avant le premier message.

Le compte rendu fixe la forme exacte des options pour la suite du plan.

## Architecture

| Module | Rôle |
|---|---|
| `core/context.py` | `compose_context`, le texte de la règle, la ligne de la tâche, `work_on_task_text(task_id)` |
| `core/mcp_data.py` | une tâche et ses notes en JSON ; la lecture des entrées (statut, priorité, échéance, filtre d'échéance), partagée avec la CLI |
| `core/config_validate.py` | `ClaudeConfig.instructions` |
| `core/db/projects.py` | `set_project_instructions` |
| `core/db/sessions.py` | `link_session_task` |
| `mcp/backend.py` | le protocole `McpBackend` |
| `mcp/server.py` | `build_server(backend) -> FastMCP`, et la traduction des erreurs |
| `cli/mcp_backend.py` | `CliMcpBackend` |
| `cli/mcp_command.py` | la commande `meute mcp`, le journal `mcp.log` |
| `cli/project_commands.py` | `project edit --instructions / --instructions-file`, `project show` |
| `claude/mcp_config.py` | le document `mcp.json` et son écriture |
| `claude/settings.py` | `permissions.allow` |
| `claude/launch.py` | `claude_argv` gagne `mcp_config` et le contexte (option ou fichier, selon S11) |
| `cli/session_launch_claude.py`, `cli/session_resume.py`, `cli/task_launch.py` | branchement ; `L` et `N` collent `work_on_task_text` |

La dépendance est ajoutée par `uv add mcp`, et `uv.lock` est commité. Le guide (`docs/dev/developpement-assiste-par-ia.md`, § 7) et la vérification des licences sont mis à jour.

## Tests

- **Cœur :**
  - instantanés `syrupy` de `compose_context` : aucun niveau, chaque niveau seul, les trois ensemble, avec une tâche ;
  - propriétés `hypothesis` sur la lecture des entrées ;
  - JSON d'une tâche et de ses notes.
- **Serveur :** client MCP en mémoire du SDK, contre un faux backend :
  - instantané de la liste des outils et de leurs schémas ;
  - appel de chaque outil ;
  - `isError` pour une `MeuteError`, `internal error` pour une autre exception ;
  - conflit de version.
- **Backend, sur une base jetable :**
  - chaque outil ;
  - historique `claude/mcp` avec l'identifiant de session ;
  - `MEUTE_SESSION` invalide ignoré ;
  - `task_link_session` avec et sans session ;
  - projet par défaut de `task_create`.
- **De bout en bout :** `meute mcp` en sous-processus, piloté par le client stdio du SDK (`initialize`, `tools/list`, `task_read`). Cela prouve que la sortie standard ne porte que le protocole.
- **Lancement :**
  - le faux `claude` enregistre `--mcp-config` et le contexte ;
  - contenu de `mcp.json` et de `permissions.allow` ;
  - la reprise recalcule le contexte ;
  - `L` colle « Work on task #N. ».
- **Consignes :**
  - `config set claude.instructions` ;
  - `project edit --instructions` et `--instructions-file` ;
  - `project show`.

**Exceptions prévues aux tests existants (n° 24 et suivantes)** : les tests qui fixent l'argv exact de Claude, le document `settings.json`, le texte collé par `L` et `N`, et la configuration par défaut. Le plan en donne la liste exacte.

## Points d'attention pour la relecture

1. **Sortie standard de `meute mcp` :** un seul octet hors protocole casse la session MCP. Cela vaut pour un avertissement de dépréciation, un message de migration de la base ou un `print` oublié.
2. **Texte des tâches lu par Claude :** c'est une donnée. Le risque d'injection dans le prompt est accepté : l'auteur des tâches est l'utilisateur, et aucun outil ne supprime ni n'arrête rien.
3. **`MEUTE_SESSION` :** il relève de la confiance locale. Un identifiant invalide n'est jamais écrit.
4. **Taille du contexte :** des consignes longues dans l'argv, et l'option fichier si S11 la confirme.
5. **Écritures concurrentes avec le tableau :** la version les règle, et Claude reçoit la version actuelle.
6. **SDK `mcp` :** des dépendances nouvelles (pydantic, anyio, starlette…), à surveiller avec pip-audit et la vérification des licences.

## Écarts constatés à la réalisation

Ce que le plan 5 a fait autrement que ce texte, ou précisé en le réalisant (les numéros sont ceux du registre de décisions du plan).

- **SDK (R6)** : « `FastMCP` » désigne la classe serveur de haut niveau du SDK installé. En `mcp` 2.x elle s'appelle `MCPServer` (`mcp.server.mcpserver`) ; `from mcp.server.fastmcp import FastMCP` échoue. Les outils sont des fonctions synchrones : `meute.mcp` ne contient ni `await` ni fil d'exécution, au-delà du `run()` du SDK. La phrase « seuls `backend.py` et `server.py` sont asynchrones » est donc sans objet.
- **Contexte en argument jusqu'à 8 000 octets, fichier au-delà (R5, R10)** : S11 a établi que `--append-system-prompt-file` fonctionne, mais il n'est pas documenté. Le contexte part donc en argument (`--append-system-prompt`, option documentée) tant qu'il tient dans 8 000 octets UTF-8, et dans un fichier 0600 `context.md` du dossier de la session (`--append-system-prompt-file`) au-delà. Raison : tmux refuse une commande d'environ 16 Ko. Coût si Claude retire l'option : les contextes longs font échouer le lancement, bruyamment.
- **`mcp.json` garde `env: {MEUTE_SESSION}` (R4)** : S11 a vu que l'environnement est hérité, mais le fichier le déclare quand même, pour le cas où Claude filtrerait un jour l'environnement des serveurs.
- **Entiers souples (R7)** : les entiers des outils acceptent la conversion du SDK (`"3"`, `true`, `1.0` deviennent des entiers). Refuser demanderait `pydantic.Field(strict=True)`, hors de la frontière d'imports de `meute.mcp` ; la valeur reste un entier validé.
- **Pas de `config.toml` (R9)** : `meute mcp` ne charge plus la configuration, et `CliMcpBackend` ne la prend pas. Une faute de frappe dans un réglage sans rapport arrêtait tous les outils. À rouvrir si un outil a besoin d'un réglage.
- **Dépendances datées (R8)** : le SDK `mcp` a ajouté des paquets neufs. Sur décision de l'auteur (2026-10-23), `pyproject.toml` fixe `[tool.uv] exclude-newer = "2026-10-15T00:00:00Z"`, avec `exclude-newer-package` pour six paquets déjà verrouillés (`tomlkit`, `hypothesis`, `ruff`, `certifi`, `platformdirs`, `pluggy`), pour que la date globale ne rétrograde pas `certifi` (version vulnérable GHSA-6q48-6c7w-9gw2) ni `ruff`.
- **Contexte sans session enregistrée (R1)** : au lancement, la session n'existe pas encore ; le contexte se calcule par `session_context(ctx, project_id=…, repo_id=…, task_id=…)`, partagé par le lancement et la reprise.
- **Journal injecté (R2)** : `build_server(backend, *, on_unexpected)` reçoit le journal des erreurs inattendues ; il ne lève jamais.
- **`task_prompt` supprimé (R11, exceptions n° 24 à 26)** : le collage complet disparaît, `core/task_prompt.py` et son test aussi, et le fichier quitte la sélection mutmut. Deux tests existants attendent désormais `work_on_task_text(task.id)`, et le test de l'argv exact gagne `--mcp-config`.
- **Limites relevées** : « no such table » se lit « database unavailable » ; les fichiers de session (`mcp.json`, `context.md`) suivent un lien symbolique planté dans le dossier de la session (hérité de `write_settings`) ; un titre de session très long peut encore dépasser la limite de tmux.
- **`python -P -m meute` (revue finale)** : Claude lance `meute mcp` et les hooks dans le dossier de la session ; `-P` retire ce dossier de `sys.path`, pour qu'un paquet `anyio/` ou `pydantic/` du dépôt ne remplace pas ceux de meute.
- **Instructions globales relues à chaque contexte (revue finale)** : `session_context` relit `config.toml`, car le tableau de bord garde le même `CliContext` toute sa vie ; un fichier devenu invalide donne une `ConfigError`, affichée comme une erreur de lancement.
