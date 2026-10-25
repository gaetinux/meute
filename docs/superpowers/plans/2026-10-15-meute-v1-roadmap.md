# Feuille de route de la V1 de meute

- Spécification : `docs/superpowers/specs/2026-10-15-meute-design.md`
- Spikes : `docs/superpowers/spikes/2026-10-15-spikes-s1-s5.md`, `docs/superpowers/spikes/2026-10-16-spike-s6-demarrage-python.md`

## Migration vers Python (2026-10-16)

meute passe de Rust à Python, pour que l'auteur, qui maîtrise Python et non Rust, puisse comprendre et relire le code que Claude écrit. Conception : `docs/superpowers/specs/2026-10-16-migration-python-design.md`. Le code Rust est conservé sous deux tags, qui servent de référence de comportement : `rust-plan-1` (`main` à la fin du plan 1 Rust) et `rust-plan-2-wip` (plan 2 Rust largement implémenté, non mergé). Le découpage en six plans ne change pas.

La V1 est découpée en six plans ; le plan 4 est lui-même découpé en 4, 4b et 4c, et le plan 6 en 6a, 6b et 6c (décision de l'auteur, 2026-10-23). Chacun produit un logiciel utilisable et testé, et donne lieu à une PR. Le plan N+1 n'est rédigé qu'une fois le plan N mergé, pour tenir compte de ce que son implémentation a appris.

| # | Plan | Livrable | Sections de la spécification |
|---|---|---|---|
| 1 | **Socle et tâches** — *fait en Python (PR #7)* : `docs/superpowers/plans/2026-10-16-meute-plan-1-python-socle-taches.md` | Workspace, CI, configuration, base SQLite et migrations, gestion des tâches et des projets en CLI | § 4.2, 4.3, 9.1–9.3, 13, 16, 17 |
| 2 | tmux, dépôts et sessions Bash — *fait en Python* : `docs/superpowers/plans/2026-10-18-meute-plan-2-python-tmux-sessions-bash.md` (référence : plan Rust sous `rust-plan-2-wip`) | `meute` démarre son serveur tmux, sa disposition (zone principale et tableau de bord minimal), découvre les dépôts et lance, échange, réconcilie et arrête des sessions Bash | § 5, 6.1, 6.3–6.5, 10 (découverte) |
| 3 | Adaptateur Claude — *fait en Python* : `docs/superpowers/plans/2026-10-18-meute-plan-3-python-adaptateur-claude.md` | Lancement de Claude (§ 6.2), `meute ingest hook` / `statusline`, rendu de la statusline, `claude agents --json` | § 5.5, 6.2, 7 |
| 4 | Vue Sessions et interface transparente — *fait en Python* : `docs/superpowers/plans/2026-10-18-meute-plan-4-python-vue-sessions.md` | Vue Sessions (projets, « à traiter », quotas et projection, détails), mode étroit, interface transparente (souris, ligne d'état meute, détacher) | § 4.5, 5.2, 5.6, 7.4, 10 |
| 4b | Vue Tâches — *fait en Python* : `docs/superpowers/plans/2026-10-20-meute-plan-4b-python-vue-taches.md` | Onglet Tâches (filtres, regroupements, détail et ses actions, « launch Claude on this task »), saisie rapide globale `M-t` avec aperçu | § 9.5, 9.6 |
| 4c | Lancement depuis le tableau — *fait en Python* : `docs/superpowers/plans/2026-10-21-meute-plan-4c-python-lancement.md` | Formulaire `N`, « dernier type utilisé » de `n`, actions sur les panneaux orphelins (adopter, fermer), reprise d'une session Claude terminée (`claude --resume`, avancée du plan 6 par l'auteur le 2026-10-19) | § 5.4, 6.4, 6.5 |
| 5 | MCP — *fait en Python* : `docs/superpowers/plans/2026-10-22-meute-plan-5-python-mcp.md` | `meute mcp` et les sept outils de tâches, `--mcp-config` et outils autorisés d'office sur chaque session Claude, contexte composé (§ 8) avec consignes globales et de projet (`meute project edit` / `show`, `[claude] instructions`), `L` et `N` collent « Work on task #N. » ; spike S11 | § 8, 12 |
| 6a | Git et worktrees — *fait en Python* : `docs/superpowers/plans/2026-10-23-meute-plan-6a-python-git-worktrees.md` (conception : `docs/superpowers/specs/2026-10-23-meute-git-worktrees-design.md`) | État Git des sessions sur les cartes (relevé en fond), champ `Worktree` de `N` et recommandation de worktree, `meute session new --worktree`, touche `W` et `meute worktree list` / `remove` (branche toujours gardée) | § 3.1, 6.4, 10, 11 |
| 6b | Reprise et états sauvegardés — *fait en Python* : `docs/superpowers/plans/2026-10-23-meute-plan-6b-python-saved-states.md` (conception : `docs/superpowers/specs/2026-10-23-meute-saved-states-design.md`) | `[ui] recent_days`, `meute session recent` / `resume`, table `saved_states` (migration 005), touches `S` et `O`, état automatique `last` tenu par le tableau, `meute state save` / `list` / `open` / `rm` | § 6.5, 6.6, 13 |
| 6c | Préparation de la V1 | Projets créés automatiquement, `meute doctor` (dont la version de git), purge de `session_events`, README | § 10, 13 |

Règles communes à tous les plans :

- Chaque plan respecte `docs/dev/developpement-assiste-par-ia.md` : TDD systématique, lints, hooks, `hypothesis` et `syrupy` là où ils s'appliquent, vérification complète (`bash scripts/verify.sh`).
- Chaque tâche de code se termine par `/simplify`, et par `/security-review` quand elle touche aux sous-processus, aux fichiers, à SQL ou à des entrées externes.
- Chaque plan se termine par une passe de `mutmut`, dont le rapport est joint à sa PR, puis par `/simplify` et `/security-review` sur toute la branche.
- Chaque plan est exécuté par des sous-agents (superpowers:subagent-driven-development) : un agent neuf par task, relu par un autre agent avant de passer à la suivante.

Ce que ce découpage implique :

- **Après le plan 1**, meute est déjà un gestionnaire de tâches en CLI, et le cœur métier (`meute.core`) existe.
- **Après le plan 3**, l'auteur peut remplacer son mod pour la supervision, avec un tableau de bord minimal.
- **Après le plan 4**, le critère de réussite n° 1 de la spécification (§ 1.2) est atteignable.

## Reports issus du plan 1

Décisions prises à la revue finale du plan 1, à traiter au début des plans suivants :

- **Plan 2, première tâche — refonte de l'API de `meute-core`** — *intégrés au plan 1 Python* :
  - un `StatusKind` sans données à la place de `TaskFilter.status: Option<&'static str>` ;
  - un filtre de statut `done` qui implique les tâches terminées, dans le cœur et non dans la CLI ;
  - une forme serde de `Due` alignée sur le JSON de `Task` (`{kind, value}`) ;
  - la suppression de la validation de statut par un `Blocked("-")` jetable dans la CLI.
- **Avant les plans 2 à 6 — tests** : regrouper les fonctions utilitaires de test de `meute-core` dans `tests/common/` — *intégré au plan 1 Python* (fixtures dans `tests/conftest.py`, fonctions dans `tests/support.py`).

## Reports issus du plan 2

Ce que le plan 2 laisse volontairement de côté, à traiter dans les plans indiqués :

- **Plan 4c — tableau de bord** : les actions sur les panneaux orphelins (adopter, fermer), qui sont seulement affichés ; le formulaire `N`, la recommandation de worktree et le « dernier type utilisé » de `n` (qui lance toujours Bash) ; la vue Sessions alimentée par tmux seul quand la base est indisponible ou verrouillée (§ 16 ; le tableau de bord affiche l'erreur dans son pied de page).
- **Défauts connus du tableau de bord** (`M-o` en mode étroit et l'arrêt qui figeait le tableau sont corrigés par le plan 4) :
  - le hook `client-resized` relance `meute layout sync` à chaque redimensionnement, sans regroupement ;
  - après un changement de `[keys]`, les anciens raccourcis restent liés jusqu'au redémarrage du serveur.
- **Plan 6 — projets automatiques et worktrees** : la création automatique de projets et les worktrees ; les worktrees découverts ne sont pas enregistrés en base.

## Reports issus du plan 3

Ce que le plan 3 laisse volontairement de côté, à traiter dans les plans indiqués :

- **Plan 4c — tableau de bord** : formulaire `N`, « dernier type utilisé » de `n` (la touche `c` lance Claude, `n` lance toujours Bash). La vue Sessions, « needs attention », `M-n` / `M-N`, le compteur de la barre d'état, les quotas et la projection et le mode de permission dans la ligne de session sont faits au plan 4.
- **Plan 5 — MCP** : `meute mcp`, `--mcp-config`, `--append-system-prompt` et le contexte composé du § 8.
- **Plan 6 — finitions** : reprise `--resume`, états sauvegardés, worktrees, `meute doctor` ; purge de `session_events`, qui grandit sans limite et garde des extraits de commandes de 80 caractères.

Limites connues, relevées pendant le plan 3 :

- **Hook `Notification`** : Claude Code 2.1.302 ne l'a jamais émis pendant la capture S7 ; les tests utilisent un exemple fait à la main. À recapturer quand une version l'émet.
- **Chemins chauds** : `ingest hook` 41,0 ms en médiane (p95 48,7 ms) et `ingest statusline` 47,1 ms sans base, pour un budget de 50 ms ; peu de marge et aucun test de durée ne les garde.
- **`ingest`** : la rotation de `ingest.log` n'est pas atomique entre processus ; un hook contenant des substituts isolés est abandonné (journalisé).
- **États** : un `SubagentStop` tardif ignoré met quand même à jour `last_activity_at` ; un sous-agent d'arrière-plan qui finit pendant que l'utilisateur lit n'apparaît pas dans l'état ; `/clear` et `/resume` sont traités d'après la documentation de Claude Code, sans capture réelle (`/clear` vérifié avec le vrai Claude par l'auteur, 2026-10-18 ; `/resume` reste à vérifier) ; `meute session stop` relit sans `claude agents` et peut écrire `stuck?` pour une session silencieuse, que le tableau de bord corrige au relevé suivant ; après une permission refusée, la session reste `permission` jusqu'au prompt suivant.
- **Statusline** : les descendants `setsid` de la commande `[statusline] chain` lui survivent.
- **`--settings`** : un `settings.json` ou un dossier de session remplacé par un lien symbolique est suivi ; les dossiers parents du dossier 0700 suivent l'umask ; le dossier de réglages reste en place si le lancement échoue.
- **`claude agents --json`** : la liste des sessions extérieures reste vide pendant qu'une nouvelle tentative attend après un échec ; la purge des relevés au démarrage du tableau de bord n'est pas protégée contre `sqlite3.Error`.
- **Verrou de migration** : `flock` sans délai maximal.
- Les défauts connus du tableau de bord listés dans « Reports issus du plan 2 » restent ouverts.

## Reports issus du plan 4

Ce que le plan 4 laisse volontairement de côté, à traiter dans les plans indiqués :

- **Plan 4b — vue Tâches** (§ 9.5, 9.6), avec les actions du détail.
- **Plan 4c — lancement depuis le tableau** : formulaire `N`, « dernier type utilisé » de `n`, actions sur les panneaux orphelins (adopter, fermer), reprise d'une session Claude terminée (§ 6.5). En attendant, `Entrée` sur une session terminée sans panneau l'indique dans le pied du tableau (PR #10).
- **Plan 5 — MCP** et contexte composé.
- **Plan 6 — finitions** : état Git des sessions, worktrees, reprise et « recent sessions to resume », états sauvegardés, projets créés automatiquement (le regroupement se fait par projet, à défaut par dépôt, à défaut `Other`).

Limites connues, relevées pendant le plan 4 :

- **Barre d'état** : le texte publié est mis en cache par le tableau de bord et n'est pas republié si le serveur tmux redémarre sans lui.
- **Essai réel** : la souris, `M-n` / `M-N`, détacher puis rattacher et le mode étroit n'ont été essayés qu'avec un faux `claude` et `send-keys` ; l'essai avec le vrai Claude dans un vrai terminal reste à faire par l'auteur.

## Reports issus du plan 4b

Ce que le plan 4b laisse volontairement de côté, à traiter dans les plans indiqués. Le plan 4b livre la passe visuelle du tableau, l'onglet Tâches avec toutes les actions du détail, « launch Claude on this task » (collage par fichier, sans envoi) et `M-t` (§ 9.5, 9.6).

- **Plan 4c — lancement depuis le tableau** : le formulaire `N`, le « dernier type utilisé » de `n`, les actions sur les panneaux orphelins (adopter, fermer) et `claude --resume` d'une session terminée, comme prévu.
- **Plan 6 — finitions** : l'état Git des sessions (la fiche n'affiche que la branche de la statusline) et les projets créés automatiquement (le projet d'une session est son `project_id`, à défaut le projet qui porte le nom de son dépôt, à défaut aucun).
- **Limites connues** : `M-t` demande tmux 3.3 ou plus (`display-popup -B`) ; sur tmux 3.2, la touche affiche une erreur de tmux et le reste de la configuration n'est pas affecté. `D` refuse une description de plusieurs lignes (à éditer par `meute task edit`). Le dernier essai, avec le vrai Claude dans un vrai terminal, reste à faire par l'auteur (liste dans le rapport de mutation et dans la PR).

## Reports issus du plan 4c

Ce que le plan 4c laisse volontairement de côté, à traiter dans les plans indiqués. Le plan 4c livre `n` (dernier type utilisé du dépôt), le formulaire `N` sans worktree, la reprise `r` (`claude --resume`, spike S10) et les actions sur les panneaux orphelins (afficher, adopter, fermer). Rapport de mutation : `docs/dev/mutants/2026-plan-4c-python.md`.

- **Plan 6 — finitions** : le champ worktree de `N` (aucun / nouveau / existant) et la recommandation de worktree (l'avertissement `⚠ another live session works in this folder` la prépare) ; la liste « recent sessions to resume » ; les états sauvegardés.
- **Plus tard (plan 6 ou petit plan 4d)** : la vue Sessions alimentée par tmux seul quand la base est indisponible (§ 16) ; la largeur en cellules ; `paste-buffer -r` ; la suppression de `quota_lines` / `details_lines`, qui ne servent plus qu'aux tests.

Limites connues, relevées pendant le plan 4c :

- **Reprise** : le `respawn-pane` est suivi de `reopen_session` ; un `SessionStart` arrivé entre les deux est ignoré, et la session reprise peut rester `unknown` jusqu'au hook suivant (masqué en pratique par le démarrage de Claude). Si `set_pane_option` échoue après le lancement (reprise comme lancement), le panneau reste sans étiquette ; la lacune existait déjà dans `spawn_and_record`.
- **Adoption** : un orphelin au dossier vide est adopté avec `Path("")` ; `x` pendant une adoption puis `y` après sa fin ferme le panneau de la session adoptée, sans passer par `stop_session` (l'état est corrigé à la relecture suivante) ; le test « le dépôt contient le dossier » est lexical (`..` n'est pas résolu).
- **Formulaire `N`** : le lancement se fait sur le fil de l'interface (comme `n`), contrairement à la reprise, à l'adoption et à la fermeture, qui passent par `BoardWorkers` ; `shares_folder` résout les chemins (`Path.resolve()`) à chaque rendu, ce qui bloque brièvement sur un système de fichiers lent ; la saisie de tâche redessine le tableau à chaque touche (avant : seulement à `Échap`).
- **Base** : `last_agent_by_repo` (sous-requête corrélée) tourne à chaque relecture de 2 s ; vérifier l'index sur `sessions(repo_id)` si le nombre de sessions grandit.
- **Dette de code** : `CliBoardBackend._perform` porte un `noqa PLR0912` et grossit ; `board_view.__all__` ne liste que les actions réexportées (préférer `X as X`) ; `tests/test_tui_launch_form.py` fait 319 lignes (limite visée : 300) ; deux tests de `test_resume_target.py` sont quasi vides ; la docstring de `tests/test_tmux_respawn.py` parle encore de `respawn-pane -k`.
- **Tests sensibles à la charge** : `test_stopping_a_claude_session_takes_two_interrupts_and_is_quick` (2,06 s pour un plafond de 2,0 s sous charge) et, une fois, `test_survivors_finds_the_processes_a_test_left` ; les deux passent seuls. Les tests de reprise attendaient la mort du panneau sans borne : corrigé par `f91a152` (attente bornée).
- **Essai réel** : la reprise, le formulaire et l'adoption n'ont été essayés qu'avec le faux `claude` ; l'essai avec le vrai Claude dans un vrai terminal reste à faire par l'auteur (liste dans le rapport de mutation et dans la PR). Le spike S10 a, lui, tourné avec le vrai Claude.

## Reports issus du plan 5

Ce que le plan 5 laisse volontairement de côté. Le plan 5 livre `meute mcp` (SDK `mcp` 2.x), `--mcp-config`, `permissions.allow`, le contexte composé (argument jusqu'à 8 000 octets, fichier privé au-delà), les consignes globales et de projet, et le collage de « Work on task #N. ». Rapport de mutation et essai scripté : `docs/dev/mutants/2026-plan-5-python.md`. Écarts à la conception : `docs/superpowers/specs/2026-10-22-meute-mcp-design.md` (« Écarts constatés à la réalisation »).

- **Plan 6 — finitions** : inchangé (worktrees, états sauvegardés, projets créés automatiquement, `meute doctor`).
- **Hors périmètre, restent ouverts** : les outils de suppression et d'arrêt de session, les confirmations en attente (§ 12), `meute mcp` pour des sessions lancées hors de meute.

Limites connues, relevées pendant le plan 5 :

- **Option non documentée** : `--append-system-prompt-file`, utilisée au-delà de 8 000 octets, n'est pas dans `claude --help` ; si Claude Code la retire, les contextes longs font échouer le lancement (bruyamment).
- **Fichiers de session** : `mcp.json` et `context.md` suivent un lien symbolique planté dans le dossier de la session (hérité de `write_settings`) ; `write_session_file` vit dans `settings.py` ; `session_context` est lu après l'écriture des fichiers.
- **Titre de session** : un titre très long (`#N` plus un titre de tâche) peut encore dépasser la limite de commande de tmux.
- **Outils** : les entiers acceptent la conversion souple du SDK (`"3"`, `1.0`) ; « no such table » se lit « database unavailable » ; `parse_priority` n'est qu'une enveloppe d'un import renommé ; un instant plus tôt aujourd'hui est à la fois `overdue` et `today` (filtres non exclusifs), `week` = [maintenant, +7 j).
- **Dépendances** : `[tool.uv] exclude-newer = "2026-10-15T00:00:00Z"` plus six exceptions par paquet (décision de l'auteur, 2026-10-23) ; à relever à la prochaine mise à jour. La sentinelle de champ omis de `task_update` s'appuie sur un comportement non documenté de pydantic (gardée par un instantané et un test) ; `MCPServer` appelle `logging.basicConfig` (stderr), à surveiller avec `mcp.log`.
- **Tests** : `test_launch_context.py` (282 lignes) répète un scénario long vers court et une fermeture `ended()` ; le test du marqueur de fin dans le titre (`test_task_launch.py`) passe désormais à vide, le titre n'étant plus collé (laissé tel quel, règle des tests) ; la docstring de `tests/test_task_launch_form.py` parle encore du « task text pasted » ; pas de test d'un `--instructions-file` non UTF-8.
- **Essai réel** : le vrai Claude n'a tourné que pour le spike S11 ; l'essai de la session complète (contexte suivi, outils appelés, contexte long) reste à faire par l'auteur (liste dans le rapport de mutation et dans la PR).

## Reports issus du plan 6a

Ce que le plan 6a laisse volontairement de côté. Le plan 6a livre l'état Git des sessions (ligne 3 des cartes, sessions Bash comprises), le champ `Worktree` de `N` (aucun / nouveau / existant) et sa recommandation, `meute session new --worktree`, la touche `W` et `meute worktree list` / `remove`. Rapport de mutation et essai scripté : `docs/dev/mutants/2026-plan-6a-python.md`. Écarts à la conception : `docs/superpowers/specs/2026-10-23-meute-git-worktrees-design.md` (« Écarts constatés à la réalisation »).

- **Plan 6b — reprise et états sauvegardés** : « recent sessions to resume », `meute state` (le worktree d'une session y figure par son dossier).
- **Plan 6c — préparation de la V1** : projets créés automatiquement, `meute doctor` (dont la version de git : git 2.36 au moins, pour `git worktree list --porcelain -z` ; `--no-optional-locks` demande 2.15), purge de `session_events`, README.
- **Hors périmètre, restent ouverts** : l'état Git en base, une mention « worktree » sur les cartes, la suppression de branches, les rappels « worktree to delete » après un merge (V1.1, forges).

Limites connues, relevées pendant le plan 6a :

- **Relevé** : le relevé avance à chaque battement du tableau (0,5 s) ; la sortie de git y est vidée d'environ un tampon de tube par battement, et un `git status` de plus de quelques centaines de Ko (dépôt énorme plein de fichiers non suivis) ne finit jamais avant le délai de 5 s : ce dossier n'a jamais de ligne Git, sans message. Tuer une commande (`kill_read`) et tester qu'un dossier existe peuvent bloquer le fil de l'interface sur un montage réseau figé. Les sessions terminées sont relevées même quand `e` ne les montre pas (40 dossiers au plus par tour).
- **Pilote de filtre ajouté pendant un tour (R17)** : dans le relevé, la recherche des pilotes et `git status` sont deux commandes séparées d'un battement au moins ; un pilote écrit dans `.git/config` entre les deux, puis enlevé, n'est pas neutralisé (il faut pouvoir écrire dans `.git/config`, ce que peut faire Claude, et gagner cette course ; l'essai scripté l'a vu une fois). Suite prévue : un seul processus d'aide par dossier, qui enchaîne recherche, `status` et `diff`.
- **Formulaire `N`** : la liste des worktrees est lue sur le fil de l'interface (2 s au plus par changement de dépôt) ; la recommandation est tronquée sous 74 colonnes environ ; `Branch`, prérempli depuis le titre, peut proposer un nom que `branch_error` refuse (`a..b`), refusé au lancement ; la recommandation s'affiche aussi avec `new` quand le chemin calculé est déjà occupé ; `Branch` est vide quand le formulaire s'ouvre sur un dossier occupé (R18).
- **Lancement dans un nouveau worktree** : entre la vérification du chemin et `worktree add`, un dossier créé par un tiers (il faut pouvoir écrire à côté du dépôt) est signalé par git, pas par meute ; un hook `post-checkout` qui laisse un processus d'arrière-plan fait dépasser le délai de 30 s.
- **`W`** : la nouvelle vérification avant l'enlèvement utilise les dossiers des sessions vivantes de la dernière relecture (2 s au plus de retard) ; `W` sur une ligne de dépôt n'affiche rien. Les messages d'erreur de `meute worktree remove` montrent l'argument tel quel (`not a linked worktree: .`) ; un worktree cassé fait échouer la liste de tout son dépôt.
- **Corrigé à la relecture finale (R16)** : le pilote de filtre au nom vide (`[filter ""]`) est neutralisé ; la vérification et l'enlèvement de `W` passent hors du fil de l'interface, le pied disant `checking worktree <chemin>…` puis `removing worktree <chemin>…` ; `read_git` donne un seul délai à la recherche des pilotes et à la commande ; la liste des worktrees est lue avec `-z` ; `printable` remplace aussi U+2028 et U+2029 (`Zl`, `Zp`). Détail : « Écarts constatés à la réalisation » de la conception.
- **Corrigé à la revue de sécurité (R20)** : les lectures ne récupèrent jamais un objet absent d'un clone partiel auprès du dépôt « promisor » (`GIT_NO_LAZY_FETCH=1`, `-c protocol.allow=never`), ce qui aurait exécuté `core.sshCommand` à chaque relevé ou à `W` ; le refus de la vérification de `W` passe par `printable`. Détail : « Écarts constatés à la réalisation » de la conception.
- **Dette de code** : `tests/test_launch_form_worktree.py` fait 317 lignes (limite : 300) ; `Worktree.prunable` est toujours faux (champ prévu par le plan, jamais rempli) ; `WorktreeCheck.commits` mêle lignes de `git log` et identifiants nus ; quelques tests importent des fixtures privées d'autres modules de test.
- **Essai réel** : la ligne Git, le formulaire et `W` n'ont été essayés qu'avec le faux `claude` ; l'essai avec le vrai Claude dans un vrai terminal (confiance du nouveau dossier, worktree créé par Claude lui-même) reste à faire par l'auteur (liste dans le rapport de mutation et dans la PR).

## Reports issus du plan 6b

Ce que le plan 6b laisse volontairement de côté. Le plan 6b livre la durée réglable des sessions récentes (`[ui] recent_days`), `meute session recent` et `resume`, les états sauvegardés (`S`, `O`, `meute state save` / `list` / `open` / `rm`) et l'état automatique `last`. Rapport de mutation et essai scripté : `docs/dev/mutants/2026-plan-6b-python.md`. Écarts à la conception : `docs/superpowers/specs/2026-10-23-meute-saved-states-design.md` (« Écarts constatés à la réalisation »).

- **Plan 6c — préparation de la V1** : inchangé (voir « Reports issus du plan 6a »).
- **Hors périmètre, restent ouverts** : les conversations Claude démarrées hors de meute (`~/.claude/projects/`), un écran dédié aux sessions récentes, le choix du nom d'un état dans le tableau, la reprise de l'historique ou des processus d'un shell.

Limites connues, relevées pendant le plan 6b :

- **`last` ne rétrécit jamais (choix de l'auteur, R11)** : une session arrêtée exprès reste dans `last` jusqu'au démarrage d'une nouvelle session, et rouvrir `last` d'ici là la ramène. `last` n'est réécrit qu'à l'apparition d'une session : la session affichée et l'ordre qu'il garde sont ceux de cette réécriture. `S` sauve la dernière lecture du tableau (2 s au plus de retard).
- **Liste de `O`** : pendant qu'elle est ouverte, le pied montre encore les touches du tableau, qui ne s'appliquent pas (la liste prend toutes les touches) ; elle reste ouverte après `Entrée`, le compte rendu arrivant dans le pied ; si la vérification de `W` revient pendant que la liste est ouverte, la question de l'enlèvement s'affiche sous la liste (sans danger : la liste prend les touches, et la question attend). Avant la première relecture, l'âge des états est calculé sur l'horloge murale.
- **Réouverture** : un état écrit à la main qui contient deux fois le même id Claude ignore le second avec `"<titre>" is still running` au lieu de `already running` ; deux sessions Bash du même dossier dans un même état reviennent toutes deux (instantané pris avant la boucle, R9), ce que ne vérifie aucun test.
- **`ActionNotice(MeuteError)`** : les comptes rendus de `S` et `O` (`state saved: <nom>`, `reopened <n> · skipped <m>`) passent par une exception dérivée de `MeuteError`, attrapée avant elle par le tableau et ses fils ; un futur appelant qui n'attraperait que `MeuteError` afficherait `Error: state saved: …`.
- **Dette de code** : `tui/board.py` fait 299 lignes, `tui/sessions_tab.py` et `cli/board_backend.py` 298, `core/board_view.py` 295 (limite : 300) : la prochaine touche du tableau demande un découpage. Le test du backend compare les ids triés, pas l'ordre du tableau.
- **Essai réel** : `S`, `O` et la réouverture n'ont été essayés qu'avec le faux `claude` ; l'essai avec le vrai Claude dans un vrai terminal (conversation reprise après un redémarrage de la machine) reste à faire par l'auteur (liste dans le rapport de mutation et dans la PR).
