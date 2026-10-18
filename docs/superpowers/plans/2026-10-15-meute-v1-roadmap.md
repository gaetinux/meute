# Feuille de route de la V1 de meute

- Spécification : `docs/superpowers/specs/2026-10-15-meute-design.md`
- Spikes : `docs/superpowers/spikes/2026-10-15-spikes-s1-s5.md`, `docs/superpowers/spikes/2026-10-16-spike-s6-demarrage-python.md`

## Migration vers Python (2026-10-16)

meute passe de Rust à Python, pour que l'auteur, qui maîtrise Python et non Rust, puisse comprendre et relire le code que Claude écrit. Conception : `docs/superpowers/specs/2026-10-16-migration-python-design.md`. Le code Rust est conservé sous deux tags, qui servent de référence de comportement : `rust-plan-1` (`main` à la fin du plan 1 Rust) et `rust-plan-2-wip` (plan 2 Rust largement implémenté, non mergé). Le découpage en six plans ne change pas.

La V1 est découpée en six plans. Chacun produit un logiciel utilisable et testé, et donne lieu à une PR. Le plan N+1 n'est rédigé qu'une fois le plan N mergé, pour tenir compte de ce que son implémentation a appris.

| # | Plan | Livrable | Sections de la spécification |
|---|---|---|---|
| 1 | **Socle et tâches** — *fait en Python (PR #7)* : `docs/superpowers/plans/2026-10-16-meute-plan-1-python-socle-taches.md` | Workspace, CI, configuration, base SQLite et migrations, gestion des tâches et des projets en CLI | § 4.2, 4.3, 9.1–9.3, 13, 16, 17 |
| 2 | tmux, dépôts et sessions Bash — *fait en Python* : `docs/superpowers/plans/2026-10-18-meute-plan-2-python-tmux-sessions-bash.md` (référence : plan Rust sous `rust-plan-2-wip`) | `meute` démarre son serveur tmux, sa disposition (zone principale et tableau de bord minimal), découvre les dépôts et lance, échange, réconcilie et arrête des sessions Bash | § 5, 6.1, 6.3–6.5, 10 (découverte) |
| 3 | Adaptateur Claude — *fait en Python* : `docs/superpowers/plans/2026-10-18-meute-plan-3-python-adaptateur-claude.md` | Lancement de Claude (§ 6.2), `meute ingest hook` / `statusline`, rendu de la statusline, `claude agents --json` | § 5.5, 6.2, 7 |
| 4 | TUI complet | Vue Sessions (projets, « à traiter », quotas et projection, détails), vue Tâches (saisie rapide avec aperçu, regroupements, détail), mode étroit | § 4.5, 5.2, 7.4, 9.5, 10 |
| 5 | MCP | `meute mcp` et les outils de tâches, contexte composé (§ 8) | § 8, 12 |
| 6 | Finitions de la V1 | Worktrees, reprise, états sauvegardés, projets créés automatiquement, `meute doctor`, README | § 6.5, 6.6, 10, 11, 13 |

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

- **Plan 4 — états Claude** : `M-n` / `M-N` et le compteur « needs attention » de la barre d'état (les états Claude existent depuis le plan 3).
- **Plan 4 — TUI complet** : les actions sur les panneaux orphelins (adopter, fermer), qui sont seulement affichés ; le formulaire `N`, la recommandation de worktree et le « dernier type utilisé » de `n` (qui lance toujours Bash) ; la vue Sessions alimentée par tmux seul quand la base est indisponible ou verrouillée (§ 16 ; le tableau de bord affiche l'erreur dans son pied de page).
- **Plan 4 — défauts connus du tableau de bord** :
  - en mode étroit, `M-o` fait sortir le tableau de bord du plein écran jusqu'au prochain rattachement ou redimensionnement : les cibles `{left}` et `{right}` désignent le panneau zoomé, il faudra des cibles par index avec `select-pane -Z` ;
  - les actions du tableau de bord s'exécutent dans la boucle de Textual : arrêter une session Bash inactive (qui ignore `C-c`) fige le tableau pendant les 5 s de délai, à déplacer dans un worker ;
  - le hook `client-resized` relance `meute layout sync` à chaque redimensionnement, sans regroupement ;
  - après un changement de `[keys]`, les anciens raccourcis restent liés jusqu'au redémarrage du serveur.
- **Plan 6 — projets automatiques et worktrees** : la création automatique de projets et les worktrees ; les worktrees découverts ne sont pas enregistrés en base.

## Reports issus du plan 3

Ce que le plan 3 laisse volontairement de côté, à traiter dans les plans indiqués :

- **Plan 4 — TUI complet** : vue Sessions complète, « needs attention », `M-n` / `M-N`, compteur de la barre d'état, quotas et projection « limit around HH:MM », formulaire `N`, « dernier type utilisé » de `n` (la touche `c` lance Claude, `n` lance toujours Bash) ; affichage du mode de permission en couleur dans le tableau de bord (le plan 3 l'affiche dans `meute session list`).
- **Plan 5 — MCP** : `meute mcp`, `--mcp-config`, `--append-system-prompt` et le contexte composé du § 8.
- **Plan 6 — finitions** : reprise `--resume`, états sauvegardés, worktrees, `meute doctor` ; purge de `session_events`, qui grandit sans limite et garde des extraits de commandes de 80 caractères.

Limites connues, relevées pendant le plan 3 :

- **Hook `Notification`** : Claude Code 2.1.302 ne l'a jamais émis pendant la capture S7 ; les tests utilisent un exemple fait à la main. À recapturer quand une version l'émet.
- **Chemin chaud `ingest hook`** : 44,8 ms en médiane (p95 45,6 ms) pour un budget de 50 ms ; peu de marge et aucun test de durée ne le garde.
- **`ingest`** : une charge trop grosse n'est pas lue jusqu'au bout ; la rotation de `ingest.log` n'est pas atomique entre processus et le journal est ouvert sans `O_NOFOLLOW` ; un hook contenant des substituts isolés est abandonné (journalisé).
- **États** : un `SubagentStop` tardif ignoré, et un état supposé (`stuck?`, `idle`), mettent quand même à jour `last_activity_at` ; un sous-agent d'arrière-plan qui finit pendant que l'utilisateur lit n'apparaît pas dans l'état.
- **Statusline** : les descendants `setsid` de la commande `[statusline] chain` lui survivent.
- **`--settings`** : un `settings.json` ou un dossier de session remplacé par un lien symbolique est suivi ; les dossiers parents du dossier 0700 suivent l'umask ; le dossier de réglages reste en place si le lancement échoue.
- **`claude agents --json`** : la liste des sessions extérieures reste vide pendant qu'une nouvelle tentative attend après un échec ; la purge des relevés au démarrage du tableau de bord n'est pas protégée contre `sqlite3.Error`.
- **Verrou de migration** : `flock` sans délai maximal.
- Les défauts connus du tableau de bord listés dans « Reports issus du plan 2 » restent ouverts.
