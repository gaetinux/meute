# Feuille de route de la V1 de meute

- Spécification : `docs/superpowers/specs/2026-10-15-meute-design.md`
- Spikes : `docs/superpowers/spikes/2026-10-15-spikes-s1-s5.md`, `docs/superpowers/spikes/2026-10-16-spike-s6-demarrage-python.md`

## Migration vers Python (2026-10-16)

meute passe de Rust à Python, pour que l'auteur, qui maîtrise Python et non Rust, puisse comprendre et relire le code que Claude écrit. Conception : `docs/superpowers/specs/2026-10-16-migration-python-design.md`. Le code Rust est conservé sous deux tags, qui servent de référence de comportement : `rust-plan-1` (`main` à la fin du plan 1 Rust) et `rust-plan-2-wip` (plan 2 Rust largement implémenté, non mergé). Le découpage en six plans ne change pas.

La V1 est découpée en six plans. Chacun produit un logiciel utilisable et testé, et donne lieu à une PR. Le plan N+1 n'est rédigé qu'une fois le plan N mergé, pour tenir compte de ce que son implémentation a appris.

| # | Plan | Livrable | Sections de la spécification |
|---|---|---|---|
| 1 | **Socle et tâches** — *à refaire en Python* : `docs/superpowers/plans/2026-10-16-meute-plan-1-python-socle-taches.md` | Workspace, CI, configuration, base SQLite et migrations, gestion des tâches et des projets en CLI | § 4.2, 4.3, 9.1–9.3, 13, 16, 17 |
| 2 | tmux, dépôts et sessions Bash — *plan Rust rédigé et largement implémenté sous `rust-plan-2-wip`, à réécrire pour Python après le plan 1* | `meute` démarre son serveur tmux, sa disposition (zone principale et tableau de bord minimal), découvre les dépôts et lance, échange, réconcilie et arrête des sessions Bash | § 5, 6.1, 6.3–6.5, 10 (découverte) |
| 3 | Adaptateur Claude | Lancement de Claude (§ 6.2), `meute ingest hook` / `statusline`, rendu de la statusline, `claude agents --json` | § 5.5, 6.2, 7 |
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
- **Plan 3, critère d'entrée — ouverture concurrente de la base** : deux processus qui ouvrent ou migrent la base en même temps (les hooks de Claude se déclenchent en parallèle) doivent passer par un verrou `IMMEDIATE`, ou relire la version et réessayer, autour de la sauvegarde et de la migration.
- **Avant les plans 2 à 6 — tests** : regrouper les fonctions utilitaires de test de `meute-core` dans `tests/common/` — *intégré au plan 1 Python* (fixtures dans `tests/conftest.py`, fonctions dans `tests/support.py`).

