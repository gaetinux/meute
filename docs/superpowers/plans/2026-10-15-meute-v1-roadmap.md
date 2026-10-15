# Feuille de route de la V1 de meute

- Spécification : `docs/superpowers/specs/2026-10-15-meute-design.md`
- Spikes : `docs/superpowers/spikes/2026-10-15-spikes-s1-s5.md`

La V1 est découpée en six plans. Chacun produit un logiciel utilisable et testé, et donne lieu à une PR. Le plan N+1 n'est rédigé qu'une fois le plan N mergé, pour tenir compte de ce que son implémentation a appris.

| # | Plan | Livrable | Sections de la spécification |
|---|---|---|---|
| 1 | **Socle et tâches** | Workspace, CI, configuration, base SQLite et migrations, gestion des tâches et des projets en CLI | § 4.2, 4.3, 9.1–9.3, 13, 16, 17 |
| 2 | tmux, dépôts et sessions Bash | `meute` démarre son serveur tmux, sa disposition (zone principale et tableau de bord minimal), découvre les dépôts et lance, échange, réconcilie et arrête des sessions Bash | § 5, 6.1, 6.3–6.5, 10 (découverte) |
| 3 | Adaptateur Claude | Lancement de Claude (§ 6.2), `meute ingest hook` / `statusline`, rendu de la statusline, `claude agents --json` | § 5.5, 6.2, 7 |
| 4 | TUI complet | Vue Sessions (projets, « à traiter », quotas et projection, détails), vue Tâches (saisie rapide avec aperçu, regroupements, détail), mode étroit | § 4.5, 5.2, 7.4, 9.5, 10 |
| 5 | MCP | `meute mcp` et les outils de tâches, contexte composé (§ 8) | § 8, 12 |
| 6 | Finitions de la V1 | Worktrees, reprise, états sauvegardés, projets créés automatiquement, `meute doctor`, README | § 6.5, 6.6, 10, 11, 13 |

Ce que ce découpage implique :

- **Après le plan 1**, meute est déjà un gestionnaire de tâches en CLI, et le cœur métier (`meute-core`) existe.
- **Après le plan 3**, l'auteur peut remplacer son mod pour la supervision, avec un tableau de bord minimal.
- **Après le plan 4**, le critère de réussite n° 1 de la spécification (§ 1.2) est atteignable.
